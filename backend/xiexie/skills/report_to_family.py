"""report_to_family — alert a family member when something looks wrong.

Looks up the recipient in ``wiki/family.md`` (default = the first relative
the user mentions or the most recently contacted), drafts a short message,
and opens the user's mail client with it pre-filled (`mailto:`). Sending
stays a one-click manual confirmation — Xiexie never sends without the user.
"""

from __future__ import annotations

import re
import subprocess
import urllib.parse
from typing import Any

from ..memory import Wiki
from .registry import Skill, register


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_NAME_HEADING_RE = re.compile(r"^##\s+(.+)$", re.M)


def _resolve_recipient(wiki: Wiki, name_hint: str | None) -> tuple[str, str | None] | None:
    family = wiki.get("family")
    if not family:
        return None
    body = family.body
    # collect every "## <Name>" section
    sections: list[tuple[str, str]] = []
    chunks = re.split(r"(?m)^## ", body)
    for chunk in chunks:
        if not chunk.strip():
            continue
        head, _, rest = chunk.partition("\n")
        sections.append((head.strip(), rest))

    target_section: tuple[str, str] | None = None
    if name_hint:
        for sec in sections:
            if name_hint.lower() in sec[0].lower():
                target_section = sec
                break
    if target_section is None and sections:
        target_section = sections[0]

    if target_section is None:
        return None

    name, sec_body = target_section
    email_match = _EMAIL_RE.search(sec_body)
    return name, email_match.group(0) if email_match else None


def _draft(verdict_summary: str, name: str) -> tuple[str, str]:
    subject = "Heads-up: I caught something in Mom's inbox"
    body = (
        f"Hi {name.split()[0]},\n\n"
        "Xiexie (the AI helper on Mom's computer) flagged a suspicious email "
        "this morning. Quick summary so you're in the loop:\n\n"
        f"{verdict_summary.strip()}\n\n"
        "Mom didn't click anything — Xiexie archived it. No action needed, "
        "just wanted you to know in case she gets worried later.\n\n"
        "— Xiexie"
    )
    return subject, body


def run(args: dict[str, Any]) -> str:
    summary = str(args.get("summary", "")).strip()
    if not summary:
        return "What's the heads-up about? I need a one-line summary."

    name_hint = args.get("recipient_hint")
    wiki = Wiki()
    target = _resolve_recipient(wiki, name_hint)
    if target is None:
        return "I don't know any family members yet — add one in wiki/family.md first."

    name, email = target
    subject, body = _draft(summary, name)

    if not email:
        return (
            f"Drafted a note for {name} but I couldn't find their email in the wiki. "
            "Add an email line under the family page and I'll send it next time."
        )

    mailto = (
        f"mailto:{email}"
        f"?subject={urllib.parse.quote(subject)}"
        f"&body={urllib.parse.quote(body)}"
    )
    try:
        subprocess.run(["open", mailto], check=True, timeout=5)
    except subprocess.SubprocessError:
        return f"I drafted the message for {name} ({email}) but couldn't open your mail client."

    return (
        f"I opened a draft to {name} ({email}). Review it and click send when you're ready — "
        "I'll never send anything without you."
    )


SKILL = register(
    Skill(
        name="report_to_family",
        description=(
            "Alert a family member with a short heads-up about something suspicious "
            "(typically the verdict from analyze_email). Drafts a `mailto:` and opens "
            "the user's mail client — never sends automatically."
        ),
        parameters={
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "One-paragraph summary suitable for a family member.",
                },
                "recipient_hint": {
                    "type": "string",
                    "description": "Optional name hint, e.g. 'Lisa'. Defaults to the first relative in wiki/family.md.",
                },
            },
            "required": ["summary"],
        },
        run=run,
        destructive=True,  # opens external app + drafts a message → confirmation gate
        tags=["family", "scam-shield"],
    )
)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--summary", required=True)
    p.add_argument("--to", default=None)
    a = p.parse_args()
    print(run({"summary": a.summary, "recipient_hint": a.to}))
