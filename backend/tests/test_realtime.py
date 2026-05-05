"""Smoke test for the OpenAI Realtime wiring.

Validates three things without touching the network:

1. ``RealtimeSession.from_skills(SKILLS)`` produces a ``tools`` array
   that exposes every registered skill (currently 13 — see ``SKILLS``).
2. The ephemeral session payload sent to ``/v1/realtime/sessions`` has
   the expected shape (model, voice, instructions present).
3. A synthetic ``response.function_call_arguments.done`` event routes
   through ``RealtimeSession.dispatch_function_call`` and lands on
   ``xiexie.skills.registry.call``.

Run::

    cd backend
    uv run python tests/test_realtime.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Allow ``uv run python tests/test_realtime.py`` from the backend folder
# to import the package without installing in editable mode.
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from xiexie.skills import SKILLS  # noqa: E402
from xiexie.voice import realtime  # noqa: E402
from xiexie.voice.realtime import RealtimeSession  # noqa: E402


# ─── 1. tools payload covers every registered skill ─────────────────────────
def test_tools_payload_covers_all_skills() -> None:
    session = RealtimeSession.from_skills(SKILLS)
    tools = session.tools_payload()
    names = {t["name"] for t in tools}
    expected = set(SKILLS.keys())
    assert names == expected, f"missing tools: {expected - names}"
    assert len(tools) == len(SKILLS), "duplicate or missing tools"
    assert len(tools) >= 13, f"expected at least 13 skills, got {len(tools)}"

    # Realtime API uses the *flat* function shape, not the nested
    # chat-completions shape (see RealtimeSession.tools_payload docstring).
    for tool in tools:
        assert tool["type"] == "function"
        assert "name" in tool and "description" in tool and "parameters" in tool
        assert "function" not in tool, "must be the flat realtime shape"


# ─── 2. ephemeral session payload shape ─────────────────────────────────────
def test_ephemeral_session_payload_shape() -> None:
    session = RealtimeSession.from_skills(
        SKILLS, voice="marin", model="gpt-realtime", api_key="sk-test-fake"
    )

    captured: dict[str, object] = {}

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "id": "sess_fake_123",
                "object": "realtime.session",
                "model": "gpt-realtime",
                "voice": "marin",
                "client_secret": {
                    "value": "ek_fake_xyz",
                    "expires_at": 1_750_000_000,
                },
            }

    class _Client:
        async def post(self, url: str, *, json, headers):  # noqa: A002 — keyword name fixed by httpx
            captured["url"] = url
            captured["payload"] = json
            captured["headers"] = headers
            return _Resp()

        async def aclose(self) -> None:
            return None

    response = asyncio.run(session.mint_ephemeral_token(http_client=_Client()))

    assert captured["url"] == realtime.OPENAI_SESSIONS_URL
    headers = captured["headers"]
    assert headers["Authorization"] == "Bearer sk-test-fake"
    assert headers["Content-Type"] == "application/json"

    payload = captured["payload"]
    assert payload["model"] == "gpt-realtime"
    assert payload["voice"] == "marin"
    assert "instructions" in payload and payload["instructions"], "system prompt missing"
    # Tools must travel with the session creation so the browser's WebRTC
    # negotiation already knows about them.
    assert isinstance(payload["tools"], list) and len(payload["tools"]) == len(SKILLS)
    assert payload["tool_choice"] == "auto"
    assert payload["turn_detection"] == {"type": "server_vad"}

    assert response["client_secret"]["value"] == "ek_fake_xyz"
    assert response["id"] == "sess_fake_123"


# ─── 3. dispatcher routes to xiexie.skills.registry.call ────────────────────
def test_dispatcher_routes_function_call() -> None:
    session = RealtimeSession.from_skills(SKILLS)

    captured_args: dict[str, object] = {}

    def _fake_call(name: str, arguments: dict[str, object]) -> str:
        captured_args["name"] = name
        captured_args["arguments"] = dict(arguments)
        return "OK from fake skill"

    with patch("xiexie.voice.realtime.call_skill", side_effect=_fake_call):
        # Synthetic event mirroring the real payload shape OpenAI sends
        # on ``response.function_call_arguments.done``.
        synthetic_event = {
            "type": "response.function_call_arguments.done",
            "name": "open_app",
            "call_id": "call_fake_123",
            "arguments": json.dumps({"name": "Mail"}),
        }

        # Fake the WS connection so we can verify the function output is
        # piped back into the conversation.
        conn = MagicMock()
        conn.conversation = MagicMock()
        conn.conversation.item = MagicMock()
        conn.conversation.item.create = AsyncMock()
        conn.response = MagicMock()
        conn.response.create = AsyncMock()

        asyncio.run(session._dispatch_event(conn, synthetic_event))

    assert captured_args.get("name") == "open_app"
    assert captured_args.get("arguments") == {"name": "Mail"}

    create_call = conn.conversation.item.create.await_args
    assert create_call is not None, "function_call_output never sent back to OpenAI"
    sent_item = create_call.kwargs["item"]
    assert sent_item["type"] == "function_call_output"
    assert sent_item["call_id"] == "call_fake_123"
    assert sent_item["output"] == "OK from fake skill"
    conn.response.create.assert_awaited_once()


def test_dispatcher_handles_unknown_skill() -> None:
    session = RealtimeSession.from_skills(SKILLS)
    output, ok = asyncio.run(
        session.dispatch_function_call("not_a_real_skill", {"foo": "bar"})
    )
    assert ok is False
    parsed = json.loads(output)
    assert "error" in parsed and "not_a_real_skill" in parsed["error"]


def main() -> None:
    test_tools_payload_covers_all_skills()
    test_ephemeral_session_payload_shape()
    test_dispatcher_routes_function_call()
    test_dispatcher_handles_unknown_skill()
    print("ok realtime tests passed")


if __name__ == "__main__":
    main()
