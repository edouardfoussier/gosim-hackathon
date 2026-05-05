"""Speech-to-text using faster-whisper (local model).

Lazy-loads the model on first call to keep server startup snappy. Default
size is ``base`` for sub-second latency on Apple silicon; bump to
``small`` if accuracy is the bottleneck.
"""

from __future__ import annotations

import io
from functools import lru_cache
from typing import BinaryIO

# Lazy import: keep import-time cheap so unrelated tests don't pay the cost.
def _model_size() -> str:
    import os

    return os.getenv("WHISPER_MODEL_SIZE", "base")


@lru_cache(maxsize=1)
def _model():
    from faster_whisper import WhisperModel  # type: ignore

    return WhisperModel(_model_size(), device="auto", compute_type="auto")


def transcribe_bytes(audio_bytes: bytes, language: str = "en") -> str:
    """Transcribe a WAV/MP3/etc blob in memory. Returns plain text."""
    buf: BinaryIO = io.BytesIO(audio_bytes)
    segments, _info = _model().transcribe(buf, language=language, vad_filter=True)
    return " ".join(seg.text.strip() for seg in segments).strip()


def transcribe_file(path: str, language: str = "en") -> str:
    segments, _info = _model().transcribe(path, language=language, vad_filter=True)
    return " ".join(seg.text.strip() for seg in segments).strip()
