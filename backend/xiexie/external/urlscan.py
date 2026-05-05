"""urlscan.io — real headless URL forensics.

Two paths:

1. ``search(domain)`` — instant. Looks up *previous* scans for a domain in
   the public urlscan database. Returns malicious flags + recent scan
   verdicts. Free, fast, no waiting. Used as the primary signal for known
   bad domains.

2. ``submit_and_wait(url)`` — slow (15–30 s). Submits a fresh scan and polls
   for the result. Optional, behind a feature flag because the demo cannot
   afford 30 s of latency on stage. Useful for Q&A / post-demo deep dives.

API key is *not* required for read-only search but lifts the rate limit.
Get a free one at https://urlscan.io/user/signup/.
"""

from __future__ import annotations

import os
import time
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

import httpx

SEARCH_URL = "https://urlscan.io/api/v1/search/"
SUBMIT_URL = "https://urlscan.io/api/v1/scan/"
RESULT_URL_TMPL = "https://urlscan.io/api/v1/result/{uuid}/"


def _headers() -> dict[str, str]:
    api_key = os.getenv("URLSCAN_API_KEY")
    return {"API-Key": api_key} if api_key else {}


@lru_cache(maxsize=256)
def _cached_search(query: str) -> dict[str, Any]:
    try:
        resp = httpx.get(
            SEARCH_URL,
            params={"q": query, "size": 10},
            headers=_headers(),
            timeout=4,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:  # noqa: BLE001
        return {"available": False, "error": str(exc)}

    data = resp.json()
    results = data.get("results", [])
    malicious = []
    for r in results:
        verdicts = r.get("verdicts", {}) or {}
        overall = verdicts.get("overall", {}) or {}
        if overall.get("malicious"):
            malicious.append(
                {
                    "url": r.get("page", {}).get("url"),
                    "score": overall.get("score"),
                    "categories": overall.get("categories", []),
                    "scan_date": r.get("task", {}).get("time"),
                    "scan_id": r.get("_id"),
                    "result_link": r.get("result"),
                }
            )

    return {
        "available": True,
        "total_recent_scans": len(results),
        "malicious_scans": malicious,
        "source": "urlscan-search",
    }


def search(url_or_domain: str) -> dict[str, Any]:
    """Look up previous scans of this URL or its domain."""
    parsed = urlparse(url_or_domain) if "://" in url_or_domain else None
    domain = parsed.hostname if parsed else url_or_domain
    if not domain:
        return {"available": False, "error": "no domain extracted"}
    return _cached_search(f"page.domain:{domain}")


def submit_and_wait(url: str, *, max_wait_s: int = 25) -> dict[str, Any]:
    """Live submit a URL for headless rendering. Slow — only behind a feature flag."""
    api_key = os.getenv("URLSCAN_API_KEY")
    if not api_key:
        return {"available": False, "error": "URLSCAN_API_KEY required for submit"}

    try:
        resp = httpx.post(
            SUBMIT_URL,
            json={"url": url, "visibility": "private"},
            headers={"API-Key": api_key, "Content-Type": "application/json"},
            timeout=5,
        )
        resp.raise_for_status()
        scan_id = resp.json()["uuid"]
    except (httpx.HTTPError, KeyError) as exc:  # noqa: BLE001
        return {"available": False, "error": f"submit failed: {exc}"}

    deadline = time.time() + max_wait_s
    result_url = RESULT_URL_TMPL.format(uuid=scan_id)
    while time.time() < deadline:
        try:
            r = httpx.get(result_url, headers={"API-Key": api_key}, timeout=4)
        except httpx.HTTPError:
            time.sleep(2)
            continue
        if r.status_code == 200:
            data = r.json()
            verdicts = data.get("verdicts", {}).get("overall", {}) or {}
            return {
                "available": True,
                "malicious": bool(verdicts.get("malicious")),
                "score": verdicts.get("score"),
                "categories": verdicts.get("categories", []),
                "screenshot": data.get("task", {}).get("screenshotURL"),
                "result_link": f"https://urlscan.io/result/{scan_id}/",
                "source": "urlscan-live",
            }
        time.sleep(2)
    return {"available": False, "error": "submit timed out"}
