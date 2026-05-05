"""zoom_text — make text bigger / smaller in the foreground app.

Sends ``Cmd+Plus`` (or ``Cmd+Minus``) repeatedly to the active
application via the macOS Accessibility API. Works in browsers (Chrome,
Safari, Firefox), Mail.app, Pages, Preview, Notes, and most other apps
that honour the universal zoom shortcut. Falls back gracefully when
the foreground app doesn't recognise the shortcut.
"""

from __future__ import annotations

import subprocess
from typing import Any

from .registry import Skill, register

_PRESSES_BY_AMOUNT = {
    "smaller": ("minus", 1),
    "normal": ("zero", 1),
    "bigger": ("plus", 2),
    "much bigger": ("plus", 4),
}


def _osascript(script: str) -> tuple[bool, str]:
    out = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, timeout=6
    )
    return out.returncode == 0, (out.stdout or out.stderr).strip()


def _press_cmd_chord(key: str, times: int) -> tuple[bool, str]:
    # AppleScript ``key code`` map for the symbol row keys we care about.
    # We use ``key code`` rather than ``keystroke`` because Cmd+= / Cmd+-
    # behave more reliably across keyboard layouts when sent by code.
    code_map = {"plus": 24, "minus": 27, "zero": 29}  # =/+, -/_, 0/)
    code = code_map[key]
    repeat = "\n".join(["    key code {} using command down".format(code)] * times)
    script = f"""
    tell application "System Events"
{repeat}
    end tell
    """
    return _osascript(script)


def run(args: dict[str, Any]) -> str:
    amount = str(args.get("amount", "bigger")).strip().lower()
    # Logged on every call so we can see in the backend log when the
    # model picks the wrong direction (which is what Edouard hit when
    # "agrandir le texte" was routed as ``amount=smaller``).
    print(f"[zoom_text] called with amount={amount!r}", flush=True)
    if amount not in _PRESSES_BY_AMOUNT:
        return f"I can make things smaller, normal, bigger, or much bigger — {amount!r} is not one of those."
    key, times = _PRESSES_BY_AMOUNT[amount]
    ok, output = _press_cmd_chord(key, times)
    if not ok:
        return (
            "I tried to change the text size but the front-most app didn't accept the "
            "shortcut. Most browsers and Mail.app should work — try clicking on the "
            "window first, then ask me again."
        )
    if amount == "smaller":
        return "Made the text a touch smaller."
    if amount == "normal":
        return "Brought the text back to its normal size."
    if amount == "much bigger":
        return "Made the text quite a bit bigger — hopefully easier on your eyes."
    return "Made the text bigger for you."


SKILL = register(
    Skill(
        name="zoom_text",
        description=(
            "Change the text size in the foreground macOS application. "
            "Use ``amount='bigger'`` (default) when the user asks to MAKE TEXT "
            "LARGER / AGRANDIR / zoom in / increase / make it easier to read. "
            "Use ``amount='smaller'`` ONLY when the user explicitly asks to make text "
            "smaller / réduire / zoom out / make it smaller. Sends Cmd+= or "
            "Cmd+- via System Events; works in Chrome, Safari, Firefox, Mail.app, "
            "Pages, Preview, Notes, and most apps that honour the universal "
            "zoom shortcut."
        ),
        parameters={
            "type": "object",
            "properties": {
                "amount": {
                    "type": "string",
                    "enum": ["smaller", "normal", "bigger", "much bigger"],
                    "default": "bigger",
                    "description": (
                        "Direction + magnitude. 'bigger' = LARGER text (zoom in, "
                        "agrandir). 'smaller' = smaller text (zoom out). 'normal' "
                        "resets to default. 'much bigger' is bigger ×4."
                    ),
                }
            },
        },
        run=run,
        destructive=False,
        tags=["accessibility", "os"],
    )
)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--amount", default="bigger")
    a = p.parse_args()
    print(run({"amount": a.amount}))
