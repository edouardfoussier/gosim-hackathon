"""Tests for the ``_inbox`` source router (demo fixture vs Mail.app).

We mock ``_mail_app.list_unread`` / ``_mail_app.archive`` so the test never
actually shells out to AppleScript — that lets the suite run on any
machine, including Linux CI, and keeps the demo's real inbox out of
the test fixtures.

Run with::

    cd backend && uv run python tests/test_mailapp_router.py
"""

from __future__ import annotations

import os
import sys
import unittest.mock as mock
from pathlib import Path

# Allow ``python tests/test_mailapp_router.py`` without ``-m``.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from xiexie.skills import _inbox, _mail_app  # noqa: E402


# A canonical Mail.app-shaped message used by every mailapp-source test.
_FAKE_MAILAPP_MSG = {
    "id": "CAB1234@mail.example.com",
    "from": {
        "name": "Aetna Customer Service",
        "address": "renewal-secure@aetnna-secure.com",
        "domain": "aetnna-secure.com",
    },
    "to": ["margaret@example.com"],
    "subject": "URGENT: Your Aetna coverage expires TODAY",
    "received_at": "2026-05-05T18:31:00",
    "read": False,
    "archived": False,
    "headers": {
        "Return-Path": "<no-reply@mailgrid-bulk.ru>",
        "Received-SPF": "fail (sender IP not authorized)",
        "Authentication-Results": "spf=fail dkim=none dmarc=fail",
    },
    "body_text": "Dear Margaret… click http://aetnna-secure.com/r/cgxq",
    "links": [
        {"text": "http://aetnna-secure.com/r/cgxq", "url": "http://aetnna-secure.com/r/cgxq"}
    ],
}


def _set_source(monkey_env: dict[str, str | None], value: str) -> None:
    """Helper: snapshot+set a single env var for restoration in tearDown."""
    monkey_env["MAIL_SOURCE"] = os.environ.get("MAIL_SOURCE")
    os.environ["MAIL_SOURCE"] = value


def _restore_env(monkey_env: dict[str, str | None]) -> None:
    for k, v in monkey_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# ─── source selection ───────────────────────────────────────────────────
def test_default_source_is_mailapp() -> None:
    saved: dict[str, str | None] = {}
    saved["MAIL_SOURCE"] = os.environ.pop("MAIL_SOURCE", None)
    try:
        assert _inbox.configured_source() == "mailapp", (
            "default should be Mail.app — read_emails depends on this"
        )
    finally:
        _restore_env(saved)
    print("ok default_source_is_mailapp")


def test_unknown_source_falls_back_to_demo() -> None:
    saved: dict[str, str | None] = {}
    _set_source(saved, "outlook")  # not a real source
    try:
        assert _inbox.configured_source() == "demo"
    finally:
        _restore_env(saved)
    print("ok unknown_source_falls_back_to_demo")


# ─── demo fixture path is unchanged ─────────────────────────────────────
def test_demo_source_reads_fixture() -> None:
    saved: dict[str, str | None] = {}
    _set_source(saved, "demo")
    try:
        msgs = _inbox.all_messages()
        assert msgs, "demo fixture must contain at least one message"
        ids = {m["id"] for m in msgs}
        assert "msg-003" in ids, f"expected msg-003 in {ids}"
        # Mail.app helpers must NOT be invoked when source is demo.
        with mock.patch.object(_mail_app, "list_unread") as fake:
            _inbox.all_messages()
            assert not fake.called, "demo source must not touch Mail.app"
    finally:
        _restore_env(saved)
    print("ok demo_source_reads_fixture")


def test_demo_source_get_message_unchanged() -> None:
    saved: dict[str, str | None] = {}
    _set_source(saved, "demo")
    try:
        msg = _inbox.get_message("msg-003")
        assert msg is not None and msg["id"] == "msg-003"
        assert "aetnna-secure" in msg["from"]["domain"]
    finally:
        _restore_env(saved)
    print("ok demo_source_get_message_unchanged")


# ─── mailapp source dispatches correctly ─────────────────────────────────
def test_mailapp_source_calls_list_unread() -> None:
    saved: dict[str, str | None] = {}
    _set_source(saved, "mailapp")
    try:
        with mock.patch.object(
            _mail_app, "list_unread", return_value=[_FAKE_MAILAPP_MSG]
        ) as fake:
            msgs = _inbox.all_messages()
        assert fake.called, "mailapp source must dispatch to _mail_app.list_unread"
        assert len(msgs) == 1
        assert msgs[0]["id"] == _FAKE_MAILAPP_MSG["id"]
    finally:
        _restore_env(saved)
    print("ok mailapp_source_calls_list_unread")


