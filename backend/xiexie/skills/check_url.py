"""check_url — fetch a URL in isolation and report what it actually does.

The skill returns structured forensics the planner can chain into
``analyze_email``:

```
{
  "url": "...",
  "redirect_chain": [{"status": 302, "url": "...", "ms": 41}, ...],
  "final_url": "...",
  "final_ip_country": "RU",
  "tls": {"issuer": "Let's Encrypt", "valid": true},
  "page_title": "Aetna - Verify Identity",
  "form_fields": ["full_name", "ssn", "credit_card_number"],
  "verdict_features": ["multi-hop redirect", "asks for SSN", "country mismatch"],
}
```

Implementation policy:

1. **Demo URLs** (anything matching the fake-inbox phishing host) return a
   hand-curated forensic report — guarantees the demo never depends on the
   network at Station F. See ``MOCK_URLS`` below.

2. **Real URLs**: if ``httpx`` is available we follow redirects with HEAD
   then GET, capture the chain + final landing, parse a ``<title>`` and
   visible form fields. We *never* execute JavaScript — the safety guarantee
   we sell to seniors. Optional Playwright path is documented but not
   wired in V1 (cut-list item).
"""

from __future__ import annotations

import datetime as dt
import re
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

from ..external import safe_browsing, urlscan as urlscan_api
from .registry import Skill, register

# Hosts we never bother whois-ing — these have hand-curated mock fixtures
# whose ``verdict_features`` already include the domain-age sentence.
_WHOIS_SKIP_HOSTS: tuple[str, ...] = ("aetnna-secure.com",)

# ── demo-time mock fixtures ───────────────────────────────────────────────
MOCK_URLS: dict[str, dict[str, Any]] = {
    "aetnna-secure.com": {
        "redirect_chain": [
            {"status": 302, "url": "http://aetnna-secure.com/r/cgxq", "ms": 41},
            {"status": 302, "url": "https://t.co/aHsW9p", "ms": 88},
            {"status": 302, "url": "https://r.mailgrid-bulk.ru/click?u=mchen", "ms": 124},
            {"status": 200, "url": "https://aetna-verify.netlify.app/login", "ms": 410},
        ],
        "final_url": "https://aetna-verify.netlify.app/login",
        "final_ip_country": "NL (Netlify CDN, registrar in RU)",
        "tls": {"issuer": "Let's Encrypt R3", "valid": True},
        "page_title": "Aetna — Verify Member Identity",
        "form_fields": [
            "full_name",
            "date_of_birth",
            "ssn",
            "member_id",
            "credit_card_number",
            "credit_card_cvv",
        ],
        "verdict_features": [
            "4-hop redirect through .ru tracker",
            "lands on free static host (.netlify.app), not aetna.com",
            "asks for SSN AND credit card AND member ID together (real Aetna never does)",
            "domain registered 9 days ago",
        ],
    },
}


def _mock_lookup(url: str) -> dict[str, Any] | None:
    host = urlparse(url).hostname or ""
    for needle, payload in MOCK_URLS.items():
        if needle in host:
            return {"url": url, **payload, "source": "mock"}
    return None


# ── real (no-JS) fetch path ───────────────────────────────────────────────
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
FORM_INPUT_RE = re.compile(
    r'<input[^>]*name=["\']([^"\']+)["\']', re.I
)


def _real_fetch(url: str, timeout: float = 6.0) -> dict[str, Any]:
    chain: list[dict[str, Any]] = []
    final_url = url
    title: str | None = None
    fields: list[str] = []

    try:
        with httpx.Client(follow_redirects=False, timeout=timeout) as client:
            current = url
            for _ in range(8):
                resp = client.get(current)
                chain.append({"status": resp.status_code, "url": current})
                if 300 <= resp.status_code < 400 and "location" in resp.headers:
                    current = str(httpx.URL(current).join(resp.headers["location"]))
                    continue
                final_url = current
                ctype = resp.headers.get("content-type", "")
                if "html" in ctype.lower():
                    text = resp.text[:200_000]  # cap
                    m = TITLE_RE.search(text)
                    if m:
                        title = re.sub(r"\s+", " ", m.group(1)).strip()
                    fields = list(dict.fromkeys(FORM_INPUT_RE.findall(text)))[:20]
                break
    except httpx.HTTPError as exc:
        return {"url": url, "error": str(exc), "redirect_chain": chain, "source": "real"}

    # Best-effort country: just resolve final host IP — country lookup is offline-only here.
    final_host = urlparse(final_url).hostname
    final_ip = None
    if final_host:
        try:
            final_ip = socket.gethostbyname(final_host)
        except OSError:
            pass

    return {
        "url": url,
        "redirect_chain": chain,
        "final_url": final_url,
        "final_ip": final_ip,
        "page_title": title,
        "form_fields": fields,
        "verdict_features": [],
        "source": "real",
    }


