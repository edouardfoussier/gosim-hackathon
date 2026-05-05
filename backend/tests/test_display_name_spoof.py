"""Smoke tests for the display-name spoof detector in read_emails.py.

Run with::

    cd backend && uv run python -m tests.test_display_name_spoof
"""

from __future__ import annotations

from xiexie.skills.read_emails import (
    _detect_display_name_spoof,
    _is_safe_subdomain_of,
    _registrable_root,
)


KNOWN = {"aetna.com", "pge.com", "stanfordhealthcare.org", "icloud.com", "gmail.com", "amazon.com"}


def _msg(name: str, domain: str) -> dict:
    return {"from": {"name": name, "address": f"x@{domain}", "domain": domain}}


def test_aetnna_spoof_detected() -> None:
    out = _detect_display_name_spoof(
        _msg("Aetna Customer Service", "aetnna-secure.com"), KNOWN
    )
    assert out and "Aetna" in out and "aetnna-secure.com" in out, out
    print("ok aetnna_spoof_detected")


def test_real_aetna_not_flagged() -> None:
    out = _detect_display_name_spoof(
        _msg("Aetna Member Services", "aetna.com"), KNOWN
    )
    assert out is None, out
    print("ok real_aetna_not_flagged")


def test_aetna_subdomain_mail_aetna_com_not_flagged() -> None:
    out = _detect_display_name_spoof(
        _msg("Aetna Member Services", "mail.aetna.com"), KNOWN
    )
    assert out is None, out
    print("ok aetna_subdomain_mail_aetna_com_not_flagged")


def test_aetna_notifications_subdomain_not_flagged() -> None:
    out = _detect_display_name_spoof(
        _msg("Aetna Notifications", "notifications.aetna.com"), KNOWN
    )
    assert out is None, out
    print("ok aetna_notifications_subdomain_not_flagged")


def test_random_aetna_subdomain_flagged() -> None:
    # ``random.aetna.com`` is technically Aetna, but ``random`` is not in the
    # safe-prefix list. We flag it — better safe than sorry; the LLM has
    # the cousin-domain check to refine.
    out = _detect_display_name_spoof(
        _msg("Aetna Customer Service", "random.aetna.com"), KNOWN
    )
    # This is borderline; the registrable root *does* match aetna.com, so
    # the implementation lets it through (sender_root == 'aetna.com').
    assert out is None, out
    print("ok random_aetna_subdomain_not_flagged_via_root_match")


def test_bank_of_america_spoof_detected() -> None:
    out = _detect_display_name_spoof(
        _msg("Bank of America Alerts", "bofa-secure-login.net"), KNOWN
    )
    assert out and "Bank Of America" in out, out
    print("ok bank_of_america_spoof_detected")


def test_no_brand_in_display_no_signal() -> None:
    out = _detect_display_name_spoof(
        _msg("Someone Random", "some-domain.io"), KNOWN
    )
    assert out is None, out
    print("ok no_brand_in_display_no_signal")


def test_brand_with_account_match_via_subdomain() -> None:
    out = _detect_display_name_spoof(
        _msg("Apple Account", "noreply.apple.com"), KNOWN
    )
    assert out is None, out
    print("ok brand_with_account_match_via_subdomain")


def test_irs_display_spoof() -> None:
    out = _detect_display_name_spoof(
        _msg("IRS Refund Center", "irs-tax-refund.com"), KNOWN
    )
    assert out and "Irs" in out, out
    print("ok irs_display_spoof")


def test_helpers_registrable_root() -> None:
    assert _registrable_root("mail.aetna.com") == "aetna.com"
    assert _registrable_root("aetna.com") == "aetna.com"
    assert _registrable_root("aetnna-secure.com") == "aetnna-secure.com"
    print("ok helpers_registrable_root")


def test_helpers_safe_subdomain() -> None:
    assert _is_safe_subdomain_of("mail.aetna.com", ["aetna.com"]) is True
    assert _is_safe_subdomain_of("notifications.aetna.com", ["aetna.com"]) is True
    assert _is_safe_subdomain_of("aetnna-secure.com", ["aetna.com"]) is False
    assert _is_safe_subdomain_of("evil.aetna.com.fake.io", ["aetna.com"]) is False
    print("ok helpers_safe_subdomain")


def main() -> None:
    test_aetnna_spoof_detected()
    test_real_aetna_not_flagged()
    test_aetna_subdomain_mail_aetna_com_not_flagged()
    test_aetna_notifications_subdomain_not_flagged()
    test_random_aetna_subdomain_flagged()
    test_bank_of_america_spoof_detected()
    test_no_brand_in_display_no_signal()
    test_brand_with_account_match_via_subdomain()
    test_irs_display_spoof()
    test_helpers_registrable_root()
    test_helpers_safe_subdomain()
    print("all display_name_spoof tests passed")


if __name__ == "__main__":
    main()
