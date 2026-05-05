"""Record user-spoken "Xiexie" wake-word samples for openWakeWord training.

Usage:
    cd training/wakeword
    python -m record_samples              # record 30 samples (default)
    python -m record_samples --count 50   # record 50 samples
    python -m record_samples --duration 1.6 --gap 0.7

Each sample is a 16 kHz mono WAV saved to ``positives/sample_NNNN.wav`` and is
fed into the Colab training notebook as a high-weight positive example
(mixed in alongside the synthetic Piper clips).

Designed for macOS arm64 (Apple Silicon). Requires ``sounddevice`` and
``soundfile``, both already in the backend's pyproject.toml. Press
Ctrl+C to stop early — partial captures are fine.

Tips for good samples
---------------------
* Quiet room. No music, no background TV.
* Hold the mic ~6–12 inches away.
* Vary tone, speed, and emphasis between takes (whisper / loud / fast / slow).
* Don't pause — start saying "Xiexie" the instant you hear the beep.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

POSITIVES_DIR = Path(__file__).resolve().parent / "positives"
SAMPLE_RATE = 16_000


def _beep(freq: float = 880.0, duration: float = 0.18, volume: float = 0.4) -> None:
    """Short sine-wave 'go' tone via sounddevice."""
    try:
        import numpy as np
        import sounddevice as sd
    except Exception:
        # Fall back to terminal bell if audio output is busy.
        print("\a", end="", flush=True)
        return

    n = int(duration * SAMPLE_RATE)
    t = np.linspace(0.0, duration, n, endpoint=False, dtype=np.float32)
    tone = (volume * np.sin(2.0 * math.pi * freq * t)).astype(np.float32)
    # 5 ms fade in/out so we don't click the speaker.
    fade = max(1, int(0.005 * SAMPLE_RATE))
    tone[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
    tone[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    try:
        sd.play(tone, SAMPLE_RATE, blocking=True)
    except Exception:
        print("\a", end="", flush=True)


def _record_one(duration: float):
    """Record `duration` seconds of mono int16 audio at 16 kHz."""
    import numpy as np
    import sounddevice as sd

    frames = int(duration * SAMPLE_RATE)
    audio = sd.rec(
        frames=frames,
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocking=True,
    )
    return np.asarray(audio).reshape(-1)


def _next_index(out_dir: Path) -> int:
    existing = sorted(out_dir.glob("sample_*.wav"))
    if not existing:
        return 0
    last = existing[-1].stem.removeprefix("sample_")
    try:
        return int(last) + 1
    except ValueError:
        return len(existing)


def _peak_dbfs(samples) -> float:
    import numpy as np

    arr = np.asarray(samples, dtype=np.float32)
    peak = float(np.max(np.abs(arr)))
    if peak <= 0.0:
        return -120.0
    return 20.0 * math.log10(peak / 32768.0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--count", type=int, default=30, help="how many samples to record"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=1.6,
        help="seconds per recording (1.5–2s is plenty for 'Xiexie')",
    )
    parser.add_argument(
        "--gap",
        type=float,
        default=0.6,
        help="silence between takes (lets you breathe)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=POSITIVES_DIR,
        help="output directory (default: training/wakeword/positives/)",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="print available audio input devices and exit",
    )
    args = parser.parse_args(argv)

    try:
        import sounddevice as sd  # noqa: F401
        import soundfile as sf
    except ImportError as exc:
        print(f"error: missing dependency ({exc}). Install with:")
        print("  uv pip install sounddevice soundfile numpy")
        return 1

    if args.list_devices:
        print(sd.query_devices())
        return 0

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    start_idx = _next_index(out_dir)

    print()
    print("=" * 60)
    print("  Xiexie wake-word recorder")
    print("=" * 60)
    print(f"  output dir : {out_dir}")
    print(f"  samples    : {args.count} (will append from #{start_idx:04d})")
    print(f"  duration   : {args.duration:.2f}s per take")
    print(f"  sample rate: {SAMPLE_RATE} Hz, mono, int16")
    print()
    print("  Tips:")
    print("    * Quiet room. Mic ~6-12 inches away.")
    print("    * Vary tone, speed, emphasis between takes.")
    print("    * Start saying 'Xiexie' the instant you hear the beep.")
    print("    * Press Ctrl+C anytime to stop early. Partial sets are fine.")
    print()
    try:
        input("Press Enter to start... ")
    except (EOFError, KeyboardInterrupt):
        print()
        return 0

    saved = 0
    too_quiet = 0
    too_loud = 0
    try:
        for k in range(args.count):
            i = start_idx + k
            print(f"\n[{k + 1:>2d}/{args.count}] sample_{i:04d}.wav — get ready...")
            time.sleep(args.gap)
            print("            BEEP — say 'Xiexie' now")
            _beep()
            audio = _record_one(args.duration)
            db = _peak_dbfs(audio)
            path = out_dir / f"sample_{i:04d}.wav"
            sf.write(path, audio, SAMPLE_RATE, subtype="PCM_16")
            saved += 1
            note = ""
            if db < -45:
                too_quiet += 1
                note = " (very quiet — speak louder or move closer)"
            elif db > -3:
                too_loud += 1
                note = " (clipping — back off a bit)"
            print(f"            saved peak={db:+.1f} dBFS{note}")
    except KeyboardInterrupt:
        print("\n  ^C — stopping early. Saved samples are kept.")

    print()
    print("=" * 60)
    print(f"  done. saved {saved} sample(s) into {out_dir}")
    if too_quiet:
        print(f"  {too_quiet} sample(s) were very quiet — consider re-recording.")
    if too_loud:
        print(f"  {too_loud} sample(s) clipped — consider re-recording.")
    print()
    print("  Next step:")
    print("    1. Listen to a few samples to spot-check quality.")
    print("    2. zip the positives folder:  cd training/wakeword && "
          "zip -r positives.zip positives")
    print("    3. Upload positives.zip to Google Drive, then open the")
    print("       Colab notebook and run all cells.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
