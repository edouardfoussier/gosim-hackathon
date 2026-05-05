"""Tiny helper around the demo inbox fixture (``data/demo/inbox.json``).

For V1 the demo inbox is a JSON file we fully control. The functions here
abstract reading + mutating it so swapping to AppleScript Mail later is a
single-file change.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import config

INBOX_PATH = (config.REPO_ROOT / "data" / "demo" / "inbox.json").resolve()


def load() -> dict[str, Any]:
    if not INBOX_PATH.exists():
        return {"owner": "", "messages": []}
    return json.loads(INBOX_PATH.read_text(encoding="utf-8"))


def save(inbox: dict[str, Any]) -> None:
    INBOX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INBOX_PATH.write_text(json.dumps(inbox, indent=2, ensure_ascii=False), encoding="utf-8")


def get_message(message_id: str) -> dict[str, Any] | None:
    for msg in load().get("messages", []):
        if msg.get("id") == message_id:
            return msg
    return None


def all_messages(unread_only: bool = False, archived: bool = False) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = list(load().get("messages", []))
    if unread_only:
        msgs = [m for m in msgs if not m.get("read")]
    if not archived:
        msgs = [m for m in msgs if not m.get("archived")]
    msgs.sort(key=lambda m: m.get("received_at", ""), reverse=True)
    return msgs


def update_message(message_id: str, **patch: Any) -> dict[str, Any] | None:
    inbox = load()
    out: dict[str, Any] | None = None
    for msg in inbox.get("messages", []):
        if msg.get("id") == message_id:
            msg.update(patch)
            out = msg
            break
    if out is not None:
        save(inbox)
    return out


def short_summary(msg: dict[str, Any]) -> str:
    """One-line plain-English summary used by ``read_emails`` reading aloud."""
    sender = msg.get("from", {}).get("name") or msg.get("from", {}).get("address", "unknown")
    subject = (msg.get("subject") or "").strip()
    return f"From {sender}: {subject}"
