"""Wake-word detector — wakes Xiexie on hearing "Xiexie".

Two pluggable backends, picked at construction time in this priority order:

    1. Custom Picovoice ``.ppn`` at ``models/xiexie_mac.ppn``
       (requires ``PICOVOICE_ACCESS_KEY``; the highest-quality option but gated
       behind Picovoice's commercial-approval workflow).
    2. **Custom openWakeWord ONNX at ``models/xiexie.onnx``** (Apache-2.0, no key,
       no cloud — the option we ship by default once the Colab notebook in
       ``training/wakeword/`` has produced a model).
    3. Built-in Porcupine keyword ``"computer"`` (still requires the Picovoice
       key, but uses no custom assets — graceful demo fallback).
    4. Nothing — ``is_available() -> False`` and the push-to-talk monitor in
       ``ptt.py`` carries the demo on its own.

Design notes
------------
* All heavy deps (``pvporcupine``, ``openwakeword``, ``sounddevice``) are
  imported lazily inside the methods that need them, so this module imports
  cleanly on dev machines where the wheels aren't installed yet.
* ``is_available()`` reports whether *some* backend will be used.
* The chosen backend is exposed via :pyattr:`WakeWordDetector.backend` for
  startup logging (``"picovoice"`` / ``"openwakeword"`` / ``None``).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

# 16 kHz mono PCM is what every backend expects.
SAMPLE_RATE = 16_000

Backend = Literal["picovoice", "openwakeword"]


def _repo_root() -> Path:
    # backend/xiexie/voice/wake.py -> repo root is parents[3].
    return Path(__file__).resolve().parents[3]


def _default_ppn_path() -> Path:
    override = os.getenv("XIEXIE_PPN_PATH")
    if override:
        return Path(override).expanduser()
    return _repo_root() / "models" / "xiexie_mac.ppn"


def _default_oww_path() -> Path:
    override = os.getenv("XIEXIE_OWW_PATH")
    if override:
        return Path(override).expanduser()
    return _repo_root() / "models" / "xiexie.onnx"


class WakeWordDetector:
    """Background wake-word listener.

    Lifecycle::

        detector = WakeWordDetector()
        detector.start(on_wake)   # spawns a daemon thread
        ...
        detector.stop()
    """

    def __init__(
        self,
        access_key: str | None = None,
        ppn_path: Path | None = None,
        oww_path: Path | None = None,
        sensitivity: float = 0.6,
        oww_threshold: float = 0.5,
        oww_cooldown_s: float = 1.5,
    ) -> None:
        self._access_key = access_key or os.getenv("PICOVOICE_ACCESS_KEY") or ""
        self._ppn_path = ppn_path or _default_ppn_path()
        self._oww_path = oww_path or _default_oww_path()
        self._sensitivity = sensitivity
        self._oww_threshold = oww_threshold
        self._oww_cooldown_s = oww_cooldown_s

        self._thread: threading.Thread | None = None
        self._stop_evt = threading.Event()
        self._callback: Callable[[], None] | None = None
        # Filled by ``_select_backend``; describes how the detector is configured.
        self._backend: Backend | None = None
        self._backend_label: str = "unavailable"
        self._select_backend()

    # ------------------------------------------------------------------ public

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def backend(self) -> Backend | None:
        """Backend in use, or ``None`` if no usable backend was found."""
        return self._backend

    @property
    def backend_label(self) -> str:
        """Human-readable description of the selected backend ("xiexie (openwakeword)"...)."""
        return self._backend_label

    def is_available(self) -> bool:
        """True iff a wake-word backend is configured and ready."""
        return self._backend is not None

    def start(self, callback: Callable[[], None]) -> None:
        """Spawn the listener thread. No-op if already running or unavailable."""
        if self.running:
            logger.debug("wake-word detector already running")
            return
        if not self.is_available():
            logger.warning(
                "[wake] no wake-word backend available — falling back to "
                "push-to-talk (ctrl+option). To enable: drop a custom "
                "Picovoice .ppn at %s, or a trained openWakeWord ONNX at %s, "
                "or set PICOVOICE_ACCESS_KEY for the built-in 'computer' fallback.",
                self._ppn_path,
                self._oww_path,
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

    # ----------------------------------------------------------------- backend

    def _select_backend(self) -> None:
        """Pick a backend at construction time per the priority chain.

        Picovoice is preferred over openWakeWord *only* when both a key and a
        custom .ppn are present — the .ppn is what makes the wake-word actually
        say "Xiexie". A bare key with no .ppn falls through to openWakeWord
        (silent no-cloud) before degrading to the built-in "computer" keyword.
        """
        # Tier 1: custom Picovoice .ppn (best quality, requires key).
        if self._access_key and self._ppn_path.exists():
            self._backend = "picovoice"
            self._backend_label = "xiexie (picovoice .ppn)"
            return

        # Tier 2: custom openWakeWord ONNX (no key, no cloud).
        if self._oww_path.exists():
            self._backend = "openwakeword"
            self._backend_label = f"xiexie ({self._oww_path.name}, openwakeword)"
            return

        # Tier 3: built-in Porcupine "computer" keyword (key required).
        if self._access_key:
            self._backend = "picovoice"
            self._backend_label = "computer (porcupine built-in fallback)"
            return

        # Tier 4: no wake-word; PTT only.
        self._backend = None
        self._backend_label = "unavailable"

    # ----------------------------------------------------------------- runtime

    def _run(self) -> None:
        if self._backend == "picovoice":
            self._run_picovoice()
        elif self._backend == "openwakeword":
            self._run_openwakeword()
        else:
            logger.error("[wake] _run called with no backend selected")

    # -- picovoice ---------------------------------------------------------

    def _build_porcupine(self):
        """Lazy-construct the Porcupine engine. Returns the engine or raises."""
        import pvporcupine  # type: ignore

        if self._ppn_path.exists():
            logger.info("[wake] using custom Picovoice model %s", self._ppn_path)
            return pvporcupine.create(
                access_key=self._access_key,
                keyword_paths=[str(self._ppn_path)],
                sensitivities=[self._sensitivity],
            )

        # Built-in keyword fallback so the demo works before the user
        # uploads a custom .ppn from console.picovoice.ai.
        logger.warning(
            "[wake] custom Picovoice model %s not found — using built-in keyword "
            "'computer'. Train a custom 'xiexie' model on https://console.picovoice.ai "
            "and drop the .ppn at the path above for the real wake-word.",
            self._ppn_path,
        )
        return pvporcupine.create(
            access_key=self._access_key,
            keywords=["computer"],
            sensitivities=[self._sensitivity],
        )

    def _run_picovoice(self) -> None:
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
            "[wake] listening for '%s' (frame=%d @ %d Hz, picovoice)",
            self._backend_label,
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
                import struct

                while not self._stop_evt.is_set():
                    pcm_bytes, _overflowed = stream.read(frame_length)
                    pcm = struct.unpack_from(
                        "h" * frame_length, bytes(pcm_bytes)
                    )
                    if porcupine.process(pcm) >= 0:
                        logger.info("[wake] heard '%s'", self._backend_label)
                        self._fire_callback()
        except Exception:
            logger.exception("[wake] picovoice listener crashed")
        finally:
            try:
                porcupine.delete()
            except Exception:
                pass
            logger.info("[wake] picovoice listener stopped")

    # -- openwakeword ------------------------------------------------------

    def _run_openwakeword(self) -> None:
        try:
            from openwakeword.model import Model as OwwModel  # type: ignore
        except Exception as exc:
            logger.error(
                "[wake] openwakeword not installed (%s) — cannot use %s. "
                "Install with `uv pip install openwakeword`.",
                exc,
                self._oww_path,
            )
            return

        try:
            model = OwwModel(
                wakeword_models=[str(self._oww_path)],
                inference_framework="onnx",
            )
        except Exception as exc:
            logger.error("[wake] failed to load %s: %s", self._oww_path, exc)
            return

        try:
            import numpy as np  # type: ignore
            import sounddevice as sd  # type: ignore
        except Exception as exc:
            logger.error(
                "[wake] sounddevice/numpy unavailable (%s) — openwakeword disabled.",
                exc,
            )
            return

        # 80 ms frames are the recommended minimum; we use 80 ms exactly.
        frame_length = 1280
        try:
            model_keys = list(model.models.keys())
        except Exception:
            model_keys = []
        primary_key = model_keys[0] if model_keys else "xiexie"

        logger.info(
            "[wake] %s loaded (openwakeword) — listening (frame=%d @ %d Hz, threshold=%.2f)",
            self._oww_path.name,
            frame_length,
            SAMPLE_RATE,
            self._oww_threshold,
        )

        last_fire = 0.0
        try:
            with sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=frame_length,
            ) as stream:
                while not self._stop_evt.is_set():
                    pcm_bytes, _overflowed = stream.read(frame_length)
                    audio = np.frombuffer(bytes(pcm_bytes), dtype=np.int16)
                    try:
                        scores = model.predict(audio)
                    except Exception:
                        logger.exception("[wake] openwakeword predict failed")
                        continue
                    score = float(scores.get(primary_key, 0.0))
                    if score >= self._oww_threshold:
                        now = time.monotonic()
                        if now - last_fire >= self._oww_cooldown_s:
                            last_fire = now
                            logger.info(
                                "[wake] heard '%s' (openwakeword score=%.3f)",
                                primary_key,
                                score,
                            )
                            self._fire_callback()
        except Exception:
            logger.exception("[wake] openwakeword listener crashed")
        finally:
            logger.info("[wake] openwakeword listener stopped")

    # -- shared ------------------------------------------------------------

    def _fire_callback(self) -> None:
        cb = self._callback
        if cb is None:
            return
        try:
            cb()
        except Exception:
            logger.exception("[wake] callback raised")
