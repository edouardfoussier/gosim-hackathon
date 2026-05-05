"""Smoke tests for the WS broadcast bridge in ``xiexie.bus``.

The tests use a tiny in-memory ``send_json`` recorder so nothing actually
opens a port. Run with::

    cd backend && uv run python -m tests.test_broadcast_alert
"""

from __future__ import annotations

import asyncio
from typing import Any

from xiexie import bus
from xiexie.skills import analyze_email


class FakeClient:
    """Minimal stand-in for a Starlette ``WebSocket`` — records send_json calls."""

    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[dict[str, Any]] = []
        self.fail = fail

    async def send_json(self, payload: dict[str, Any]) -> None:
        if self.fail:
            raise RuntimeError("client dropped")
        self.sent.append(payload)


def _reset_state() -> None:
    bus._active_clients.clear()
    with analyze_email._LAST_VERDICT_LOCK:
        analyze_email._LAST_VERDICTS.clear()


def test_register_and_unregister() -> None:
    _reset_state()
    a = FakeClient()
    bus.register(a)
    assert bus.active_count() == 1
    bus.unregister(a)
    assert bus.active_count() == 0
    print("ok register_and_unregister")


def test_broadcast_alert_to_two_clients() -> None:
    _reset_state()
    a, b = FakeClient(), FakeClient()
    bus.register(a)
    bus.register(b)
    asyncio.run(bus.broadcast_alert("danger", "scam detected"))
    assert a.sent == [{"type": "alert", "level": "danger", "message": "scam detected"}], a.sent
    assert b.sent == [{"type": "alert", "level": "danger", "message": "scam detected"}], b.sent
    print("ok broadcast_alert_to_two_clients")


def test_broadcast_drops_dead_clients() -> None:
    _reset_state()
    healthy, dead = FakeClient(), FakeClient(fail=True)
    bus.register(healthy)
    bus.register(dead)
    asyncio.run(bus.broadcast_alert("warning", "look at this"))
    assert dead not in bus._active_clients
    assert healthy in bus._active_clients
    assert healthy.sent and healthy.sent[0]["level"] == "warning"
    print("ok broadcast_drops_dead_clients")


def test_pop_last_verdict_lifo() -> None:
    _reset_state()
    analyze_email._stash_verdict(
        "msg-001",
        {"verdict": "safe", "confidence": "high", "signs": ["clean"], "speak_aloud": "fine"},
    )
    analyze_email._stash_verdict(
        "msg-003",
        {
            "verdict": "phishing",
            "confidence": "high",
            "signs": ["typo domain"],
            "speak_aloud": "this is a scam",
        },
    )
    out = analyze_email.pop_last_verdict()
    assert out and out["message_id"] == "msg-003" and out["verdict"] == "phishing", out
    out2 = analyze_email.pop_last_verdict()
    assert out2 and out2["message_id"] == "msg-001", out2
    assert analyze_email.pop_last_verdict() is None
    print("ok pop_last_verdict_lifo")


def test_broadcast_verdict_levels() -> None:
    _reset_state()
    client = FakeClient()
    bus.register(client)

    cases = [
        ("phishing", "danger"),
        ("suspicious", "warning"),
        ("safe", "info"),
        ("clear", "info"),
    ]
    for verdict_label, expected_level in cases:
        client.sent.clear()
        analyze_email._stash_verdict(
            "msg-x",
            {
                "verdict": verdict_label,
                "confidence": "high",
                "signs": [f"{verdict_label} sign"],
                "speak_aloud": f"speaking about {verdict_label}",
            },
        )
        broadcasted = asyncio.run(bus.broadcast_verdict_if_any())
        assert broadcasted is True, verdict_label
        assert client.sent and client.sent[0]["level"] == expected_level, (
            verdict_label,
            client.sent,
        )
        assert verdict_label in client.sent[0]["message"]
    print("ok broadcast_verdict_levels")


def test_unclear_verdict_does_not_broadcast() -> None:
    _reset_state()
    client = FakeClient()
    bus.register(client)
    analyze_email._stash_verdict(
        "msg-y",
        {
            "verdict": "unclear",
            "confidence": "low",
            "signs": ["ambiguous"],
            "speak_aloud": "not sure",
        },
    )
    broadcasted = asyncio.run(bus.broadcast_verdict_if_any())
    assert broadcasted is False
    assert client.sent == [], client.sent
    print("ok unclear_verdict_does_not_broadcast")


def test_no_stashed_verdict_no_op() -> None:
    _reset_state()
    client = FakeClient()
    bus.register(client)
    broadcasted = asyncio.run(bus.broadcast_verdict_if_any())
    assert broadcasted is False
    assert client.sent == []
    print("ok no_stashed_verdict_no_op")


def test_stash_caps_max_entries() -> None:
    _reset_state()
    for i in range(analyze_email._MAX_STASHED_VERDICTS + 5):
        analyze_email._stash_verdict(
            f"id-{i}",
            {"verdict": "safe", "confidence": "low", "signs": [], "speak_aloud": ""},
        )
    with analyze_email._LAST_VERDICT_LOCK:
        n = len(analyze_email._LAST_VERDICTS)
    assert n == analyze_email._MAX_STASHED_VERDICTS, n
    print("ok stash_caps_max_entries")


def main() -> None:
    test_register_and_unregister()
    test_broadcast_alert_to_two_clients()
    test_broadcast_drops_dead_clients()
    test_pop_last_verdict_lifo()
    test_broadcast_verdict_levels()
    test_unclear_verdict_does_not_broadcast()
    test_no_stashed_verdict_no_op()
    test_stash_caps_max_entries()
    print("all broadcast_alert tests passed")


if __name__ == "__main__":
    main()
