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
import re
from typing import Any

from ..external import email_rep
from ..llm import get_provider
from ..memory import Wiki
from . import _inbox, check_url as _check_url, search_scam_intel as _intel
from .registry import Skill, register

EXPECTED_KEYS: tuple[str, ...] = (
    "verdict",
    "confidence",
    "signs",
    "recommended_actions",
    "speak_aloud",
)
ALLOWED_VERDICTS: tuple[str, ...] = ("safe", "unclear", "suspicious", "phishing")
ALLOWED_CONFIDENCE: tuple[str, ...] = ("low", "medium", "high")
DEFAULT_VERDICT: dict[str, Any] = {
    "verdict": "unclear",
    "confidence": "low",
    "signs": [
        "I couldn't reach a clear conclusion — the model returned malformed output."
    ],
    "recommended_actions": ["Don't click anything; ask someone you trust to look."],
    "speak_aloud": (
        "I'm not sure about this one. The safest thing is to not click "
        "any links and check with someone you trust before acting."
    ),
}

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

What you are NOT looking for (false-positive guard — explicitly tolerate
these patterns; they are not scams on their own):
- Legitimate marketing or newsletter blasts (unsubscribe footer, friendly
  tone, no request for credentials or money). Verdict: 'safe'.
- Emails from a sender whose domain matches an entry in wiki/accounts.md
  exactly, with neutral or transactional language and no sense of urgency.
  Verdict: 'safe'.
- Account notifications (e.g. password change, login from new device,
  shipping update) sent from a domain that exactly matches a wiki/accounts.md
  entry — even when they mention "verify" or "click", as long as the link
  goes back to the same known domain. Verdict: 'safe'.
- Transactional emails — receipts, order confirmations, shipping updates,
  appointment reminders — from a known vendor, with no urgency and no
  request for sensitive information beyond what the user already shared.
  Verdict: 'safe'.
- Personal emails from known family contacts in wiki/family.md (sender
  address or display name matches), even when warm/emotional language could
  superficially look manipulative. Verdict: 'safe'.
- Routine corporate updates (open-enrollment reminders, policy renewals)
  from a sender domain that exactly matches accounts.md, with the link
  pointing back to that same domain. Verdict: 'safe'.
- Two-factor codes / one-time passcodes from a known service. Verdict: 'safe'.

When in doubt between 'safe' and 'unclear', prefer 'unclear' with a sentence
explaining the single ambiguity — never invent risks that aren't in the
evidence above.
"""


_DOMAIN_RE = re.compile(r"\b([a-z0-9][a-z0-9\-]*\.[a-z]{2,}(?:\.[a-z]{2,})?)\b", re.I)


def _levenshtein(a: str, b: str) -> int:
    """Tiny Levenshtein implementation — short strings only (domain labels)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def _compact_doubles(s: str) -> str:
    """Collapse runs of repeated letters: ``aetnna`` → ``aetna``."""
    return re.sub(r"(.)\1+", r"\1", s)


def _split_tld(domain: str) -> tuple[str, str]:
    """Return (root_label, tld) using the rightmost dot. Naive — good enough
    for cousin-detection where we only need a same-TLD comparison.
    """
    domain = domain.lower().strip(".")
    if "." not in domain:
        return domain, ""
    head, _, tld = domain.rpartition(".")
    return head.split(".")[-1], tld


def _wiki_account_domains(wiki: Wiki) -> list[str]:
    """Pull out plausible domain tokens from ``wiki/accounts.md``."""
    page = wiki.get("accounts")
    if not page:
        return []
    found = {m.group(1).lower() for m in _DOMAIN_RE.finditer(page.body)}
    # Drop obvious noise — schemes already stripped by the regex.
    return sorted(found)


