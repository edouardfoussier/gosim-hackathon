"""set_reminder — create a Reminders.app reminder via AppleScript.

Voice → osascript. Uses natural-language ``when`` strings ("tomorrow 9am",
"in 30 minutes", "at 3:30 pm"). For V1 we leave the date parsing to the LLM
planner — it converts the user's voice phrase into an ISO 8601 timestamp
before calling this skill.
"""

from __future__ import annotations

import datetime as dt
import subprocess
from typing import Any

from .registry import Skill, register


def _osascript(script: str) -> tuple[bool, str]:
    out = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, timeout=8
    )
    return out.returncode == 0, (out.stdout or out.stderr).strip()


def run(args: dict[str, Any]) -> str:
    when_iso = str(args.get("when_iso", "")).strip()
    what = str(args.get("what", "")).strip()
    if not what:
        return "What's the reminder for?"
    if not when_iso:
        return "When should I set it for?"

    try:
        when = dt.datetime.fromisoformat(when_iso)
    except ValueError:
        return f"I couldn't read that time ({when_iso!r}). Try ISO 8601, e.g. 2026-05-05T15:30."

    # AppleScript's ``date "..."`` constructor is locale-sensitive and
    # rejects perfectly-valid US-formatted strings on French / Chinese /
    # German locales (the user's previous "Invalid date and time date
    # May 05, 2026 03:30:00 PM" error). We build the date with explicit
    # property setters instead — bulletproof across every locale.
    safe_what = what.replace('"', "'")
    script = f'''
    set targetDate to current date
    set year of targetDate to {when.year}
    set month of targetDate to {when.month}
    set day of targetDate to {when.day}
    set hours of targetDate to {when.hour}
    set minutes of targetDate to {when.minute}
    set seconds of targetDate to 0
    tell application "Reminders"
        set newReminder to make new reminder with properties {{name:"{safe_what}", remind me date:targetDate}}
    end tell
    '''
    ok, output = _osascript(script)
    if not ok:
        return f"I couldn't set the reminder: {output}"
    return f"Reminder set for {when.strftime('%A %-I:%M %p')}: {what}."


SKILL = register(
    Skill(
        name="set_reminder",
        description=(
            "Create a reminder in macOS Reminders.app. The planner must resolve any "
            "natural-language time ('tomorrow 9am', 'in 30 minutes') into an ISO 8601 "
            "timestamp before calling this."
        ),
        parameters={
            "type": "object",
            "properties": {
                "what": {"type": "string", "description": "Plain text reminder content."},
                "when_iso": {
                    "type": "string",
                    "description": "ISO 8601 datetime, local TZ. Example: 2026-05-05T15:30:00.",
                },
            },
            "required": ["what", "when_iso"],
        },
        run=run,
        destructive=False,
        tags=["os", "reminders"],
    )
)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--what", required=True)
    p.add_argument("--when-iso", required=True, dest="when_iso")
    a = p.parse_args()
    print(run({"what": a.what, "when_iso": a.when_iso}))
