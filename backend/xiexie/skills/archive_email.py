"""archive_email — move a single message out of the inbox.

Source-agnostic: ``_inbox.update_message`` dispatches to the configured
``MAIL_SOURCE`` (``mailapp`` → AppleScript ``move ... to mailbox "Archive"``;
``demo`` → JSON fixture mutation), so the same skill body covers both
the deterministic stage demo and the real Mail.app run-through.
"""

from __future__ import annotations

from typing import Any

from . import _inbox
from .registry import Skill, register


def run(args: dict[str, Any]) -> str:
    message_id = str(args.get("message_id", "")).strip()
    if not message_id:
        return "Which email should I archive? I need its id."

    # Works for both sources: the JSON fixture mutates in place, the
    # Mail.app router translates ``archived=True`` into a real
    # AppleScript move-to-Archive (and ignores ``read=True`` for safety).
    msg = _inbox.update_message(message_id, archived=True, read=True)
    if msg is None:
        return f"I couldn't find an email with id {message_id!r}."
    sender = msg.get("from", {}).get("name") or msg.get("from", {}).get("address") or "(unknown)"
    return f"Archived the email from {sender}. It's out of your inbox."


SKILL = register(
    Skill(
        name="archive_email",
        description="Move a single email to the archive (so it leaves the inbox view but can be retrieved later).",
        parameters={
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "The id of the email to archive."}
            },
            "required": ["message_id"],
        },
        run=run,
        destructive=True,  # acts on user's data → confirmation gate triggers
        tags=["email", "scam-shield"],
    )
)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--id", required=True)
    a = p.parse_args()
    print(run({"message_id": a.id}))
