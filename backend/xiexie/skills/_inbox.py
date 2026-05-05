"""Tiny helper around the user's inbox — JSON fixture or live Mail.app.

V1 had a single source: ``data/demo/inbox.json``. The Mail.app pivot keeps
that fixture as a deterministic fallback for stage demos and adds a live
AppleScript-backed source for the recorded video, both routed through a
thin ``configured_source()`` switch read from ``$MAIL_SOURCE``:

- ``MAIL_SOURCE=mailapp`` (default) — read the user's real inbox via
  ``_mail_app.list_unread()``. Mutations only support ``archived=True``.
- ``MAIL_SOURCE=demo``               — read / mutate ``data/demo/inbox.json``
  (the original fixture path; full mutability is preserved).

Both sources MUST emit messages in the same dict shape (see
``read_emails`` for the schema) so downstream skills (``analyze_email``,
``archive_email``) are completely source-agnostic.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from ..config import config
from . import _mail_app

logger = logging.getLogger("xiexie.inbox")

INBOX_PATH = (config.REPO_ROOT / "data" / "demo" / "inbox.json").resolve()

# Mutations we accept on the live Mail.app source. Anything else is a no-op
# with a warning — the JSON fixture stays free-form for `read=True`,
# `archived=True`, etc., but Mail.app only exposes `archive()`.
_MAILAPP_ALLOWED_PATCHES: frozenset[str] = frozenset({"archived"})


# ─── source selection ────────────────────────────────────────────────────
def configured_source() -> str:
    """Read ``$MAIL_SOURCE`` (default ``"mailapp"``).

    Resolved per-call rather than at import time so tests can flip the env
    var with ``monkeypatch.setenv`` without re-importing the module.
    """
    raw = (os.getenv("MAIL_SOURCE", "mailapp") or "").strip().lower()
    if raw in {"mailapp", "demo"}:
        return raw
    logger.warning("unknown MAIL_SOURCE=%r, falling back to 'demo'", raw)
    return "demo"


# ─── fixture-source helpers (kept verbatim from V1) ──────────────────────
def load() -> dict[str, Any]:
    if not INBOX_PATH.exists():
        return {"owner": "", "messages": []}
    return json.loads(INBOX_PATH.read_text(encoding="utf-8"))


def save(inbox: dict[str, Any]) -> None:
    INBOX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INBOX_PATH.write_text(json.dumps(inbox, indent=2, ensure_ascii=False), encoding="utf-8")


def _filter_messages(
    msgs: list[dict[str, Any]],
    *,
    unread_only: bool,
    archived: bool,
) -> list[dict[str, Any]]:
    if unread_only:
        msgs = [m for m in msgs if not m.get("read")]
    if not archived:
        msgs = [m for m in msgs if not m.get("archived")]
    msgs.sort(key=lambda m: m.get("received_at", ""), reverse=True)
    return msgs


# ─── public API — dispatched by ``configured_source()`` ──────────────────
def all_messages(unread_only: bool = False, archived: bool = False) -> list[dict[str, Any]]:
    """Return inbox messages, filtered + sorted (newest first).

    The Mail.app source only ever ships unread messages (we filter at the
    AppleScript level for speed), so ``archived=True`` is moot there — the
    moment a message is archived it stops being in the inbox query.
    """
    if configured_source() == "mailapp":
        msgs = list(_mail_app.list_unread())
        return _filter_messages(msgs, unread_only=unread_only, archived=archived)

    msgs = list(load().get("messages", []))
    return _filter_messages(msgs, unread_only=unread_only, archived=archived)


def get_message(message_id: str) -> dict[str, Any] | None:
    """Look up a single message by id, dispatched to the right source."""
    if configured_source() == "mailapp":
        return _mail_app.find_one(message_id)

    for msg in load().get("messages", []):
        if msg.get("id") == message_id:
            return msg
    return None


def update_message(message_id: str, **patch: Any) -> dict[str, Any] | None:
    """Apply a patch to a message.

    For the demo fixture we mutate the JSON freely. For the live Mail.app
    source we only honour ``archived=True`` (which translates to a "move
    to Archive mailbox" AppleScript call); other patches are dropped with
    a warning so we never silently lie about mutating real user data.
    """
    if configured_source() == "mailapp":
        unsupported = [k for k in patch if k not in _MAILAPP_ALLOWED_PATCHES]
        if unsupported:
            logger.warning(
                "ignoring unsupported Mail.app patch keys: %s (only %s are wired)",
                unsupported,
                sorted(_MAILAPP_ALLOWED_PATCHES),
            )
        if patch.get("archived") is not True:
            return get_message(message_id)
        msg = get_message(message_id)
        if msg is None:
            return None
        ok = _mail_app.archive(message_id)
        if not ok:
            return None
        # Reflect the post-mutation state back to the caller. The message
        # is no longer in the inbox query; we hand back the snapshot we
        # already had with the archived flag set so callers can build a
        # confirmation sentence ("Archived from Lisa…") without an extra
        # round-trip.
        return {**msg, "archived": True, "read": True}

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
