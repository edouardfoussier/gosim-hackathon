"""Skill stubs — registered but not yet implemented.

These exist so the planner can *route* to them today and so the wiki linter
can already see them in the tool surface. Each ``run`` returns the
on-brand fallback message and logs the ask to ``data/raw/unhandled_asks.md``.

Replace each ``run`` with a real implementation as we build (see CLAUDE.md
§3 V1 skills + the J1/J2 plan).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from ..config import config
from .registry import Skill, register

UNHANDLED_PATH = config.RAW_DIR / "unhandled_asks.md"


def _log_unhandled(skill: str, args: dict[str, Any]) -> None:
    UNHANDLED_PATH.parent.mkdir(parents=True, exist_ok=True)
    block = (
        f"\n## {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}\n"
        f"- skill_attempted: {skill}\n"
        f"- args: {args}\n"
        f"- response: stub fallback (\"taking a note so I can learn\")\n"
    )
    with UNHANDLED_PATH.open("a", encoding="utf-8") as fh:
        fh.write(block)


def _stub_run(skill_name: str, friendly: str):
    def _run(args: dict[str, Any]) -> str:
        _log_unhandled(skill_name, args)
        return friendly

    return _run


# ── read_emails ───────────────────────────────────────────────────────────
register(
    Skill(
        name="read_emails",
        description="Read recent emails aloud (Mail.app or Gmail). Filter by sender, urgency, or 'today'.",
        parameters={
            "type": "object",
            "properties": {
                "filter": {"type": "string", "description": "Optional: 'today', 'from Lisa', 'urgent', etc."},
                "limit": {"type": "integer", "default": 5},
            },
        },
        run=_stub_run(
            "read_emails",
            "I'll read your emails for you in a moment — I'm still learning that one. Adding it to my list.",
        ),
        tags=["email", "stub"],
    )
)


# ── zoom_text ─────────────────────────────────────────────────────────────
register(
    Skill(
        name="zoom_text",
        description="Increase text size on the active app or system-wide (macOS zoom).",
        parameters={
            "type": "object",
            "properties": {
                "amount": {"type": "string", "enum": ["smaller", "normal", "bigger", "much bigger"], "default": "bigger"},
            },
        },
        run=_stub_run(
            "zoom_text",
            "I'll make things bigger for you — give me a second, this is one I'm still learning.",
        ),
        tags=["accessibility", "stub"],
    )
)


# ── login_site ────────────────────────────────────────────────────────────
register(
    Skill(
        name="login_site",
        description="Open a website and log in using credentials stored in the Keychain (referenced from wiki/accounts.md).",
        parameters={
            "type": "object",
            "properties": {
                "site": {"type": "string", "description": "Site name as in wiki/accounts.md (e.g. 'aetna', 'pge')."},
            },
            "required": ["site"],
        },
        run=_stub_run(
            "login_site",
            "I'll log you in once I've finished learning that — taking a note for now.",
        ),
        destructive=True,
        tags=["browser", "auth", "stub"],
    )
)


# ── daily_brief ───────────────────────────────────────────────────────────
register(
    Skill(
        name="daily_brief",
        description="Read the user a short morning briefing: emails, calendar, recurring tasks, weather.",
        parameters={"type": "object", "properties": {}},
        run=_stub_run(
            "daily_brief",
            "Good morning! Your full briefing is one I'm still learning — I'll have it ready soon.",
        ),
        tags=["composite", "stub"],
    )
)