def cousin_domain_check(
    sender_domain: str | None,
    known_domains: list[str],
) -> dict[str, Any]:
    """Deterministic DKIM-alignment-ish heuristic.

    Returns a structured dict the LLM consumes as one piece of evidence
    (never the only one). Verdict scale:

    - ``"none"``       — no comparable known domain.
    - ``"safe"``       — exact match against a known domain.
    - ``"cousin"``     — close enough to be suspicious (typosquat-ish).

    Each cousin match records the closest known domain, the matching rule,
    and the edit distance so the LLM can ground its sentence in a specific
    sign instead of hallucinating a generic "looks like a typosquat".
    """
    sd = (sender_domain or "").lower().strip().strip(".")
    if not sd:
        return {
            "sender_domain": "",
            "known_domains_checked": list(known_domains),
            "result": "none",
            "matches": [],
            "rationale": "no sender domain available",
        }
    if not known_domains:
        return {
            "sender_domain": sd,
            "known_domains_checked": [],
            "result": "none",
            "matches": [],
            "rationale": "no known accounts on file",
        }

    # 1. Exact match — short-circuit safe.
    if sd in known_domains:
        return {
            "sender_domain": sd,
            "known_domains_checked": list(known_domains),
            "result": "safe",
            "matches": [{"known": sd, "rule": "exact", "distance": 0}],
            "rationale": "sender domain exactly matches a wiki/accounts.md entry",
        }

    sd_root, sd_tld = _split_tld(sd)
    sd_compact = _compact_doubles(sd_root)

    matches: list[dict[str, Any]] = []
    for known in known_domains:
        if known == sd:
            continue
        k_root, k_tld = _split_tld(known)
        k_compact = _compact_doubles(k_root)
        dist = _levenshtein(sd_root, k_root)

        # 2. Compact-doubles equality (aetnna ↔ aetna).
        if sd_compact == k_compact and sd_root != k_root:
            matches.append(
                {
                    "known": known,
                    "rule": "compact_doubles",
                    "distance": dist,
                    "note": f"{sd_root!r} collapses to {sd_compact!r}, identical to {k_root!r}",
                }
            )
            continue

        # 3. One-edit Levenshtein.
        if dist == 1:
            matches.append(
                {
                    "known": known,
                    "rule": "levenshtein_1",
                    "distance": 1,
                    "note": f"one-character edit away from {known!r}",
                }
            )
            continue

        # 4. Levenshtein 2 with same TLD.
        if dist == 2 and sd_tld == k_tld and sd_tld:
            matches.append(
                {
                    "known": known,
                    "rule": "levenshtein_2_same_tld",
                    "distance": 2,
                    "note": f"two-character edit away from {known!r} with the same .{sd_tld}",
                }
            )
            continue

        # 5. Shared first 4 characters but ≠. Keep last so the more specific
        # rules above win when both fire.
        if len(sd_root) >= 4 and len(k_root) >= 4 and sd_root[:4] == k_root[:4]:
            matches.append(
                {
                    "known": known,
                    "rule": "shared_prefix_4",
                    "distance": dist,
                    "note": f"shares the first 4 characters with {known!r} but the rest differs",
                }
            )

    if matches:
        # Prefer the most specific (lowest distance, then earliest rule index).
        rule_priority = {
            "compact_doubles": 0,
            "levenshtein_1": 1,
            "levenshtein_2_same_tld": 2,
            "shared_prefix_4": 3,
        }
        matches.sort(key=lambda m: (m["distance"], rule_priority.get(m["rule"], 9)))
        return {
            "sender_domain": sd,
            "known_domains_checked": list(known_domains),
            "result": "cousin",
            "matches": matches[:3],
            "rationale": (
                f"sender domain {sd!r} is close to a known account domain "
                f"({matches[0]['known']!r}) by rule {matches[0]['rule']!r}"
            ),
        }

    return {
        "sender_domain": sd,
        "known_domains_checked": list(known_domains),
        "result": "none",
        "matches": [],
        "rationale": "no comparable known domain (not in accounts.md, not a typosquat)",
    }


def _strip_code_fence(raw: str) -> str:
    """Strip a leading ```json fence from an LLM response if present."""
    raw = raw.strip()
    if not raw.startswith("```"):
        return raw
    raw = raw.strip("` \n")
    if raw.lower().startswith("json"):
        raw = raw[4:].lstrip()
    # Some models close with another fence inside the body.
    if raw.endswith("```"):
        raw = raw[:-3].rstrip()
    return raw


def _try_json_repair(raw: str) -> Any | None:
    """Attempt ``json_repair`` parse; lazily imported so the dep is optional.

    Returns the parsed object on success, ``None`` when the library is
    unavailable, the parse fails, or the result is empty. The original
    fall-through to ``DEFAULT_VERDICT`` keeps the skill usable even if
    ``json-repair`` was not installed.
    """
    try:
        from json_repair import loads as _repair_loads  # type: ignore
    except Exception:  # noqa: BLE001 — optional dep
        return None
    try:
        out = _repair_loads(raw)
    except Exception:  # noqa: BLE001
        return None
    # ``json_repair`` returns ``""`` for hopeless inputs.
    if out == "" or out is None:
        return None
    return out


