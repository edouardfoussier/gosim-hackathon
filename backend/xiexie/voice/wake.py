"""Porcupine wake-word detector — wakes Xiexie on hearing "Xiexie".

Design notes
------------
* All heavy deps (``pvporcupine``, ``sounddevice``) are imported lazily inside
  the methods that need them, so this module imports cleanly on dev machines
  where the wheels aren't installed yet.
* If ``PICOVOICE_ACCESS_KEY`` is missing, the detector logs a warning and
  reports ``is_available() == False`` — the rest of Xiexie keeps running and
  the push-to-talk fallback (``ptt.py``) takes over.
* Custom model lookup order:
    1. ``$XIEXIE_PPN_PATH`` env override
    2. ``<repo>/models/xiexie_mac.ppn``
    3. built-in keyword ``"computer"`` (graceful demo fallback)
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

# 16 kHz mono PCM is the only sample format Porcupine accepts.
SAMPLE_RATE = 16_000


def _default_ppn_path() -> Path:
    override = os.getenv("XIEXIE_PPN_PATH")
    if override:
        return Path(override).expanduser()
    # repo_root/models/xiexie_mac.ppn — assume backend/xiexie/voice/wake.py layout.
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "models" / "xiexie_mac.ppn"


class WakeWordDetector:
    """Background wake-word listener.

    Lifecycle:
        detector = WakeWordDetector()
        detector.start(on_wake)   # spawns a daemon thread
        ...
        detector.stop()
    """

    def __init__(
        self,
        access_key: str | None = None,
        ppn_path: Path | None = None,
        sensitivity: float = 0.6,
    ) -> None:
        self._access_key = access_key or os.getenv("PICOVOICE_ACCESS_KEY") or ""
        self._ppn_path = ppn_path or _default_ppn_path()
        self._sensitivity = sensitivity

        self._thread: threading.Thread | None = None
        self._stop_evt = threading.Event()
        self._callback: Callable[[], None] | None = None
        # Records which keyword variant we ended up using ("xiexie" or "computer").
        self._keyword_label: str = "unknown"

    # ------------------------------------------------------------------ public

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def is_available(self) -> bool:
        """True iff we have a Picovoice key (custom .ppn is optional)."""
        return bool(self._access_key)

    def start(self, callback: Callable[[], None]) -> None:
        """Spawn the listener thread. No-op if already running or unavailable."""
        if self.running:
            logger.debug("wake-word detector already running")
            return
        if not self.is_available():
            logger.warning(
                "PICOVOICE_ACCESS_KEY not set — wake-word disabled, "
                "falling back to push-to-talk (ctrl+option)."
            )
            return

        self._callback = callback
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._run, name="xiexie-wake", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_evt.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        self._thread = None

    # ------------------------------------------------------------------ inner

    def _build_porcupine(self):
        """Lazy-construct the Porcupine engine. Returns the engine or raises."""
        import pvporcupine  # type: ignore

        if self._ppn_path.exists():
            self._keyword_label = "xiexie (custom)"
            logger.info("[wake] using custom model %s", self._ppn_path)
            return pvporcupine.create(
                access_key=self._access_key,
                keyword_paths=[str(self._ppn_path)],
                sensitivities=[self._sensitivity],
            )

        # Built-in keyword fallback so the demo works before the user
        # uploads a custom .ppn from console.picovoice.ai.
        self._keyword_label = "computer (built-in fallback)"
        logger.warning(
            "[wake] custom model %s not found — using built-in keyword 'computer'. "
            "Train a custom 'xiexie' model on https://console.picovoice.ai and drop "
            "the .ppn at the path above for the real wake-word.",
            self._ppn_path,
        )
        return pvporcupine.create(
            access_key=self._access_key,
            keywords=["computer"],
            sensitivities=[self._sensitivity],
        )

    def _run(self) -> None:
        try:
            porcupine = self._build_porcupine()
        except Exception as exc:
            logger.error("[wake] failed to start Porcupine: %s", exc)
            return

        try:
            import sounddevice as sd  # type: ignore
        except Exception as exc:
            logger.error(
                "[wake] sounddevice unavailable (%s) — wake-word disabled.", exc
            )
            try:
                porcupine.delete()
            except Exception:
                pass
            return

        frame_length = porcupine.frame_length
        logger.info(
            "[wake] listening for '%s' (frame=%d @ %d Hz)",
            self._keyword_label,
            frame_length,
            SAMPLE_RATE,
        )

        try:
            with sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=frame_length,
            ) as stream:
                while not self._stop_evt.is_set():
                    pcm_bytes, _overflowed = stream.read(frame_length)
                    # Porcupine wants a list/array of int16 samples.
                    import struct

                    pcm = struct.unpack_from(
                        "h" * frame_length, bytes(pcm_bytes)
                    )
                    if porcupine.process(pcm) >= 0:
                        logger.info("[wake] heard '%s'", self._keyword_label)
                        cb = self._callback
                        if cb is not None:
                            try:
                                cb()
                            except Exception:
                                logger.exception("[wake] callback raised")
        except Exception:
            logger.exception("[wake] listener crashed")
        finally:
            try:
                porcupine.delete()
            except Exception:
                pass
            logger.info("[wake] listener stopped")
