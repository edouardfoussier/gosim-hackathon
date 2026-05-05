"""OpenAI Realtime (gpt-realtime) wrapper, wired to the Xiexie skill registry.

The class mirrors the pattern in the user's own ``madeleine-agent``
(``app/realtime/openai_realtime.py``) but adapted to our needs:

* tools are taken from ``xiexie.skills.SKILLS`` via ``Skill.to_tool_schema``
  so voice and text mode dispatch the **same** 13 skills
* the system prompt projects ``Wiki.as_planner_context`` so the voice
  loop knows about Margaret, Lisa, Aetna, etc., exactly like the typed
  planner does
* the dispatcher delegates to ``xiexie.skills.registry.call``, the same
  entry point used by ``/plan-and-run`` and ``/ws``

Two transports are supported because the brief asks for the WebRTC
flavour (browser ↔ OpenAI for low-latency audio) while still wanting
the backend to be the function-calling tool runner:

1. ``mint_ephemeral_token`` POSTs to ``/v1/realtime/sessions`` with the
   tools + voice + instructions baked in. The browser uses the returned
   ``client_secret`` to negotiate a WebRTC peer connection.
2. ``run_tool_loop`` opens a parallel WebSocket (or accepts function
   call payloads relayed by the browser through HTTP) and dispatches
   ``response.function_call_arguments.done`` events to the local skill
   registry.

Both paths funnel through ``dispatch_function_call`` so the unit test
can verify wiring without touching the network.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..config import config
from ..memory import Wiki
from ..skills import SKILLS
from ..skills.registry import Skill, call as call_skill

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Defaults — also surfaced in .env.example so demo machines can override.
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_MODEL = "gpt-realtime"
DEFAULT_VOICE = "marin"
"""``marin`` is the warm GA voice OpenAI recommends. Margaret-friendly."""

OPENAI_SESSIONS_URL = "https://api.openai.com/v1/realtime/sessions"
OPENAI_REALTIME_WS = "wss://api.openai.com/v1/realtime"

VOICE_PROMPT_ADDENDUM = """\

# Voice mode (the user is speaking aloud — you reply by speaking back)

- Keep replies short, warm, plain English. No markdown, no bullet lists.
- When you're about to call a tool, say a brief preamble out loud first
  ("Of course, let me check…") so the user doesn't sit in silence.
- For destructive skills, ask one short spoken question before doing it.
- Never claim you've taken an action unless the corresponding tool
  actually returned. If a tool errored, say so plainly.
"""


PLANNER_SYSTEM_TEMPLATE = """\
You are Xiexie, the AI grandchild for {persona}. The user is a senior speaking
out loud to their Mac; you reply in a warm, plain-English voice.

# USER WIKI (compact projection, source of truth)

{wiki}

# CRITICAL — TOOL DISPATCH

You **act through tools**, never through narration. If the user's request
matches any registered skill, you MUST emit a function call for that skill.
The text you say out loud is only the warm preamble the user hears WHILE
the tool runs. It is NOT a substitute for the call.

CORRECT
- "Did I get any new emails?" → speak: "Let me check." + read_emails()
- "Take a closer look at the suspicious one." → speak: "On it." +
  analyze_email(message_id="msg-003")
- "Open Mail." → speak: "Opening Mail." + open_app(name="Mail")
- "Set a reminder for 3 pm to call Lisa." → speak: "Reminder set." +
  set_reminder(what="Call Lisa", when_iso="2026-05-05T15:00:00")

INCORRECT
- speak: "I'll check your inbox now." (WHERE IS THE TOOL CALL?)

# Other rules
- For destructive skills, briefly ask the user to confirm out loud first.
- If no skill matches, reply with one short sentence so the runtime can
  log it for the linter to propose a new skill.
