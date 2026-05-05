"""open_app — launch a macOS app by name.

Skill #1 of V1. Trivial wrapper around ``open -a "<App>"``. Doubles as the
template every other skill follows: register a ``Skill`` dataclass with a
JSON-schema and a ``run`` callable.
"""

from __future__ import annotations

import subprocess
from typing import Any

from .registry import Skill, register

# Common voice → app aliases. Margaret says "Whatsapp" not "WhatsApp"; Xiexie
# normalises before calling `open -a`.
ALIASES = {
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "browser": "Google Chrome",
    "whatsapp": "WhatsApp",
    "wa": "WhatsApp",
    "messages": "Messages",
    "imessage": "Messages",
    "mail": "Mail",
    "email": "Mail",
    "calendar": "Calendar",
    "reminders": "Reminders",
    "photos": "Photos",
    "facetime": "FaceTime",
    "zoom": "zoom.us",
    "safari": "Safari",
    "preview": "Preview",
    "system settings": "System Settings",
}


def _normalise(name: str) -> str:
    key = name.strip().lower()
    return ALIASES.get(key, name.strip())


def run(args: dict[str, Any]) -> str:
    raw = str(args.get("name", "")).strip()
    if not raw:
        return "I need an app name."
    app = _normalise(raw)
    try:
        subprocess.run(["open", "-a", app], check=True, timeout=5)
        return f"Opened {app}."
    except subprocess.CalledProcessError:
        return f"I couldn't find an app called {app!r}. Want me to try a search instead?"
    except subprocess.TimeoutExpired:
        return f"Opening {app} took too long. It might be already loading."


SKILL = register(
    Skill(
        name="open_app",
        description=(
            "Open (launch or bring to front) a macOS application by name or common alias. "
            "Use for any voice request like 'open WhatsApp', 'launch Chrome', 'show me my calendar'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "App name as the user said it (e.g. 'Whatsapp', 'Chrome', 'mail').",
                }
            },
            "required": ["name"],
        },
        run=run,
        destructive=False,
        tags=["os", "launcher"],
    )
)


# CLI for quick testing: `uv run python -m xiexie.skills.open_app --app "Mail"`
if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--app", required=True)
    a = p.parse_args()
    print(run({"name": a.app}))
