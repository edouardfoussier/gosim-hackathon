"""Text-to-speech.

Hierarchy:
1. Kokoro (local, warm voice) — preferred when installed.
2. macOS ``say`` command — always available, no extra deps. Good fallback
   for hackathon dev so we don't wait on Kokoro install.
3. ElevenLabs (premium) — for the final demo video only, gated by env var.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def _kokoro_available() -> bool:
    try:
        import kokoro  # type: ignore  # noqa: F401

        return True
    except ImportError:
        return False


def synth_to_wav(text: str, voice: str = "af_bella") -> Path:
    """Synthesise ``text`` to a WAV file and return its path."""
    out = Path(tempfile.mkstemp(prefix="xiexie_tts_", suffix=".wav")[1])

    if _kokoro_available():
        from kokoro import KPipeline  # type: ignore
        import soundfile as sf  # type: ignore

        pipeline = KPipeline(lang_code="a")
        audio = None
        for _, _, audio in pipeline(text, voice=voice):  # noqa: B007
            break
        if audio is None:
            raise RuntimeError("Kokoro returned no audio")
        sf.write(out, audio, 24000)
        return out

    # macOS fallback — produces AIFF natively, we ask for AAC then rename.
    aiff = out.with_suffix(".aiff")
    subprocess.run(["say", "-o", str(aiff), text], check=True, timeout=15)
    return aiff


def speak(text: str) -> None:
    """Fire-and-forget speech using the simplest available backend."""
    try:
        subprocess.run(["say", text], check=True, timeout=20)
    except FileNotFoundError:
        # not on macOS — just synth + drop, the UI will play it
        synth_to_wav(text)