- Resolve natural-language times into ISO 8601 yourself.
- You may chain up to 3 skill calls per turn.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Type aliases — the WebRTC flow doesn't need most of these but we mirror
# the madeleine-agent shape so a UI consumer can plug into the same hooks.
# ─────────────────────────────────────────────────────────────────────────────

AsyncToolCallback = Callable[[str, dict[str, Any]], Awaitable[None]]
AsyncToolResultCallback = Callable[[str, str, bool], Awaitable[None]]
AsyncTextCallback = Callable[[str], Awaitable[None]]
AsyncErrorCallback = Callable[[str], Awaitable[None]]


@dataclass
class VoiceCallbacks:
    """Optional async hooks fired during a Realtime session."""

    on_tool_started: AsyncToolCallback | None = None
    on_tool_finished: AsyncToolResultCallback | None = None
    on_error: AsyncErrorCallback | None = None
    on_assistant_transcript_done: AsyncTextCallback | None = None
    on_user_transcript_done: AsyncTextCallback | None = None


class RealtimeUnavailable(RuntimeError):
    """Raised when the realtime endpoint cannot be used (no API key, etc.)."""


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class RealtimeSession:
    """One Xiexie ↔ OpenAI Realtime session.

    Construct via :meth:`from_skills` so the tools payload is built from
    the registered skill set automatically. Then either::

        # Browser-side WebRTC: just mint the ephemeral key
        token = await session.mint_ephemeral_token()

        # Backend-side WS (parallel) for tool dispatch
        await session.run_tool_loop(token["client_secret"]["value"])

    Both paths share :meth:`dispatch_function_call`, which is the only
    thing the test suite needs to exercise.
    """

    skills: dict[str, Skill]
    voice: str = DEFAULT_VOICE
    model: str = DEFAULT_MODEL
    instructions: str = ""
    callbacks: VoiceCallbacks = field(default_factory=VoiceCallbacks)
    tool_choice: str = "auto"
    api_key: str | None = None

    # runtime state — populated by ``run_tool_loop``
    _stop: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)

    # ── construction ──────────────────────────────────────────────────────

    @classmethod
    def from_skills(
        cls,
        skills: dict[str, Skill] | None = None,
        *,
        voice: str | None = None,
        model: str | None = None,
        instructions: str | None = None,
        api_key: str | None = None,
    ) -> RealtimeSession:
        """Build a session whose ``tools`` mirror the live skill registry.

        ``instructions`` defaults to the Wiki-projecting planner prompt so
        the voice loop talks to Margaret with the same grounding the
        text planner uses. Pass an explicit string to override.
        """
        skills = skills if skills is not None else dict(SKILLS)
        return cls(
            skills=skills,
            voice=(voice or os.getenv("OPENAI_REALTIME_VOICE") or DEFAULT_VOICE),
            model=(model or os.getenv("OPENAI_REALTIME_MODEL") or DEFAULT_MODEL),
            instructions=instructions if instructions is not None else cls.default_system_prompt(),
            api_key=api_key or config.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY"),
        )

    @staticmethod
    def default_system_prompt(persona: str = "Margaret") -> str:
        """Return the Wiki-projecting system prompt used by the planner.

        Reuses ``Wiki.as_planner_context`` so the realtime loop has the
        same memory the typed planner does. Best-effort: if the wiki
        directory is missing in the test environment we degrade to a
        bare prompt without exploding.
        """
        try:
            wiki_text = Wiki().as_planner_context()
        except Exception:  # noqa: BLE001 — wiki is best-effort here
            wiki_text = "(wiki unavailable)"
        body = PLANNER_SYSTEM_TEMPLATE.format(persona=persona, wiki=wiki_text)
        return body + VOICE_PROMPT_ADDENDUM

    # ── tools payload ─────────────────────────────────────────────────────

    def tools_payload(self) -> list[dict[str, Any]]:
        """Translate ``Skill.to_tool_schema()`` to the Realtime tool shape.

        The Realtime API uses the *flat* function shape (``type``, ``name``,
        ``description``, ``parameters``) — NOT the nested
        ``{"type":"function","function":{…}}`` shape used by the chat
        completions API. ``Skill.to_tool_schema`` returns the latter, so
        we unwrap it here.
        """
        out: list[dict[str, Any]] = []
        for skill in self.skills.values():
            schema = skill.to_tool_schema()
            fn = schema.get("function", {})
            out.append(
                {
                    "type": "function",
                    "name": fn.get("name", skill.name),
                    "description": fn.get("description", skill.description),
                    "parameters": fn.get(
                        "parameters", {"type": "object", "properties": {}}
                    ),
                }
            )
        return out

    def session_payload(self) -> dict[str, Any]:
        """Body used both for ``/v1/realtime/sessions`` and ``session.update``."""
        return {
            "model": self.model,
            "voice": self.voice,
            "modalities": ["audio", "text"],
            "instructions": self.instructions,
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "input_audio_transcription": {"model": "whisper-1"},
            "turn_detection": {"type": "server_vad"},
            "tools": self.tools_payload(),
            "tool_choice": self.tool_choice,
        }

    # ── REST: ephemeral token ─────────────────────────────────────────────

    async def mint_ephemeral_token(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        """POST to ``/v1/realtime/sessions`` and return the JSON response.

        The returned ``client_secret.value`` is a short-lived bearer the
        browser passes in its WebRTC SDP exchange. We never expose the
        long-lived ``OPENAI_API_KEY`` to the browser.

        Raises :class:`RealtimeUnavailable` when the API key is missing
        so the caller can degrade to the click-mic fallback.
        """
        if not self.api_key:
            raise RealtimeUnavailable(
                "OPENAI_API_KEY is not set — cannot mint a Realtime ephemeral token."
            )

        payload = self.session_payload()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # The Realtime API gates GA features behind the v1 beta header
            # at the time of writing; harmless once it is removed.
            "OpenAI-Beta": "realtime=v1",
        }

        owns_client = http_client is None
        client = http_client or httpx.AsyncClient(timeout=30.0)
        try:
            resp = await client.post(OPENAI_SESSIONS_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        finally:
            if owns_client:
                await client.aclose()

        # Defensive: surface a helpful error if the shape changed.
        if not isinstance(data, dict) or "client_secret" not in data:
            raise RealtimeUnavailable(
                f"Unexpected /v1/realtime/sessions response: {data!r}"
            )
        return data

    # ── WebSocket: backend tool loop (optional, parallel to WebRTC) ───────

    async def run_tool_loop(self, ephemeral_secret: str) -> None:
        """Listen for ``response.function_call_arguments.done`` events.

        Architecture caveat — see CLAUDE.md ADR for full notes:
        OpenAI Realtime sessions are normally single-client, so opening a
        backend WS while the browser is also connected via WebRTC may not
        work end-to-end without the relay variant (see ``/voice/tool``).
        We still ship this loop because:
          - it is the canonical pattern when the backend owns the audio
            (no WebRTC), e.g. for the smoke-test CLI; and
          - it documents intent in code so a future direct OpenAI key
            with multi-client sessions plugs in cleanly.
        """
        if not self.api_key:
            raise RealtimeUnavailable("OPENAI_API_KEY is not set.")

        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover — declared dep
            raise RealtimeUnavailable(
                "openai package is required for the realtime tool loop"
            ) from exc

        client = AsyncOpenAI(api_key=self.api_key)
        logger.info("Opening backend Realtime tool loop model=%s", self.model)
        async with client.realtime.connect(model=self.model) as conn:
            with contextlib.suppress(Exception):
                await conn.session.update(session=self.session_payload())
            async for event in conn:
                if self._stop.is_set():
                    break
                try:
                    await self._dispatch_event(conn, event)
                except Exception:  # noqa: BLE001 — never let one bad event kill the loop
                    logger.exception(
                        "Failed to dispatch realtime event type=%s",
                        getattr(event, "type", "?"),
                    )
        logger.info("Backend Realtime tool loop finished")

    def stop(self) -> None:
        """Signal :meth:`run_tool_loop` to break out at the next event."""
        self._stop.set()

    # ── Event dispatch ────────────────────────────────────────────────────

    async def _dispatch_event(self, conn: Any, event: Any) -> None:
        """Route a raw realtime event to the right handler."""
        etype = getattr(event, "type", "") or (
            event.get("type", "") if isinstance(event, dict) else ""
        )

        if etype == "response.function_call_arguments.done":
            name = self._event_attr(event, "name") or ""
            call_id = self._event_attr(event, "call_id") or ""
            raw_args = self._event_attr(event, "arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except (json.JSONDecodeError, TypeError):
                args = {}
            result, ok = await self.dispatch_function_call(name, args)
            await self._send_function_output(conn, call_id, result)
            return

        if etype == "response.audio_transcript.done":
            transcript = self._event_attr(event, "transcript") or ""
            await _safe_cb(self.callbacks.on_assistant_transcript_done, transcript)
            return

        if etype == "conversation.item.input_audio_transcription.completed":
            transcript = self._event_attr(event, "transcript") or ""
            await _safe_cb(self.callbacks.on_user_transcript_done, transcript)
            return

        if etype == "error":
            err = self._event_attr(event, "error") or {}
            msg = (
                getattr(err, "message", None)
                or (err.get("message") if isinstance(err, dict) else None)
                or "unknown realtime error"
            )
            await _safe_cb(self.callbacks.on_error, str(msg))
            return

        # All other event types are consumed elsewhere (audio playback on
        # the browser via WebRTC, transcript display, …). We just log.
        logger.debug("Unhandled realtime event type=%s", etype)

    @staticmethod
    def _event_attr(event: Any, name: str) -> Any:
        if isinstance(event, dict):
            return event.get(name)
        return getattr(event, name, None)

    async def dispatch_function_call(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> tuple[str, bool]:
        """Run a registered skill in a thread and return ``(result, ok)``.

        This is the **single chokepoint** every transport (WS, WebRTC
        relay, smoke test) calls into. The returned string is what gets
        sent back to OpenAI as ``function_call_output``.
        """
        await _safe_cb(self.callbacks.on_tool_started, name, arguments)

        if name not in self.skills and name not in SKILLS:
            err = f"unknown skill {name!r}"
            await _safe_cb(self.callbacks.on_tool_finished, name, err, False)
            return json.dumps({"error": err}), False

        try:
            output = await asyncio.to_thread(call_skill, name, arguments)
        except Exception as exc:  # noqa: BLE001 — feed the error back to the LLM
            err_payload = json.dumps(
                {"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False
            )
            await _safe_cb(self.callbacks.on_tool_finished, name, str(exc), False)
            return err_payload, False

        result_str = output if isinstance(output, str) else json.dumps(
            output, ensure_ascii=False, default=str
        )
        await _safe_cb(self.callbacks.on_tool_finished, name, result_str, True)
        return result_str, True

    async def _send_function_output(self, conn: Any, call_id: str, output: str) -> None:
        """Forward the tool result to OpenAI and ask for a follow-up response."""
        if conn is None or not call_id:
            return
        with contextlib.suppress(Exception):
            await conn.conversation.item.create(
                item={
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": output,
                }
            )
            await conn.response.create()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def is_available() -> bool:
    """Cheap capability check — used by ``/voice/session`` to gate the route."""
    return bool(config.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY"))


async def _safe_cb(cb: Callable[..., Awaitable[None]] | None, *args: Any) -> None:
    if cb is None:
        return
    try:
        await cb(*args)
    except Exception:  # noqa: BLE001 — UI bugs must not kill the audio stream
        logger.exception("Voice callback raised")