def _whois_age_days(host: str) -> int | None:
    """Best-effort domain age in days via the optional ``python-whois`` lib.

    Returns ``None`` when the lib is missing, the host is in the skip list,
    the lookup raises, or the registrar didn't return a ``creation_date``.
    Never raises — callers can drop the result without guarding.
    """
    if not host or any(host.endswith(skip) for skip in _WHOIS_SKIP_HOSTS):
        return None
    try:
        import whois  # type: ignore
    except Exception:  # noqa: BLE001 — optional dep
        return None
    try:
        record = whois.whois(host)
    except Exception:  # noqa: BLE001 — many whois failures bubble up as generic exceptions
        return None
    created = getattr(record, "creation_date", None) or (
        record.get("creation_date") if isinstance(record, dict) else None
    )
    # Some TLDs return a list of dates; take the earliest.
    if isinstance(created, list):
        created = next((c for c in created if c), None)
    if created is None:
        return None
    if isinstance(created, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                created = dt.datetime.strptime(created, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if not isinstance(created, dt.datetime):
        return None
    if created.tzinfo is not None:
        created = created.astimezone(dt.timezone.utc).replace(tzinfo=None)
    age = (dt.datetime.utcnow() - created).days
    return age if age >= 0 else None


def _enrich_with_external(url: str, data: dict[str, Any]) -> dict[str, Any]:
    """Add Google Safe Browsing + urlscan.io + whois signals.

    These are *additive*; the mock fixture (for our demo URL) and the no-JS
    fetch path (for everything else) remain authoritative for the structured
    forensic fields.
    """
    # Mock-sourced data already carries an authoritative ``verdict_features``
    # block (the demo fixture). Skip whois entirely so the demo never blocks
    # on the network at Station F.
    if data.get("source") != "mock":
        final_url = data.get("final_url") or url
        final_host = (urlparse(final_url).hostname or urlparse(url).hostname or "").lower()
        if final_host:
            age = _whois_age_days(final_host)
            if age is not None:
                data["domain_registered_days_ago"] = age
                if age < 60 and "verdict_features" in data:
                    data["verdict_features"].append(
                        f"domain {final_host} registered {age} days ago (very new)"
                    )

    gsb = safe_browsing.lookup(url)
    if gsb.get("available"):
        data["safe_browsing"] = gsb
        if gsb.get("malicious") and "verdict_features" in data:
            data["verdict_features"].append(
                f"Google Safe Browsing flagged: {', '.join(gsb.get('threats', []))}"
            )

    scans = urlscan_api.search(url)
    if scans.get("available"):
        data["urlscan_search"] = {
            "total_recent_scans": scans.get("total_recent_scans"),
            "malicious_scans": scans.get("malicious_scans"),
        }
        mal = scans.get("malicious_scans") or []
        if mal and "verdict_features" in data:
            categories = {c for s in mal for c in s.get("categories", [])}
            cat_str = (", ".join(sorted(categories))) or "scam"
            data["verdict_features"].append(
                f"urlscan.io has {len(mal)} prior malicious scan(s) of this domain ({cat_str})"
            )

    return data


def run(args: dict[str, Any]) -> str:
    url = str(args.get("url", "")).strip()
    if not url:
        return "I need a URL to check."

    data = _mock_lookup(url) or _real_fetch(url)
    data.setdefault("verdict_features", [])
    data = _enrich_with_external(url, data)
    # Short human-friendly summary; planner gets the structured ``data``
    # via the conversational tool-call result text.
    summary_lines = [f"Checked {url} ({data.get('source')})"]
    chain = data.get("redirect_chain") or []
    if chain:
        summary_lines.append(f"Redirect chain ({len(chain)} hop{'s' if len(chain) != 1 else ''}):")
        for hop in chain:
            summary_lines.append(f"  [{hop.get('status')}] {hop.get('url')}")
    if data.get("final_url"):
        summary_lines.append(f"Final URL: {data['final_url']}")
    if data.get("page_title"):
        summary_lines.append(f"Page title: {data['page_title']}")
    if data.get("form_fields"):
        summary_lines.append(f"Form fields: {', '.join(data['form_fields'])}")
    if data.get("verdict_features"):
        summary_lines.append("Forensic features:")
        for f in data["verdict_features"]:
            summary_lines.append(f"  - {f}")
    if data.get("safe_browsing", {}).get("available"):
        gsb = data["safe_browsing"]
        verdict = "malicious" if gsb.get("malicious") else "clean"
        summary_lines.append(
            f"Google Safe Browsing: {verdict}"
            + (f" ({', '.join(gsb.get('threats', []))})" if gsb.get("threats") else "")
        )
    if data.get("urlscan_search", {}).get("total_recent_scans") is not None:
        scans = data["urlscan_search"]
        n = len(scans.get("malicious_scans") or [])
        total = scans.get("total_recent_scans") or 0
        summary_lines.append(f"urlscan.io history: {n}/{total} prior scans flagged malicious")
    if data.get("domain_registered_days_ago") is not None:
        summary_lines.append(
            f"Domain age (whois): {data['domain_registered_days_ago']} days"
        )
    if data.get("error"):
        summary_lines.append(f"(fetch error: {data['error']})")
    return "\n".join(summary_lines)


def fetch_struct(url: str) -> dict[str, Any]:
    """Same as ``run`` but returns the structured dict — used by analyze_email."""
    data = _mock_lookup(url) or _real_fetch(url)
    data.setdefault("verdict_features", [])
    return _enrich_with_external(url, data)


SKILL = register(
    Skill(
        name="check_url",
        description=(
            "Open a URL in isolation (no JavaScript executed), follow redirects, capture the "
            "final landing page title and visible form fields. Use to forensically inspect "
            "links from suspicious emails before the user even hovers."
        ),
        parameters={
            "type": "object",
            "properties": {"url": {"type": "string", "description": "URL to check."}},
            "required": ["url"],
        },
        run=run,
        destructive=False,
        tags=["scam-shield", "browser"],
    )
)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    a = p.parse_args()
    print(run({"url": a.url}))
