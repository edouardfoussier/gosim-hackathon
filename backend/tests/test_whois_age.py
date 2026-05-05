"""Smoke tests for the whois shim in check_url.py.

These tests intentionally do NOT hit the network: they verify the skip
list, the lazy-import graceful no-op path, and the mock-fixture path is
preserved. Run with::

    cd backend && uv run python -m tests.test_whois_age
"""

from __future__ import annotations

import sys
from typing import Any

from xiexie.skills import check_url


def test_skip_list_returns_none_for_demo_host() -> None:
    out = check_url._whois_age_days("aetnna-secure.com")
    assert out is None, out
    print("ok skip_list_returns_none_for_demo_host")


def test_empty_host_returns_none() -> None:
    assert check_url._whois_age_days("") is None
    print("ok empty_host_returns_none")


def test_missing_lib_returns_none(monkeypatched: dict[str, Any]) -> None:
    """Simulate ``import whois`` failing — should silently degrade."""
    saved = sys.modules.pop("whois", None)
    try:
        # Inject a sentinel that makes ``import whois`` raise on next access.
        sys.modules["whois"] = None  # type: ignore[assignment]
        out = check_url._whois_age_days("example.com")
        assert out is None, out
    finally:
        if saved is not None:
            sys.modules["whois"] = saved
        else:
            sys.modules.pop("whois", None)
    print("ok missing_lib_returns_none")


def test_mock_fixture_unchanged() -> None:
    """The hand-curated mock for the demo URL must keep its 9-day signal."""
    data = check_url.fetch_struct("http://aetnna-secure.com/r/cgxq?u=mchen")
    # The whois enrichment must NOT have added a key for the skip-listed host.
    assert "domain_registered_days_ago" not in data, data
    # The fixture's verdict_features must still mention the 9-day signal.
    assert any(
        "9 days ago" in feat or "9 days" in feat for feat in data.get("verdict_features", [])
    ), data["verdict_features"]
    print("ok mock_fixture_unchanged")


def test_parses_string_creation_date() -> None:
    """If ``whois`` returns an ISO string, ``_whois_age_days`` should accept it."""
    saved = sys.modules.get("whois")
    fake = type(sys)("whois")

    def fake_whois(_host: str) -> dict[str, str]:
        return {"creation_date": "2024-01-01"}

    fake.whois = fake_whois  # type: ignore[attr-defined]
    sys.modules["whois"] = fake  # type: ignore[assignment]
    try:
        out = check_url._whois_age_days("example.com")
        assert isinstance(out, int) and out > 0, out
    finally:
        if saved is not None:
            sys.modules["whois"] = saved
        else:
            sys.modules.pop("whois", None)
    print("ok parses_string_creation_date")


def test_handles_list_of_dates() -> None:
    """Some TLDs (e.g. .com via certain registrars) return multiple dates."""
    import datetime as dt

    saved = sys.modules.get("whois")
    fake = type(sys)("whois")
    early = dt.datetime(2024, 1, 1)
    late = dt.datetime(2025, 6, 1)

    def fake_whois(_host: str):
        class _R:
            creation_date = [late, early]

        return _R()

    fake.whois = fake_whois  # type: ignore[attr-defined]
    sys.modules["whois"] = fake  # type: ignore[assignment]
    try:
        out = check_url._whois_age_days("example.com")
        # Implementation picks the first non-None entry — that's still ≥ 0.
        assert isinstance(out, int) and out > 0, out
    finally:
        if saved is not None:
            sys.modules["whois"] = saved
        else:
            sys.modules.pop("whois", None)
    print("ok handles_list_of_dates")


def main() -> None:
    test_skip_list_returns_none_for_demo_host()
    test_empty_host_returns_none()
    test_missing_lib_returns_none({})
    test_mock_fixture_unchanged()
    test_parses_string_creation_date()
    test_handles_list_of_dates()
    print("all whois_age tests passed")


if __name__ == "__main__":
    main()
