"""analyze_email — the flagship composite skill.

Composes ``check_url`` (per link), ``search_scam_intel`` (per pattern), the
wiki ``scam_alerts.md`` knowledge base, and a final GLM reasoning call into
a single graded verdict the agent can speak in plain English.

Output (as the planner sees it via the tool result text):

    VERDICT: phishing  (confidence: high)
    SIGNS:
      1. Sender domain `aetnna-secure.com` typosquats `aetna.com`.
      2. Link redirects 4 hops, lands on netlify.app, asks for SSN.
      3. Pattern matches FTC alert from 2026-04-28.
    RECOMMENDED ACTION:
      - Don't click. Don't pay.
      - Archive the email.
      - Tell Lisa.

Confidence ladder mirrors the risk-log gradation:
- ``safe``        → no signals, no action
- ``unclear``     → call your bank / your daughter to double-check
- ``suspicious``  → don't click; the agent can archive
- ``phishing``    → don't act; archive + alert family
"""

from __future__ import annotations

import json
from typing import Any

from ..external import email_rep
from ..llm import get_provider
from ..memory import Wiki
from . import _inbox, check_url as _check_url, search_scam_intel as _intel
from .registry import Skill, register

ANALYZE_SYSTEM = """\
You are Xiexie's email forensics agent. The user is a senior. You receive:
- the email object (headers, sender, subject, body, links)
- the structured report from `check_url` for each link in the email
  (now enriched with Google Safe Browsing + urlscan.io history when configured)
- the EmailRep.io reputation for the sender address
- 3 web-search hits from `search_scam_intel`
- the user's wiki/scam_alerts.md (known active patterns)
- the user's wiki/accounts.md (their *real* accounts, for sender comparison)

Return STRICT JSON with this shape and nothing else:

{
  "verdict": "safe" | "unclear" | "suspicious" | "phishing",
  "confidence": "low" | "medium" | "high",
  "signs": [
    "Plain English short sentence — one sign per item, maximum 3."
  ],
  "recommended_actions": [
    "Plain English imperative — e.g. 'Don't click.', 'Archive it.', 'Tell Lisa.'"
  ],
  "speak_aloud": "One paragraph the agent reads to the user. Warm, calm, no jargon. End with a question if action is needed."
}

Hard rules:
- Be calibrated. If signals are weak, return 'unclear' with low confidence —
  never assert 'phishing' below 'high' confidence.
- Speak as a kind, calm grandchild — never alarmist. Never 'YOU MUST'.
- If the email is from a real known sender (matches accounts.md exactly),
  default to 'safe' unless the body or links contradict that.
- Acronyms are forbidden in `speak_aloud`. Say 'Social Security Number' once
  and then 'that number'.
"""


def _build_user_prompt(message: dict[str, Any], url_reports: list[dict[str, Any]],
                       intel: list[dict[str, str]], sender_rep: dict[str, Any],
                       wiki: Wiki) -> str:
    parts: list[str] = []
    parts.append("## EMAIL\n```json\n" + json.dumps(message, indent=2) + "\n```")
    if url_reports:
        parts.append("## URL FORENSICS\n```json\n" + json.dumps(url_reports, indent=2) + "\n```")
    if sender_rep.get("available"):
        parts.append("## SENDER REPUTATION (EmailRep.io)\n```json\n"
                     + json.dumps(sender_rep, indent=2) + "\n```")
    if intel:
        parts.append("## WEB SCAM INTEL\n```json\n" + json.dumps(intel, indent=2) + "\n```")

    scam_page = wiki.get("scam_alerts")
    if scam_page:
        parts.append("## KNOWN SCAM PATTERNS (wiki/scam_alerts.md)\n" + scam_page.body[:3000])

    accounts_page = wiki.get("accounts")
    if accounts_page:
        parts.append("## USER'S REAL ACCOUNTS (wiki/accounts.md, for comparison)\n"
                     + accounts_page.body[:1500])
    return "\n\n".join(parts)


def analyze(message: dict[str, Any]) -> dict[str, Any]:
    """Pure function — no I/O on the message — returns the verdict dict."""
    # 1. URL forensics for each link (enriched with GSB + urlscan inside check_url)
    url_reports: list[dict[str, Any]] = []
    for link in (message.get("links") or [])[:5]:
        url = link.get("url")
        if url:
            url_reports.append(_check_url.fetch_struct(url))

    # 2. EmailRep on the sender
    sender_addr = message.get("from", {}).get("address") or ""
    sender_rep = email_rep.lookup(sender_addr) if sender_addr else {"available": False}

    # 3. One scam-intel search keyed by sender brand + 'phishing'
    sender_brand = (message.get("from", {}).get("name") or message.get("subject") or "").lower()
    pattern_hint = " ".join(sender_brand.split()[:3]) + " phishing"
    intel = _intel.search(pattern_hint)

    # 4. GLM verdict
    wiki = Wiki()
    user_msg = _build_user_prompt(message, url_reports, intel, sender_rep, wiki)
    llm = get_provider()
    resp = llm.chat(
        messages=[
            {"role": "system", "content": ANALYZE_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.1,
        max_tokens=700,
    )

    raw = resp.text.strip()
    # Strip optional ```json fences
    if raw.startswith("```"):
        raw = raw.strip("` \n")
        if raw.lower().startswith("json"):
            raw = raw[4:].lstrip()

    try:
        verdict = json.loads(raw)
    except json.JSONDecodeError:
        verdict = {
            "verdict": "unclear",
            "confidence": "low",
            "signs": ["I couldn't reach a clear conclusion — the model returned malformed output."],
            "recommended_actions": ["Don't click anything; ask someone you trust to look."],
            "speak_aloud": (
                "I'm not sure about this one. The safest thing is to not click "
                "any links and check with someone you trust before acting."
            ),
        }

    verdict["_evidence"] = {
        "url_reports": url_reports,
        "sender_reputation": sender_rep,
        "intel": intel,
        "message_id": message.get("id"),
    }
    return verdict


def run(args: dict[str, Any]) -> str:
    message_id = str(args.get("message_id", "")).strip()
    if not message_id:
        return "Which email should I look at? I need its id."
    message = _inbox.get_message(message_id)
    if message is None:
        return f"I couldn't find an email with id {message_id!r}."

    verdict = analyze(message)

    lines = [
        f"VERDICT: {verdict.get('verdict', 'unclear')}  (confidence: {verdict.get('confidence', 'low')})"
    ]
    if verdict.get("signs"):
        lines.append("SIGNS:")
        for i, sign in enumerate(verdict["signs"], 1):
            lines.append(f"  {i}. {sign}")
    if verdict.get("recommended_actions"):
        lines.append("RECOMMENDED ACTIONS:")
        for action in verdict["recommended_actions"]:
            lines.append(f"  - {action}")
    if verdict.get("speak_aloud"):
        lines.append("")
        lines.append(verdict["speak_aloud"])
    return "\n".join(lines)


SKILL = register(
    Skill(
        name="analyze_email",
        description=(
            "Forensically analyse a single email for scam / phishing risk. Composes "
            "URL sandbox checks, web-grounded scam intelligence, and the user's wiki of "
            "known patterns into a graded verdict (safe / unclear / suspicious / phishing) "
            "with plain-English signs and recommended actions."
        ),
        parameters={
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "The id of the email to analyse (from `read_emails`).",
                }
            },
            "required": ["message_id"],
        },
        run=run,
        destructive=False,
        tags=["scam-shield", "flagship"],
    )
)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--id", required=True)
    a = p.parse_args()
    print(run({"message_id": a.id}))
