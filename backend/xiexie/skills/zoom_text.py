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
    if amount not in _PRESSES_BY_AMOUNT:
        return f"I can make things smaller, normal, bigger, or much bigger — {amount!r} is not one of those."
    key, times = _PRESSES_BY_AMOUNT[amount]
    ok, output = _press_cmd_chord(key, times)
    if not ok:
        return (
            "I tried to make the text bigger but the front-most app didn't accept the "
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
            "Increase or decrease the text size in the foreground macOS application "
            "by sending Cmd+Plus / Cmd+Minus. Works in Chrome, Safari, Firefox, "
            "Mail.app, Pages, Preview, Notes, and most other apps that honour the "
            "universal zoom shortcut."
        ),
        parameters={
            "type": "object",
            "properties": {
                "amount": {
                    "type": "string",
                    "enum": ["smaller", "normal", "bigger", "much bigger"],
                    "default": "bigger",
                    "description": "How much to change the text size. Defaults to one notch bigger.",
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
