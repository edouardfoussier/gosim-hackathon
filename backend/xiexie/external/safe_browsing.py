"""Google Safe Browsing v4 — instant, free, non-commercial URL lookup.

API: ``POST https://safebrowsing.googleapis.com/v4/threatMatches:find``
Docs: https://developers.google.com/safe-browsing/v4

Returns a list of threat matches; empty list = clean (or unknown).
Cached aggressively in-process to keep demo latency snappy.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import httpx

GSB_URL = "https://safebrowsing.googleapis.com/v4/threatMatches:find"
THREAT_TYPES = ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"]


def _payload(api_key: str, urls: list[str]) -> dict[str, Any]:
    return {
        "client": {"clientId": "xiexie", "clientVersion": "0.1.0"},
        "threatInfo": {
            "threatTypes": THREAT_TYPES,
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": u} for u in urls],
        },
    }


@lru_cache(maxsize=256)
def _cached_lookup(url: str, api_key: str) -> tuple[str, ...]:
    try:
        resp = httpx.post(
            GSB_URL,
            params={"key": api_key},
            json=_payload(api_key, [url]),
            timeout=4,
        )
        resp.raise_for_status()
    except httpx.HTTPError:
        return ()

    matches = resp.json().get("matches", [])
    return tuple(m.get("threatType", "UNKNOWN") for m in matches)


def lookup(url: str) -> dict[str, Any]:
    """Returns ``{available, malicious, threats, source}``."""
    api_key = os.getenv("GOOGLE_SAFE_BROWSING_API_KEY")
    if not api_key:
        return {"available": False, "malicious": None, "threats": [], "source": "gsb-disabled"}

    threats = list(_cached_lookup(url, api_key))
    return {
        "available": True,
        "malicious": bool(threats),
        "threats": threats,
        "source": "google-safe-browsing-v4",
    }
