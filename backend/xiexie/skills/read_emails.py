"""read_emails — list recent unread emails (V1 reads from the demo inbox).

Returns a short plain-English summary the planner can either speak directly
or pipe into ``analyze_email`` if anything looks suspicious.

The "scam-shield triage" is intentionally cheap and rule-based here so the
demo always flags the prepared phishing message:
- SPF/DKIM/DMARC failure in the headers
- Sender domain typosquats a known wiki account (we read ``accounts.md``)
- Subject screams urgency in ALL-CAPS
"""

from __future__ import annotations

import re
from typing import Any

from ..memory import Wiki
from . import _inbox
from .registry import Skill, register

URGENT_RE = re.compile(r"\b(urgent|immediately|expires?\s+today|verify\s+now|act\s+now)\b", re.I)


def _known_account_domains() -> set[str]:
    wiki = Wiki()
    page = wiki.get("accounts")
    if not page:
        return set()
    # Very cheap extraction: grab tokens that look like domains.
    domains = set(re.findall(r"\b[a-z0-9][a-z0-9\-]*\.[a-z]{2,}\b", page.body, re.I))
    return {d.lower() for d in domains}


def _is_typosquat(domain: str, known: set[str]) -> bool:
    """Tiny Levenshtein-ish heuristic: shared root, slight edit distance."""
    d = domain.lower()
    for k in known:
        if d == k:
            return False
        # share at least the first 4 chars but differ slightly
        if len(d) >= 4 and len(k) >= 4 and d[:4] == k[:4] and d != k:
            return True
        # contains an extra letter pattern (aetnna vs aetna)
        compact_d = re.sub(r"(.)\1+", r"\1", d)
        compact_k = re.sub(r"(.)\1+", r"\1", k)
        if compact_d != d and compact_d == compact_k:
            return True
    return False


def _suspicion_signals(msg: dict[str, Any], known_domains: set[str]) -> list[str]:
    signals: list[str] = []
    headers = msg.get("headers", {})
    auth = (headers.get("Authentication-Results") or "").lower()
    if "spf=fail" in auth or "dmarc=fail" in auth:
        signals.append("SPF/DKIM/DMARC failure")

    sender_domain = (msg.get("from", {}).get("domain") or "").lower()
    if sender_domain and _is_typosquat(sender_domain, known_domains):
        signals.append(f"sender domain {sender_domain!r} looks like a typosquat")

    subject = msg.get("subject") or ""
    if URGENT_RE.search(subject):
        signals.append("urgent / scare-tactic subject line")

    body = msg.get("body_text") or ""
    if URGENT_RE.search(body) and "social security" in body.lower():
        signals.append("asks for Social Security Number")

    return signals


def run(args: dict[str, Any]) -> str:
    limit = int(args.get("limit", 5))
    unread_only = bool(args.get("unread_only", True))
    msgs = _inbox.all_messages(unread_only=unread_only)[:limit]
    if not msgs:
        return "Your inbox is quiet. Nothing new to read."

    known = _known_account_domains()
    lines: list[str] = []
    flagged: list[str] = []

    for m in msgs:
        line = f"- {_inbox.short_summary(m)}"
        signals = _suspicion_signals(m, known)
        if signals:
            line += "  ⚠ unusual"
            flagged.append(m["id"])
        lines.append(line)

    summary = f"You have {len(msgs)} unread email" + ("s" if len(msgs) != 1 else "") + ":\n" + "\n".join(lines)

    if flagged:
        summary += (
            f"\n\nOne ({flagged[0]}) looks unusual to me — want me to take a closer look?"
        )

    return summary


SKILL = register(
    Skill(
        name="read_emails",
        description=(
            "List recent unread emails with a short summary. Flags any message that looks "
            "suspicious based on cheap header + sender + subject heuristics so the planner "
            "can offer to run `analyze_email` on it."
        ),
        parameters={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 5},
                "unread_only": {"type": "boolean", "default": True},
            },
        },
        run=run,
        destructive=False,
        tags=["email", "scam-shield"],
    )
)


if __name__ == "__main__":
    print(run({}))
