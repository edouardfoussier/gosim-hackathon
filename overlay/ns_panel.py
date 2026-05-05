"""PyObjC bridge: promote the Qt window's NSWindow to behave like an NSPanel.

PyQt6 gives us a transparent always-on-top QWidget, which is enough for a
single Space. To survive Spaces switching (and to stay visible above
fullscreen apps — including Mail.app modal sheets, which is the whole
point of Scam Shield), we reach into the underlying ``NSWindow`` and
toggle three things:

1. ``setLevel_(NSScreenSaverWindowLevel)`` — sit above *everything* in
   normal app windowing, including modal sheets, popovers, and tear-off
   panels. We deliberately step above ``NSStatusWindowLevel`` (25) since
   a finding from the Clicky deep-read showed that Mail.app phishing
   warning sheets render at a level that hides a status-level glyph.
   Screen-saver level (1000) is the conventional "really above
   everything else from the app world" tier.
2. ``setCollectionBehavior_`` with the ``CanJoinAllSpaces |
   StationaryFanInOut | FullScreenAuxiliary`` mask — join every Space and
   coexist with fullscreen apps.
3. ``setIgnoresMouseEvents_(True)`` — global click-through. The glyph
   itself uses ``setMask`` to define a non-pass-through region, so we
   keep this False on the QWidget side and only flip it via Cocoa when
   we want the *whole* window to ignore clicks.

If PyObjC is unavailable (non-macOS, or missing dep) we no-op so the
overlay still runs in degraded mode (single Space, normal stack).
"""

from __future__ import annotations

import sys

# These collection-behaviour bit values are stable Cocoa constants — we
# inline them to avoid a hard dep on AppKit symbols when PyObjC isn't
# installed (e.g. CI on Linux).
_NS_WINDOW_COLLECTION_BEHAVIOR_CAN_JOIN_ALL_SPACES = 1 << 0
_NS_WINDOW_COLLECTION_BEHAVIOR_STATIONARY = 1 << 4
_NS_WINDOW_COLLECTION_BEHAVIOR_FULLSCREEN_AUXILIARY = 1 << 8
_NS_WINDOW_COLLECTION_BEHAVIOR_IGNORES_CYCLE = 1 << 6

# NSScreenSaverWindowLevel == 1000 — sits above NSStatusWindowLevel (25),
# NSModalPanelWindowLevel (8), and NSFloatingWindowLevel (3). We import
# the symbol from AppKit when PyObjC is available so a future Cocoa
# revision can adjust the underlying integer for us.
_NS_SCREEN_SAVER_WINDOW_LEVEL = 1000


def promote_to_panel(qt_widget, *, ignore_mouse: bool = False) -> bool:
    """Promote ``qt_widget``'s underlying NSWindow to an always-on-top panel.

    Returns ``True`` if Cocoa tweaks were applied, ``False`` otherwise.
    """
    if sys.platform != "darwin":
        return False

    try:
        from AppKit import NSApp  # type: ignore[import-not-found]
    except Exception:  # pragma: no cover — pyobjc missing
        print("[overlay.ns_panel] PyObjC not available — Spaces tweak skipped.")
        return False

    try:
        from AppKit import NSScreenSaverWindowLevel  # type: ignore[import-not-found]

        screen_saver_level = int(NSScreenSaverWindowLevel)
    except Exception:
        screen_saver_level = _NS_SCREEN_SAVER_WINDOW_LEVEL

    # The Qt widget must already be ``show()``-n for an NSWindow to exist.
    win_id = int(qt_widget.winId())
    target = None
    for ns_win in NSApp.windows():
        try:
            if int(ns_win.windowNumber()) == win_id:
                target = ns_win
                break
        except Exception:
            continue
    if target is None and NSApp.windows():
        # Fallback: most recently created window. Good enough for our
        # single-window overlay.
        target = NSApp.windows()[-1]
    if target is None:
        return False

    target.setLevel_(screen_saver_level)
    target.setCollectionBehavior_(
        _NS_WINDOW_COLLECTION_BEHAVIOR_CAN_JOIN_ALL_SPACES
        | _NS_WINDOW_COLLECTION_BEHAVIOR_STATIONARY
        | _NS_WINDOW_COLLECTION_BEHAVIOR_FULLSCREEN_AUXILIARY
        | _NS_WINDOW_COLLECTION_BEHAVIOR_IGNORES_CYCLE
    )
    target.setIgnoresMouseEvents_(bool(ignore_mouse))
    target.setHidesOnDeactivate_(False)
    # Don't grab focus when shown — critical so the user keeps typing in
    # the underlying app while our glyph appears.
    try:
        target.setBecomesKeyOnlyIfNeeded_(True)
    except Exception:
        pass
    return True
