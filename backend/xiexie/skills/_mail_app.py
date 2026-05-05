"""AppleScript-backed reader for the user's real macOS Mail.app inbox.

This is the "live" cousin of the ``data/demo/inbox.json`` fixture handled in
``_inbox.py``. The two sources speak the same dict shape (see
``_inbox`` docstring + read_emails for the schema), so downstream skills
(``analyze_email``, ``archive_email``) don't care which one fed them.

Design notes:

- We shell out to ``osascript`` per call (same pattern as ``set_reminder``
  and ``zoom_text``). One-shot scripts are easier to reason about and
  fail-isolate than a long-lived Mail.app session.

- AppleScript's record/list serialisation is painful to parse. We sidestep
  it by emitting plain text with ASCII control-character separators —
  ``\\x1f`` between fields, ``\\x1e`` between messages — neither of which
  ever appears in a legitimate email. Parsing in Python is then a single
  ``str.split``.

- Dates are formatted to ISO 8601 inside AppleScript so we don't depend on
  the user's locale ("Tuesday, May 5, 2026 at 22:31:00" is the default
  AppleScript stringification on this Mac and a parsing nightmare on FR /
  ZH locales).

- Headers we care about (Return-Path / Received-SPF / Authentication-Results)
  are pulled from the single ``all headers`` blob with simple regex passes;
  older Mail.app messages may not expose every header so callers MUST
  treat the values as ``str | None``.

- Results are cached for 5 s in-process. A single user phrase ("did I get
  any new emails? open the suspicious one") can fire 3–4 inbox lookups
  back-to-back; without caching every turn would spin up four AppleScript
  subprocesses.

- Every public entry point catches errors and returns a sentinel
  (``[]`` / ``False`` / ``None``) rather than raising. That keeps the
  voice loop alive when Mail.app is quit, denied permission, or pushing
  back on a Migration Assistant pane.
"""

from __future__ import annotations

import logging
import re
import subprocess
import threading
import time
from typing import Any

logger = logging.getLogger("xiexie.mail_app")

# ─── delimiters used by the AppleScript output format ────────────────────
# These are ASCII control characters that should never legitimately appear
# in a sender, subject, header, or body. If they do (a malicious sender
# might try), the parser drops the malformed message rather than crashing.
_FS = "\x1f"  # field separator (between fields of a single message)
_RS = "\x1e"  # record separator (between messages)


# ─── tiny TTL cache so a single user phrase fires one AppleScript call ───
_CACHE_TTL_S = 5.0
_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, Any]] = {}


def _cache_get(key: str) -> Any | None:
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        ts, value = entry
        if (time.monotonic() - ts) > _CACHE_TTL_S:
            _cache.pop(key, None)
            return None
        return value


def _cache_set(key: str, value: Any) -> None:
    with _cache_lock:
        _cache[key] = (time.monotonic(), value)


def invalidate_cache() -> None:
    """Drop every cached read. Called after an archive mutation."""
    with _cache_lock:
        _cache.clear()


# ─── osascript helper (mirrors set_reminder.py / zoom_text.py shape) ─────
def _osascript(script: str, *, timeout: int = 8) -> tuple[bool, str]:
    """Run ``osascript -e SCRIPT``. Returns ``(ok, output_or_error)``."""
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"osascript timed out after {timeout}s"
    except FileNotFoundError:
        return False, "osascript not available (not on macOS?)"
    return proc.returncode == 0, (proc.stdout or proc.stderr).strip()


# ─── Mail.app readiness ──────────────────────────────────────────────────
def _ensure_mail_running(grace_s: float = 5.0) -> bool:
    """Make sure Mail.app is running; launch it (silently) if not.

    AppleScript's ``tell application "Mail" to launch`` is the polite form
    that doesn't bring Mail to the foreground — perfect for a backend
    reading the inbox without stealing focus from the user's browser.
    """
    ok, out = _osascript(
        'tell application "System Events" to (name of processes) contains "Mail"',
        timeout=4,
    )
    if ok and out.strip() == "true":
        return True
    ok, _ = _osascript('tell application "Mail" to launch', timeout=4)
    if not ok:
        return False
    # Mail.app needs a moment after launch before its scripting dictionary
    # is fully responsive. We poll instead of sleeping the full grace.
    deadline = time.monotonic() + grace_s
    while time.monotonic() < deadline:
        ok, out = _osascript(
            'tell application "System Events" to (name of processes) contains "Mail"',
            timeout=2,
        )
        if ok and out.strip() == "true":
            return True
        time.sleep(0.25)
    return False


