"""search_scam_intel — web-search for current elder-scam patterns.

Two paths:
1. **Live**: if ``TAVILY_API_KEY`` is set, hit Tavily Search and summarise
   the top 3 results.
2. **Fixture**: otherwise, return a hand-curated payload tied to the demo
   phishing template. Matches the same style as a real Tavily response so
   the planner / analyze_email prompt is identical in either path.

The wiki linter is the *long-running* counterpart of this skill: it queries
weekly and writes the consolidated picture into ``data/wiki/scam_alerts.md``.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from .registry import Skill, register

TAVILY_URL = "https://api.tavily.com/search"


# ── fixture for the demo phishing pattern ─────────────────────────────────
FIXTURE: dict[str, list[dict[str, str]]] = {
    "aetna renewal phishing": [
        {
            "title": "FTC Consumer Alert: 'Aetna' renewal scam targeting Medicare-age users",
            "url": "https://consumer.ftc.gov/consumer-alerts/2026/04/aetna-renewal-scam",
            "content": "The FTC has received over 4,200 reports in the last 30 days of phishing emails imitating Aetna's open-enrollment renewals. The scam emails come from typosquatted domains (aetnna-secure.com, aetna-renew.net) and ask for Social Security numbers and credit cards on a separate site.",
            "published": "2026-04-28",
        },
        {
            "title": "AARP Fraud Watch — Fake insurance renewal emails surge",
            "url": "https://www.aarp.org/money/scams-fraud/info-2026/fake-aetna-renewal.html",
            "content": "AARP Fraud Watch confirms a wave of phishing emails impersonating Aetna and other major US insurers. Common signs: domain looks slightly off, urgent tone ('your coverage ends today'), asks for SSN. Real insurers never request SSN at renewal via email link.",
            "published": "2026-04-30",
        },
        {
            "title": "Reddit r/scams — got an 'Aetna verify identity' email today",
            "url": "https://www.reddit.com/r/scams/comments/aetna-verify-identity",
            "content": "Multiple users reporting nearly identical phishing emails impersonating Aetna over the past week. Sender domains include aetnna-secure.com and aetna.support. Links go through bit.ly to a Netlify-hosted fake login page.",
            "published": "2026-05-02",
        },
    ]
}


def _live_tavily(query: str, api_key: str) -> list[dict[str, str]]:
    payload = {"api_key": api_key, "query": query, "max_results": 3, "search_depth": "advanced"}
    try:
        resp = httpx.post(TAVILY_URL, json=payload, timeout=8)
        resp.raise_for_status()
    except httpx.HTTPError as exc:  # noqa: BLE001
        return [{"title": "Tavily unreachable", "url": "", "content": str(exc), "published": ""}]

    raw = resp.json().get("results", [])
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
            "published": r.get("published_date", ""),
        }
        for r in raw
    ]


def search(query: str) -> list[dict[str, str]]:
    api_key = os.getenv("TAVILY_API_KEY")
    if api_key:
        return _live_tavily(query, api_key)
    # try every fixture key — pick the one whose words overlap the query most
    q_words = set(query.lower().split())
    best_key = max(
        FIXTURE,
        key=lambda k: len(q_words & set(k.split())),
        default=None,
    )
    if best_key:
        return FIXTURE[best_key]
    return []


def run(args: dict[str, Any]) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        return "What scam pattern should I search for?"
    results = search(query)
    if not results:
        return "Nothing in my scam-intel feeds matches that query yet."
    lines = [f"Found {len(results)} relevant report{'s' if len(results) != 1 else ''}:"]
    for r in results:
        published = r.get("published") or ""
        when = f" ({published})" if published else ""
        lines.append(f"- {r['title']}{when}")
        excerpt = r["content"]
        if excerpt:
            lines.append(f"  {excerpt[:280]}…" if len(excerpt) > 280 else f"  {excerpt}")
    return "\n".join(lines)


SKILL = register(
    Skill(
        name="search_scam_intel",
        description=(
            "Search the public web (FTC, AARP, Action Fraud, Reddit r/scams, etc.) for "
            "current scam patterns matching a description. Use to ground a verdict in "
            "live evidence — not just heuristics."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Short query — e.g. 'aetna renewal phishing 2026', "
                    "'fake usps redelivery fee', 'IRS refund scam'.",
                }
            },
            "required": ["query"],
        },
        run=run,
        destructive=False,
        tags=["scam-shield", "research"],
    )
)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--query", required=True)
    a = p.parse_args()
    print(run({"query": a.query}))
