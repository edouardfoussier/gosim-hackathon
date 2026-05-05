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

from ..external import email_rep
from ..memory import Wiki
from . import _inbox
from .registry import Skill, register

URGENT_RE = re.compile(r"\b(urgent|immediately|expires?\s+today|verify\s+now|act\s+now)\b", re.I)

# Brands the planner should recognise as targets of display-name spoofing
# even when the user has no matching wiki/accounts.md entry. Keep tight —
# false positives here are noisier than false negatives because the
# verdict pipeline still has the cousin-domain + URL forensics signals.
COMMON_BRANDS: dict[str, list[str]] = {
    "aetna": ["aetna.com"],
    "pg&e": ["pge.com"],
    "pge": ["pge.com"],
    "bank of america": ["bankofamerica.com", "bofa.com"],
    "wells fargo": ["wellsfargo.com"],
    "chase": ["chase.com", "jpmorganchase.com"],
    "amazon": ["amazon.com"],
    "apple": ["apple.com", "icloud.com"],
    "paypal": ["paypal.com"],
    "irs": ["irs.gov"],
    "usps": ["usps.com"],
    "fedex": ["fedex.com"],
    "ups": ["ups.com"],
    "netflix": ["netflix.com"],
    "microsoft": ["microsoft.com"],
    "google": ["google.com"],
    "stanford": ["stanfordhealthcare.org", "stanford.edu"],
}

# Subdomain prefixes that are clearly transactional / safe when paired with
# a known brand domain (``mail.aetna.com`` ≈ ``aetna.com``).
SAFE_SUBDOMAIN_PREFIXES: tuple[str, ...] = (
    "mail",
    "email",
    "notifications",
    "noreply",
    "no-reply",
    "alerts",
    "updates",
    "billing",
    "support",
    "service",
    "help",
    "newsletter",
)


def _known_account_domains() -> set[str]:
    wiki = Wiki()
    page = wiki.get("accounts")
    if not page:
        return set()
    # Very cheap extraction: grab tokens that look like domains.
    domains = set(re.findall(r"\b[a-z0-9][a-z0-9\-]*\.[a-z]{2,}\b", page.body, re.I))
    return {d.lower() for d in domains}


def _registrable_root(domain: str) -> str:
    """Return the rightmost two labels — ``mail.aetna.com`` → ``aetna.com``.

    Naïve eTLD handling. Good enough for our brand allowlist; for a true
    Public Suffix List lookup we would pull in ``tldextract`` (cut from V1).
    """
    parts = (domain or "").lower().strip(".").split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return parts[0] if parts else ""


def _is_safe_subdomain_of(domain: str, brand_domains: list[str]) -> bool:
    """``mail.aetna.com`` is OK for the brand ``aetna``."""
    domain = (domain or "").lower().strip(".")
    if not domain:
        return False
    for bd in brand_domains:
        bd = bd.lower()
        if domain == bd:
            return True
        if not domain.endswith("." + bd):
            continue
        prefix = domain[: -(len(bd) + 1)]  # strip trailing ".bd"
        first_label = prefix.split(".")[0] if prefix else ""
        if first_label in SAFE_SUBDOMAIN_PREFIXES:
            return True
    return False


def _detect_display_name_spoof(
    msg: dict[str, Any],
    known_domains: set[str],
) -> str | None:
    """Return a signal sentence when ``from.name`` references a known brand
    but the actual domain is neither in ``accounts.md`` nor a recognised
    transactional subdomain of the brand.
    """
    sender = msg.get("from", {}) or {}
    display = (sender.get("name") or "").lower()
    sender_domain = (sender.get("domain") or "").lower().strip(".")
    if not display or not sender_domain:
        return None

    sender_root = _registrable_root(sender_domain)
    for brand, brand_domains in COMMON_BRANDS.items():
        if brand not in display:
            continue

        # Direct match against the brand's official root → not spoofed.
        if sender_root in brand_domains or sender_domain in brand_domains:
            return None
        # Recognised transactional subdomain of the brand → not spoofed.
        if _is_safe_subdomain_of(sender_domain, brand_domains):
            return None
        # Wiki/accounts.md exact domain entry overrides — the user told
        # Xiexie this domain is theirs, even if we don't recognise it.
        if sender_root in known_domains or sender_domain in known_domains:
            return None
        # Display references the brand, sender domain doesn't → spoof.
        return (
            f"display name pretends to be {brand.title()} "
            f"but the domain {sender_domain!r} doesn't match"
        )

    return None


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

    spoof = _detect_display_name_spoof(msg, known_domains)
    if spoof:
        signals.append(spoof)

    subject = msg.get("subject") or ""
    if URGENT_RE.search(subject):
        signals.append("urgent / scare-tactic subject line")

    body = msg.get("body_text") or ""
    if URGENT_RE.search(body) and "social security" in body.lower():
        signals.append("asks for Social Security Number")

    # EmailRep enrichment (free tier, graceful no-op if rate-limited)
    sender_addr = msg.get("from", {}).get("address")
    if sender_addr:
        rep = email_rep.lookup(sender_addr)
        if rep.get("available"):
            if rep.get("suspicious"):
                signals.append("EmailRep flags this sender as suspicious")
            if rep.get("reputation") == "low":
                signals.append("EmailRep gives this sender a low reputation score")
            domain_age = rep.get("domain_age_days")
            if isinstance(domain_age, int) and domain_age < 60:
                signals.append(f"sender domain registered {domain_age} days ago (very new)")

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