# ─── AppleScript template for listing unread inbox messages ──────────────
# We pull the most-recent ``LIMIT`` unread messages of *every* account's
# inbox (Mail.app's top-level ``inbox`` is a unified inbox across accounts).
# Field order MUST match ``_FIELD_NAMES`` below.
_LIST_UNREAD_SCRIPT = """
on iso8601(d)
    set y to year of d as integer
    set m to (month of d as integer)
    set dd to day of d as integer
    set hh to hours of d as integer
    set mn to minutes of d as integer
    set sc to seconds of d as integer
    set yy to (y as string)
    set mm to text -2 thru -1 of ("0" & (m as string))
    set dy to text -2 thru -1 of ("0" & (dd as string))
    set hr to text -2 thru -1 of ("0" & (hh as string))
    set mi to text -2 thru -1 of ("0" & (mn as string))
    set ss to text -2 thru -1 of ("0" & (sc as string))
    return yy & "-" & mm & "-" & dy & "T" & hr & ":" & mi & ":" & ss
end iso8601

set FS to (ASCII character 31)
set RS to (ASCII character 30)
set out to ""

tell application "Mail"
    set theMessages to (messages of inbox whose read status is false)
    set msgCount to count of theMessages
    set startIdx to msgCount - __LIMIT__ + 1
    if startIdx < 1 then set startIdx to 1
    repeat with i from msgCount to startIdx by -1
        try
            set theMessage to item i of theMessages
            set msgId to message id of theMessage
            set msgSender to sender of theMessage
            set msgSubject to subject of theMessage
            set msgDateRaw to date received of theMessage
            set msgDate to my iso8601(msgDateRaw)
            set msgRead to (read status of theMessage) as string
            set msgHeaders to all headers of theMessage
            set msgContent to content of theMessage
            try
                set msgTo to address of to recipient 1 of theMessage
            on error
                set msgTo to ""
            end try
            set out to out & msgId & FS & msgSender & FS & msgSubject & FS & msgDate & FS & msgRead & FS & msgTo & FS & msgHeaders & FS & msgContent & RS
        end try
    end repeat
end tell
return out
"""

# Order MUST match the AppleScript output above.
_FIELD_NAMES = (
    "id",
    "sender",
    "subject",
    "date_iso",
    "read",
    "to",
    "headers_blob",
    "body_text",
)


# ─── parsing helpers ─────────────────────────────────────────────────────
_SENDER_RE = re.compile(r"^\s*(?:\"?(?P<name>[^\"<]*?)\"?\s*)?<(?P<addr>[^>]+)>\s*$")
_LINK_RE = re.compile(r"https?://[^\s<>'\"\)\]]+", re.IGNORECASE)


def _parse_sender(raw: str) -> dict[str, str]:
    """``"Lisa <lisa@example.co.uk>"`` → ``{"name", "address", "domain"}``."""
    raw = (raw or "").strip()
    m = _SENDER_RE.match(raw)
    if m:
        name = (m.group("name") or "").strip().strip('"')
        addr = m.group("addr").strip()
    elif "@" in raw and "<" not in raw:
        name = ""
        addr = raw.strip()
    else:
        return {"name": raw, "address": "", "domain": ""}
    domain = addr.rsplit("@", 1)[-1].lower() if "@" in addr else ""
    return {"name": name, "address": addr, "domain": domain}


def _parse_one_header(blob: str, name: str) -> str | None:
    """Pull the first occurrence of ``Header-Name:`` from a raw header blob.

    Header values can wrap to a continuation line (RFC 5322 §2.2.3) starting
    with whitespace. We collapse that by joining continuation lines onto
    the first one. Returns ``None`` when the header isn't present.
    """
    if not blob:
        return None
    pattern = rf"^{re.escape(name)}\s*:\s*(.+(?:\n[ \t].+)*)"
    m = re.search(pattern, blob, flags=re.IGNORECASE | re.MULTILINE)
    if not m:
        return None
    value = re.sub(r"\n[ \t]+", " ", m.group(1)).strip()
    return value or None


def _extract_headers(blob: str) -> dict[str, str | None]:
    return {
        "Return-Path": _parse_one_header(blob, "Return-Path"),
        "Received-SPF": _parse_one_header(blob, "Received-SPF"),
        "Authentication-Results": _parse_one_header(blob, "Authentication-Results"),
    }


def _extract_links(body: str) -> list[dict[str, str]]:
    """Naive https?:// extraction. Good enough for scam-shield triage."""
    if not body:
        return []
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for url in _LINK_RE.findall(body):
        url = url.rstrip(".,);:!?")
        if url in seen:
            continue
        seen.add(url)
        out.append({"text": url, "url": url})
    return out


def _msg_id_normalise(raw: str) -> str:
    """Mail.app's ``message id`` returns the bare RFC 2822 value (no <>)."""
    s = (raw or "").strip()
    if s.startswith("<") and s.endswith(">"):
        return s[1:-1]
    return s