def _unwrap_envelope(obj: Any) -> Any:
    """Unwrap a single layer of common LLM-output envelopes.

    Recognises ``{"verdict": {...}}``, ``{"output": {...}}``, ``{"data": {...}}``
    when the inner dict already carries verdict-shaped keys. Stops after one
    unwrap so a legitimate top-level ``verdict`` field (the literal string
    "phishing") is never mistaken for a wrapper.
    """
    if not isinstance(obj, dict):
        return obj
    for key in ("output", "data", "result"):
        inner = obj.get(key)
        if isinstance(inner, dict) and any(k in inner for k in EXPECTED_KEYS):
            return inner
    inner = obj.get("verdict")
    # Only unwrap when the *inner* dict itself has a verdict key (e.g. nested
    # ``{"verdict": {"verdict": "phishing", ...}}``). A bare string verdict
    # at this level is the legitimate top-level shape.
    if isinstance(inner, dict) and "verdict" in inner:
        return inner
    return obj


def _coerce_str_list(value: Any, *, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        out = [str(item).strip() for item in value if str(item).strip()]
        return out or fallback
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return fallback


def _validate_verdict(obj: Any) -> dict[str, Any]:
    """Coerce the parsed object into the documented schema, filling defaults."""
    if not isinstance(obj, dict):
        return dict(DEFAULT_VERDICT)
    obj = _unwrap_envelope(obj)
    if not isinstance(obj, dict):
        return dict(DEFAULT_VERDICT)

    verdict_label = str(obj.get("verdict", "")).strip().lower()
    if verdict_label not in ALLOWED_VERDICTS:
        verdict_label = DEFAULT_VERDICT["verdict"]

    confidence = str(obj.get("confidence", "")).strip().lower()
    if confidence not in ALLOWED_CONFIDENCE:
        confidence = DEFAULT_VERDICT["confidence"]

    signs = _coerce_str_list(obj.get("signs"), fallback=list(DEFAULT_VERDICT["signs"]))
    actions = _coerce_str_list(
        obj.get("recommended_actions"),
        fallback=list(DEFAULT_VERDICT["recommended_actions"]),
    )

    speak = obj.get("speak_aloud")
    if not isinstance(speak, str) or not speak.strip():
        speak = DEFAULT_VERDICT["speak_aloud"]

    return {
        "verdict": verdict_label,
        "confidence": confidence,
        "signs": signs[:5],
        "recommended_actions": actions[:5],
        "speak_aloud": speak.strip(),
    }


def parse_verdict(raw: str) -> dict[str, Any]:
    """Robust LLM → verdict-dict conversion.

    Order of attempts:
    1. ``json.loads`` after stripping a code fence (the happy path).
    2. ``json_repair.loads`` for nested or malformed JSON (lazy import; if
       the lib is missing we degrade silently to the defaults).
    3. Single-layer envelope unwrap (``{"output": {...}}`` etc.).
    4. Schema validation with sensible defaults for missing keys.
    """
    cleaned = _strip_code_fence(raw)
    parsed: Any = None
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        parsed = _try_json_repair(cleaned)
    if parsed is None:
        return dict(DEFAULT_VERDICT)
    return _validate_verdict(parsed)


def _build_user_prompt(message: dict[str, Any], url_reports: list[dict[str, Any]],
                       intel: list[dict[str, str]], sender_rep: dict[str, Any],
                       wiki: Wiki, cousin_check: dict[str, Any] | None = None) -> str:
    parts: list[str] = []
    parts.append("## EMAIL\n```json\n" + json.dumps(message, indent=2) + "\n```")
    if cousin_check is not None:
        parts.append(
            "## COUSIN-DOMAIN CHECK (deterministic — one piece of evidence)\n"
            "```json\n" + json.dumps(cousin_check, indent=2) + "\n```"
        )
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

    # 4. Cousin-domain check (deterministic, before the LLM call). The
    # LLM uses this as one piece of evidence, never the only one.
    wiki = Wiki()
    sender_domain = (message.get("from", {}).get("domain") or "").lower()
    cousin_check = cousin_domain_check(sender_domain, _wiki_account_domains(wiki))

    # 5. GLM verdict
    user_msg = _build_user_prompt(
        message, url_reports, intel, sender_rep, wiki, cousin_check=cousin_check
    )
    llm = get_provider()
    resp = llm.chat(
        messages=[
            {"role": "system", "content": ANALYZE_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.1,
        max_tokens=700,
    )

    verdict = parse_verdict(resp.text or "")

    verdict["_evidence"] = {
        "url_reports": url_reports,
        "sender_reputation": sender_rep,
        "intel": intel,
        "cousin_domain_check": cousin_check,
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
