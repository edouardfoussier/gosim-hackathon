"""EmailRep.io — sender reputation, free tier (50 unauthenticated/day or
~unlimited with a free API key).

API: ``GET https://emailrep.io/{email}``
Docs: https://emailrep.io/

The response is rich; we project to a small flat dict so prompts stay tight.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import httpx

EMAILREP_URL = "https://emailrep.io/{email}"


@lru_cache(maxsize=256)
def _cached_lookup(email: str) -> dict[str, Any]:
    headers = {"User-Agent": "Xiexie/0.1 (hackathon)"}
    api_key = os.getenv("EMAILREP_API_KEY")
    if api_key:
        headers["Key"] = api_key

    try:
        resp = httpx.get(EMAILREP_URL.format(email=email), headers=headers, timeout=4)
        resp.raise_for_status()
    except httpx.HTTPError as exc:  # noqa: BLE001
        return {"available": False, "error": str(exc)}

    data = resp.json()
    details = data.get("details", {}) or {}
    return {
        "available": True,
        "email": email,
        "reputation": data.get("reputation"),  # none | low | medium | high
        "suspicious": bool(data.get("suspicious")),
        "spam_count": details.get("blacklisted"),
        "domain_age_days": details.get("days_since_domain_creation"),
        "spf_strict": details.get("spf_strict"),
        "dmarc_enforced": details.get("dmarc_enforced"),
        "credentials_leaked": details.get("credentials_leaked"),
        "data_breach": details.get("data_breach"),
        "free_provider": details.get("free_provider"),
        "disposable": details.get("disposable"),
        "deliverable": details.get("deliverable"),
        "source": "emailrep",
    }


def lookup(email: str) -> dict[str, Any]:
    if not email or "@" not in email:
        return {"available": False, "error": "invalid email"}
    return _cached_lookup(email.lower().strip())