def _parse_record(record: str) -> dict[str, Any] | None:
    """Turn one ``\\x1f``-delimited message string into the canonical dict."""
    fields = record.split(_FS)
    if len(fields) < len(_FIELD_NAMES):
        logger.debug("dropping malformed mail record (got %d fields)", len(fields))
        return None
    raw = dict(zip(_FIELD_NAMES, fields))
    sender = _parse_sender(raw["sender"])
    headers = _extract_headers(raw["headers_blob"])
    body = raw["body_text"]
    return {
        "id": _msg_id_normalise(raw["id"]),
        "from": sender,
        "to": [raw["to"]] if raw["to"] else [],
        "subject": raw["subject"].strip(),
        "received_at": raw["date_iso"].strip(),
        "read": raw["read"].strip().lower() == "true",
        "archived": False,  # an archived message wouldn't be in inbox anymore
        "headers": headers,
        "body_text": body,
        "links": _extract_links(body),
    }


# ─── public API ──────────────────────────────────────────────────────────
def list_unread(limit: int = 10) -> list[dict[str, Any]]:
    """Return up to ``limit`` recent unread inbox messages, newest-first.

    On any failure (Mail.app unreachable, AppleScript error, no permission),
    returns ``[]`` and logs a single warning. Callers can detect the
    "unavailable" state by combining an empty return with the log line —
    or by calling :func:`status` for a structured probe.
    """
    cache_key = f"list_unread:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    if not _ensure_mail_running():
        logger.warning("Mail.app not running and could not be launched")
        _cache_set(cache_key, [])
        return []

    script = _LIST_UNREAD_SCRIPT.replace("__LIMIT__", str(int(limit)))
    ok, out = _osascript(script, timeout=10)
    if not ok:
        logger.warning("AppleScript list_unread failed: %s", out[:200])
        _cache_set(cache_key, [])
        return []

    if not out.strip():
        _cache_set(cache_key, [])
        return []

    messages: list[dict[str, Any]] = []
    for record in out.split(_RS):
        record = record.strip("\n")
        if not record:
            continue
        parsed = _parse_record(record)
        if parsed is not None:
            messages.append(parsed)

    _cache_set(cache_key, messages)
    return messages


def find_one(message_id: str) -> dict[str, Any] | None:
    """Look up a single inbox message by its RFC 2822 Message-ID.

    Currently sourced from the cached unread list — sufficient for the
    Scam Shield flow where ``analyze_email`` always follows ``read_emails``
    on the same unread message. If a caller passes an id we haven't seen,
    we widen the lookup to a fresh ``list_unread(50)`` before giving up.
    """
    if not message_id:
        return None
    target = _msg_id_normalise(message_id)

    for m in list_unread(limit=10):
        if m["id"] == target:
            return m

    # Widen the net before bailing — the user might be referencing a message
    # that scrolled past the default limit on a busy inbox.
    for m in list_unread(limit=50):
        if m["id"] == target:
            return m

    return None


def archive(message_id: str) -> bool:
    """Move the message identified by ``message_id`` into the Archive mailbox.

    Returns ``True`` on success, ``False`` otherwise (with a warning log).
    The "Archive" mailbox is per-account on Mail.app; we try the account
    that owns the message first, then fall back to a top-level
    ``mailbox "Archive"`` (some setups have one), and finally give up.
    """
    if not message_id:
        return False
    if not _ensure_mail_running():
        logger.warning("Mail.app not running, cannot archive")
        return False

    target = _msg_id_normalise(message_id)
    safe_id = target.replace("\\", "\\\\").replace('"', '\\"')

    script = f'''
tell application "Mail"
    set foundMsg to missing value
    repeat with m in (messages of inbox)
        try
            if (message id of m) is "{safe_id}" then
                set foundMsg to m
                exit repeat
            end if
        end try
    end repeat
    if foundMsg is missing value then return "not_found"
    set destMb to missing value
    try
        set acc to account of (mailbox of foundMsg)
        set destMb to mailbox "Archive" of acc
    on error
        try
            set destMb to mailbox "Archive"
        on error
            return "no_archive_mailbox"
        end try
    end try
    move foundMsg to destMb
    return "ok"
end tell
'''
    ok, out = _osascript(script, timeout=8)
    invalidate_cache()  # the inbox just changed, drop stale reads
    if not ok:
        logger.warning("AppleScript archive failed: %s", out[:200])
        return False
    if out.strip() != "ok":
        logger.warning("archive returned %r for %r", out, message_id)
        return False
    return True


def status() -> dict[str, Any]:
    """Cheap probe. ``{"available": bool, "error": str | None}``.

    Used by the source-router in ``_inbox`` to decide whether to fall back
    to the demo fixture when ``MAIL_SOURCE=mailapp`` was requested but
    Mail.app refuses to talk.
    """
    if not _ensure_mail_running(grace_s=2.0):
        return {"available": False, "error": "Mail.app not running"}
    ok, out = _osascript(
        'tell application "Mail" to count messages of inbox',
        timeout=4,
    )
    if not ok:
        return {"available": False, "error": out[:200] or "AppleScript error"}
    return {"available": True, "error": None, "inbox_count": out.strip()}


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "status":
        print(json.dumps(status(), indent=2))
    else:
        print(json.dumps(list_unread(limit=5), indent=2, ensure_ascii=False))