def test_mailapp_source_filters_unread_only() -> None:
    """Even though Mail.app already filters, the router enforces the contract."""
    saved: dict[str, str | None] = {}
    _set_source(saved, "mailapp")
    read_msg = {**_FAKE_MAILAPP_MSG, "id": "READ@example.com", "read": True}
    try:
        with mock.patch.object(
            _mail_app,
            "list_unread",
            return_value=[_FAKE_MAILAPP_MSG, read_msg],
        ):
            msgs = _inbox.all_messages(unread_only=True)
        ids = {m["id"] for m in msgs}
        assert read_msg["id"] not in ids, "unread_only=True must drop read messages"
        assert _FAKE_MAILAPP_MSG["id"] in ids
    finally:
        _restore_env(saved)
    print("ok mailapp_source_filters_unread_only")


def test_mailapp_source_get_message_dispatches_find_one() -> None:
    saved: dict[str, str | None] = {}
    _set_source(saved, "mailapp")
    try:
        with mock.patch.object(
            _mail_app, "find_one", return_value=_FAKE_MAILAPP_MSG
        ) as fake:
            msg = _inbox.get_message(_FAKE_MAILAPP_MSG["id"])
        assert fake.called
        assert msg == _FAKE_MAILAPP_MSG
    finally:
        _restore_env(saved)
    print("ok mailapp_source_get_message_dispatches_find_one")


# ─── mutation routing ───────────────────────────────────────────────────
def test_mailapp_archive_invokes_apple_event() -> None:
    saved: dict[str, str | None] = {}
    _set_source(saved, "mailapp")
    try:
        with (
            mock.patch.object(_mail_app, "find_one", return_value=_FAKE_MAILAPP_MSG),
            mock.patch.object(_mail_app, "archive", return_value=True) as fake_arch,
        ):
            out = _inbox.update_message(_FAKE_MAILAPP_MSG["id"], archived=True, read=True)
        assert fake_arch.called, "archived=True must dispatch to _mail_app.archive"
        assert out is not None and out["archived"] is True
        assert out["read"] is True, (
            "post-archive snapshot should report read=True so the planner "
            "can build a clean confirmation sentence"
        )
    finally:
        _restore_env(saved)
    print("ok mailapp_archive_invokes_apple_event")


def test_mailapp_archive_failure_returns_none() -> None:
    saved: dict[str, str | None] = {}
    _set_source(saved, "mailapp")
    try:
        with (
            mock.patch.object(_mail_app, "find_one", return_value=_FAKE_MAILAPP_MSG),
            mock.patch.object(_mail_app, "archive", return_value=False),
        ):
            out = _inbox.update_message(_FAKE_MAILAPP_MSG["id"], archived=True)
        assert out is None, "failed archive must propagate as None"
    finally:
        _restore_env(saved)
    print("ok mailapp_archive_failure_returns_none")


def test_mailapp_unsupported_patch_is_dropped() -> None:
    """Only ``archived`` is wired; everything else logs a warning + is ignored."""
    saved: dict[str, str | None] = {}
    _set_source(saved, "mailapp")
    try:
        with (
            mock.patch.object(_mail_app, "find_one", return_value=_FAKE_MAILAPP_MSG),
            mock.patch.object(_mail_app, "archive") as fake_arch,
        ):
            # No archived flag → archive must NOT be called.
            out = _inbox.update_message(
                _FAKE_MAILAPP_MSG["id"], starred=True, flagged=True
            )
        assert not fake_arch.called, "non-archive patches must not touch Mail.app"
        # We still return the current snapshot so the caller can chain.
        assert out is not None and out["id"] == _FAKE_MAILAPP_MSG["id"]
    finally:
        _restore_env(saved)
    print("ok mailapp_unsupported_patch_is_dropped")


def test_demo_archive_mutates_fixture_via_save() -> None:
    """The fixture path still mutates JSON; verified by patching ``save``."""
    saved: dict[str, str | None] = {}
    _set_source(saved, "demo")
    try:
        # Avoid clobbering the real fixture on disk.
        with mock.patch.object(_inbox, "save") as fake_save:
            out = _inbox.update_message("msg-003", archived=True)
        assert fake_save.called, "demo source must persist via save()"
        assert out is not None and out["archived"] is True
    finally:
        _restore_env(saved)
    print("ok demo_archive_mutates_fixture_via_save")


def main() -> None:
    test_default_source_is_mailapp()
    test_unknown_source_falls_back_to_demo()
    test_demo_source_reads_fixture()
    test_demo_source_get_message_unchanged()
    test_mailapp_source_calls_list_unread()
    test_mailapp_source_filters_unread_only()
    test_mailapp_source_get_message_dispatches_find_one()
    test_mailapp_archive_invokes_apple_event()
    test_mailapp_archive_failure_returns_none()
    test_mailapp_unsupported_patch_is_dropped()
    test_demo_archive_mutates_fixture_via_save()
    print("all mailapp_router tests passed")


if __name__ == "__main__":
    main()
