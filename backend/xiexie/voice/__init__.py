"""Voice loop — STT in, TTS out. Local-first for demo robustness.

Triggers:
* ``wake.WakeWordDetector`` — Porcupine-driven "Xiexie" wake-word
* ``ptt.PushToTalkMonitor`` — global ctrl+option safety-net chord

``start_voice_triggers(on_activate)`` wires both paths to a single
callback so the demo always has at least one working activation route.
"""

from __future__ import annotations

from collections.abc import Callable

from . import ptt, wake

__all__ = ["ptt", "wake", "start_voice_triggers"]


def start_voice_triggers(
    on_activate: Callable[[], None],
) -> tuple[wake.WakeWordDetector, ptt.PushToTalkMonitor]:
    """Wire wake-word + push-to-talk to ``on_activate`` and return the monitors.

    * Wake-word fires ``on_activate()`` on each detection.
    * PTT fires ``on_activate()`` on key-down (release is currently a no-op
      placeholder — the STT loop decides when to stop listening).

    Both paths run concurrently. Either degrading silently (no Picovoice key,
    no Quartz, no Input Monitoring grant) does not affect the other.
    """
    detector = wake.WakeWordDetector()
    detector.start(on_activate)

    monitor = ptt.PushToTalkMonitor()
    monitor.start(on_press=on_activate, on_release=lambda: None)

    return detector, monitor
