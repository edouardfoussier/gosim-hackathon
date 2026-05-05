"""Smoke tests for ``analyze_email.cousin_domain_check`` (no LLM, no network).

Run with::

    cd backend && uv run python -m tests.test_cousin_domain
"""

from __future__ import annotations

from xiexie.skills.analyze_email import cousin_domain_check


KNOWN = [
    "aetna.com",
    "pge.com",
    "stanfordhealthcare.org",
    "icloud.com",
    "gmail.com",
    "amazon.com",
]


def test_exact_match_safe() -> None:
    out = cousin_domain_check("aetna.com", KNOWN)
    assert out["result"] == "safe", out
    assert out["matches"][0]["rule"] == "exact"
    print("ok exact_match_safe")


def test_compact_doubles_aetnna_aetna() -> None:
    out = cousin_domain_check("aetnna-secure.com", KNOWN)
    # Note: ``aetnna-secure`` ≠ ``aetna`` after collapsing, so the strict
    # compact_doubles rule should miss; expect shared_prefix_4 to fire.
    assert out["result"] == "cousin", out
    rules = {m["rule"] for m in out["matches"]}
    assert "shared_prefix_4" in rules, out
    assert any(m["known"] == "aetna.com" for m in out["matches"]), out
    print("ok compact_doubles_aetnna_aetna")


def test_pure_compact_doubles_match() -> None:
    out = cousin_domain_check("aetnna.com", KNOWN)
    assert out["result"] == "cousin", out
    rules = {m["rule"] for m in out["matches"]}
    assert "compact_doubles" in rules, out
    print("ok pure_compact_doubles_match")


def test_levenshtein_one_edit() -> None:
    out = cousin_domain_check("aetnaa.com", KNOWN)
    assert out["result"] == "cousin", out
    assert out["matches"][0]["rule"] in {"levenshtein_1", "compact_doubles"}, out
    print("ok levenshtein_one_edit")


def test_levenshtein_two_same_tld() -> None:
    out = cousin_domain_check("aetne.com", KNOWN)
    assert out["result"] == "cousin", out
    rules = {m["rule"] for m in out["matches"]}
    # "aetne" → "aetna": one edit, so levenshtein_1; both possible.
    assert rules & {"levenshtein_1", "shared_prefix_4"}, out
    print("ok levenshtein_two_same_tld")


def test_unrelated_domain_none() -> None:
    out = cousin_domain_check("foobar-xyz.io", KNOWN)
    assert out["result"] == "none", out
    print("ok unrelated_domain_none")


def test_no_known_domains_none() -> None:
    out = cousin_domain_check("aetna.com", [])
    assert out["result"] == "none", out
    print("ok no_known_domains_none")


def test_empty_sender_none() -> None:
    out = cousin_domain_check("", KNOWN)
    assert out["result"] == "none", out
    print("ok empty_sender_none")


def test_amazon_typosquat_amaz0n() -> None:
    out = cousin_domain_check("amaz0n.com", KNOWN)
    assert out["result"] == "cousin", out
    assert any(m["known"] == "amazon.com" for m in out["matches"]), out
    print("ok amazon_typosquat_amaz0n")


def test_pge_pg_e_typo() -> None:
    out = cousin_domain_check("pgee.com", KNOWN)
    assert out["result"] == "cousin", out
    assert any(m["known"] == "pge.com" for m in out["matches"]), out
    print("ok pge_pg_e_typo")


def main() -> None:
    test_exact_match_safe()
    test_compact_doubles_aetnna_aetna()
    test_pure_compact_doubles_match()
    test_levenshtein_one_edit()
    test_levenshtein_two_same_tld()
    test_unrelated_domain_none()
    test_no_known_domains_none()
    test_empty_sender_none()
    test_amazon_typosquat_amaz0n()
    test_pge_pg_e_typo()
    print("all cousin_domain_check tests passed")


if __name__ == "__main__":
    main()
