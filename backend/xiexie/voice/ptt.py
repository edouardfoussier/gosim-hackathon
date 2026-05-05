"""Push-to-talk monitor — global ctrl+option chord via a CGEventTap.

This is the **safety net** for wake-word detection: even if Porcupine misses
the trigger word in a noisy room, holding ``ctrl`` + ``option`` activates
Xiexie. Releasing either modifier ends the press.

Implementation
--------------
We install a *listen-only* CGEventTap on the session input. Listen-only
means kernel events are observed but never blocked or modified — same
pattern Clicky's ``GlobalPushToTalkShortcutMonitor.swift`` uses, and the
right call for an accessibility-adjacent app where intercepting keystrokes
would be hostile.

The tap runs on a dedicated CFRunLoop inside a daemon thread so the FastAPI
event loop is unaffected.

Permissions: macOS will prompt for **Input Monitoring** the first time the
tap is created. Without that grant ``CGEventTapCreate`` returns ``None``
and we log a warning + degrade silently — the wake-word path keeps working.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Quartz event-flag bit-masks (see CGEventTypes.h).
_FLAG_CONTROL = 0x00040000  # kCGEventFlagMaskControl
_FLAG_ALT = 0x00080000  # kCGEventFlagMaskAlternate (a.k.a. option)
_CHORD_MASK = _FLAG_CONTROL | _FLAG_ALT


class PushToTalkMonitor:
    """Watches the global keyboard for the ctrl+option chord.

    ``on_press`` fires when both modifiers go down together; ``on_release``
    fires when either modifier comes back up. Both callbacks are invoked
    from the Quartz tap thread — keep them fast / non-blocking.
    """

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._runloop = None
        self._tap = None
        self._on_press: Callable[[], None] | None = None
        self._on_release: Callable[[], None] | None = None
        self._chord_active = False

    # ------------------------------------------------------------------ public

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(
        self,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
    ) -> None:
        if self.running:
            logger.debug("PTT monitor already running")
            return
        self._on_press = on_press
        self._on_release = on_release
        self._thread = threading.Thread(
            target=self._run, name="xiexie-ptt", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        try:
            from Quartz import CFRunLoopStop  # type: ignore

            if self._runloop is not None:
                CFRunLoopStop(self._runloop)
        except Exception:
            logger.debug("PTT stop: CFRunLoopStop unavailable", exc_info=True)
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        self._thread = None
        self._runloop = None
        self._tap = None

    # ------------------------------------------------------------------ inner

    def _handle_flags(self, flags: int) -> None:
        chord = (flags & _CHORD_MASK) == _CHORD_MASK
        if chord and not self._chord_active:
            self._chord_active = True
            logger.info("[ptt] ctrl+option pressed")
            cb = self._on_press
            if cb is not None:
                try:
                    cb()
                except Exception:
                    logger.exception("[ptt] on_press raised")
        elif not chord and self._chord_active:
            self._chord_active = False
            logger.info("[ptt] ctrl+option released")
            cb = self._on_release
            if cb is not None:
                try:
                    cb()
                except Exception:
                    logger.exception("[ptt] on_release raised")

    def _run(self) -> None:
        try:
            from Quartz import (  # type: ignore
                CFMachPortCreateRunLoopSource,
                CFRunLoopAddSource,
                CFRunLoopGetCurrent,
                CFRunLoopRun,
                CGEventGetFlags,
                CGEventTapCreate,
                CGEventTapEnable,
                kCFAllocatorDefault,
                kCFRunLoopCommonModes,
                kCGEventFlagsChanged,
                kCGEventTapOptionListenOnly,
                kCGHeadInsertEventTap,
                kCGSessionEventTap,
            )
        except Exception as exc:
            logger.error(
                "[ptt] Quartz unavailable (%s) — push-to-talk disabled. "
                "Install pyobjc-framework-Quartz on macOS.",
                exc,
            )
            return

        event_mask = 1 << kCGEventFlagsChanged

        def _callback(_proxy, _etype, event, _refcon):
            try:
                flags = CGEventGetFlags(event)
                self._handle_flags(int(flags))
            except Exception:
                logger.exception("[ptt] callback failed")
            # listen-only ⇒ always return the original event untouched
            return event

        tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionListenOnly,
            event_mask,
            _callback,
            None,
        )
        if tap is None:
            logger.warning(
                "[ptt] CGEventTapCreate returned None — grant Input Monitoring "
                "to your terminal in System Settings → Privacy & Security."
            )
            return

        self._tap = tap
        source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0)
        runloop = CFRunLoopGetCurrent()
        self._runloop = runloop
        CFRunLoopAddSource(runloop, source, kCFRunLoopCommonModes)
        CGEventTapEnable(tap, True)
        logger.info("[ptt] watching for ctrl+option chord")
        try:
            CFRunLoopRun()
        finally:
            try:
                CGEventTapEnable(tap, False)
            except Exception:
                pass
            logger.info("[ptt] monitor stopped")
