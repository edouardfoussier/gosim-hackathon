"""FastAPI entry point — HTTP + WebSocket bridge to the Next.js overlay.

Endpoints:
- ``GET /health`` — sanity check
- ``GET /skills`` — list registered skills (debug)
- ``GET /wiki`` / ``GET /wiki/{slug}`` — read the wiki (debug + UI banner)
- ``POST /transcribe`` — multipart audio → text (used when the browser STT
  is disabled; primary STT happens client-side in the future)
- ``POST /plan-and-run`` — synchronous: text in → spoken reply + skill results
- ``WS  /ws`` — duplex stream for the live UI (transcript + steps + replies)
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import bus
from . import skills as _skills_pkg  # noqa: F401  # ensures registration side-effects
from .config import config
from .memory import Wiki
from .planner import Planner
from .skills import analyze_email as _analyze_email
from .skills import read_screen as _read_screen
from .skills.registry import SKILLS, call as call_skill
from .voice.realtime import (
    RealtimeSession,
    RealtimeUnavailable,
    is_available as realtime_available,
)
from .voice.stt import transcribe_bytes

# Re-export the broadcast helper so the ``backend.main`` module remains the
# documented entry point for callers who want to push their own alerts
# (e.g. the wiki linter publishing a fresh ``scam_alerts.md`` summary).
broadcast_alert = bus.broadcast_alert


# ── working-state labels ──────────────────────────────────────────────────
# Surfaced to the cursor halo and the chat status pill so Margaret sees a
# warm hint of what's happening even when Xiexie is silent. Keep them
# short (≤ 32 chars) and present-tense.
_SKILL_WORKING_LABELS: dict[str, str] = {
    "read_screen":   "looking at your screen",
    "read_emails":   "checking your inbox",
    "analyze_email": "studying that email",
    "find_file":     "searching your files",
    "open_app":      "opening the app",
    "set_reminder":  "setting your reminder",
    "zoom_text":     "adjusting the text size",
    "play_music":    "queueing the music",
    "check_wifi":    "checking your wifi",
    "check_battery": "checking the battery",
    "set_volume":    "adjusting the volume",
    "daily_brief":   "putting together your brief",
    "report_to_family": "drafting the family note",
    "narrate":       None,
}


def _label_for(skill_name: str) -> str:
    """Friendly hint for a skill, fallback to a generic phrasing."""
    label = _SKILL_WORKING_LABELS.get(skill_name)
    if label is not None:
        return label
    return f"working on {skill_name.replace('_', ' ')}"

app = FastAPI(title="Xiexie", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _warmup() -> None:
    """Pre-load the faster-whisper model in a background thread.

    Without this the first ``POST /transcribe`` call takes 8–12 s on a
    cold cache while the model downloads + loads — confusing during the
    live demo because the user sees ``transcribing…`` hang for ages.
    Warming on startup makes the first real request feel instant.
    """
    import threading

    def _load() -> None:
        try:
            from .voice import stt

            # Touch the lazy-loaded model so the heavy import happens
            # off the request hot path.
            stt._model()  # noqa: SLF001 — internal warmup call
        except Exception:  # noqa: BLE001 — warmup is best-effort
            pass

    threading.Thread(target=_load, daemon=True, name="whisper-warmup").start()


# ── lazily share one planner + wiki across requests ──────────────────────
_planner: Planner | None = None


def planner() -> Planner:
    global _planner
    if _planner is None:
        _planner = Planner()
    return _planner




# ── debug / health ────────────────────────────────────────────────────────
@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "provider": config.primary_provider(),
        "skills": list(SKILLS.keys()),
        "wiki_dir": str(config.WIKI_DIR),
    }


@app.get("/skills")
def list_skills() -> list[dict[str, Any]]:
    return [
        {"name": s.name, "description": s.description, "destructive": s.destructive, "tags": s.tags}
        for s in SKILLS.values()
    ]


@app.get("/wiki")
def list_wiki() -> dict[str, Any]:
    wiki = Wiki()
    return {"slugs": wiki.list_slugs()}


@app.get("/wiki/{slug}")
def get_wiki(slug: str) -> dict[str, Any]:
    page = Wiki().get(slug)
    if not page:
        return {"error": "not found"}
    return {"slug": page.slug, "metadata": page.metadata, "body": page.body}


# ── transcribe ────────────────────────────────────────────────────────────
@app.post("/transcribe")
async def transcribe(audio: UploadFile) -> dict[str, str]:
    data = await audio.read()
    text = transcribe_bytes(data)
    return {"text": text}


# ── continuous voice (OpenAI Realtime) ────────────────────────────────────
# The browser opens a WebRTC peer connection straight to OpenAI for
# low-latency audio. Our role on the server side is to (a) mint the
# short-lived bearer the browser hands over in its SDP exchange, and
# (b) be the function-calling tool runner — either via a parallel WS
# (``run_tool_loop``) or via the relay endpoint below when the browser
# forwards function call payloads it receives on its data channel.
_realtime_tool_loops: set[asyncio.Task[None]] = set()


@app.get("/voice/capabilities")
def voice_capabilities() -> dict[str, Any]:
    """Tell the browser whether continuous mode is wired or click-mic only."""
    return {
        "continuous": realtime_available(),
        "model": os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime"),
        "voice": os.getenv("OPENAI_REALTIME_VOICE", "marin"),
    }


@app.post("/voice/session")
async def voice_session() -> dict[str, Any]:
    """Mint an ephemeral Realtime session token for the browser.

    Also kicks off ``RealtimeSession.run_tool_loop`` as a background task —
    this is the "parallel WS" tool runner. See the docstring on
    :meth:`RealtimeSession.run_tool_loop` for the architectural caveat.
    """
    if not realtime_available():
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    session = RealtimeSession.from_skills(SKILLS)
    try:
        token = await session.mint_ephemeral_token()
    except RealtimeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — surface a useful error to the browser
        raise HTTPException(status_code=502, detail=f"OpenAI session error: {exc}") from exc

    secret = (token.get("client_secret") or {}).get("value", "")

    # Best-effort: kick off the parallel WS tool runner. Failing here
    # MUST NOT block the browser flow — the relay endpoint below covers
    # function calls if the parallel WS turns out to be unsupported.
    if secret:
        loop_task = asyncio.create_task(_run_tool_loop_safely(session, secret))
        _realtime_tool_loops.add(loop_task)
        loop_task.add_done_callback(_realtime_tool_loops.discard)

    return {
        "client_secret": secret,
        "session_id": token.get("id", ""),
        "expires_at": (token.get("client_secret") or {}).get("expires_at"),
        "model": session.model,
        "voice": session.voice,
    }


async def _run_tool_loop_safely(session: RealtimeSession, secret: str) -> None:
    try:
        await session.run_tool_loop(secret)
    except RealtimeUnavailable as exc:
        # No key / openai package missing — the browser-relay endpoint
        # picks up the slack so we just log and move on.
        bus_logger().info("realtime tool loop unavailable: %s", exc)
    except Exception:  # noqa: BLE001
        bus_logger().exception("realtime tool loop crashed")


def bus_logger():
    import logging

    return logging.getLogger("xiexie.voice.realtime")


class VoiceSpeakingRequest(BaseModel):
    """Payload for ``POST /voice/speaking`` — drives the soundwave overlay.

    Emitted ~10×/s by the browser realtime client (``app/lib/realtime.ts``)
    while Marin is producing audio. ``level`` is the RMS amplitude on a
    ``0..1`` scale; the field is optional so the simplest "Marin is /
    isn't speaking" wiring (one ``start`` + one ``stop``) still works
    and the overlay falls back to its procedural sine animation.
    """

    state: str  # "start" | "stop"
    level: float | None = None


@app.post("/voice/speaking", status_code=204)
async def voice_speaking(req: VoiceSpeakingRequest):
    """Forward a speaking-state event to every WS subscriber.

    Internal/loopback only — the browser hits this from the same machine
    while gpt-realtime audio plays. No auth gate (the FastAPI process
    binds 127.0.0.1 in production via uvicorn's ``--host`` arg).
    """
    state = (req.state or "").strip().lower()
    if state not in {"start", "stop"}:
        raise HTTPException(
            status_code=422, detail=f"unknown state {state!r}; expected start|stop"
        )

    level = req.level
    if level is not None:
        try:
            level = max(0.0, min(1.0, float(level)))
        except (TypeError, ValueError):
            level = None

    await bus.broadcast_speaking(state, level)
    # 204 No Content — nothing to return; the WS push is the side-effect.
    return None


class VoiceToolRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = {}
    call_id: str | None = None


@app.post("/voice/tool")
async def voice_tool(req: VoiceToolRequest) -> dict[str, Any]:
    """Run a single Xiexie skill on behalf of the browser's data channel.

    The browser receives ``response.function_call_arguments.done`` events
    over the WebRTC data channel, forwards them here, and pipes the
    result back into the conversation as a ``function_call_output`` item.
    This is the path that actually works end-to-end today (the parallel
    WS in ``/voice/session`` is best-effort).
    """
    session = RealtimeSession.from_skills(SKILLS)
    label = _label_for(req.name)
    await bus.broadcast_working("start", label)
    try:
        output, ok = await session.dispatch_function_call(req.name, req.arguments)
    finally:
        await bus.broadcast_working("stop")

    if req.name == "analyze_email" and ok:
        await bus.broadcast_verdict_if_any()
    if req.name == "read_screen" and ok:
        # Fan out any [POINT:x,y|label] hints emitted by GLM-4.5V into
        # the spoken reply; the overlay (PyQt6 PointerOverlay) and the
        # in-browser arrow both subscribe and animate to the target.
        for pt in _read_screen.pop_last_points():
            await bus.broadcast_point(
                int(pt["x"]), int(pt["y"]), pt.get("label")
            )

    return {"call_id": req.call_id or "", "ok": ok, "output": output}


# ── plan-and-run (synchronous) ────────────────────────────────────────────
class PlanRunRequest(BaseModel):
    text: str
    history: list[dict[str, Any]] = []


@app.post("/plan-and-run")
async def plan_and_run(req: PlanRunRequest) -> dict[str, Any]:
    # Light-up the cursor halo while the planner thinks — first GLM-4.6
    # round-trip can be 1-2 s and Margaret should see the agent is busy.
    await bus.broadcast_working("start", "thinking")
    try:
        plan = await asyncio.to_thread(planner().plan, req.text, req.history)
    finally:
        await bus.broadcast_working("stop")

    results: list[dict[str, Any]] = []
    followup_prompt: str | None = None
    for step in plan.steps:
        label = _label_for(step.skill)
        await bus.broadcast_working("start", label)
        try:
            output = await asyncio.to_thread(call_skill, step.skill, step.arguments)
            results.append({"skill": step.skill, "args": step.arguments, "result": output})
            # Money-shot bridge: when ``analyze_email`` finishes, fan out
            # the verdict to every overlay subscriber on /ws.
            if step.skill == "analyze_email":
                await bus.broadcast_verdict_if_any()
                # Surface the chained follow-up question so HTTP callers
                # (smoke tests, the demo CLI) can prompt the user in-line
                # — same data the WS endpoint sends as a ``confirm`` frame.
                followup = _analyze_email.peek_followup()
                if followup and followup.get("prompt_user"):
                    followup_prompt = followup["prompt_user"]
            if step.skill == "read_screen":
                for pt in _read_screen.pop_last_points():
                    await bus.broadcast_point(
                        int(pt["x"]), int(pt["y"]), pt.get("label")
                    )
        except Exception as exc:  # noqa: BLE001
            results.append(
                {"skill": step.skill, "args": step.arguments, "error": str(exc)}
            )
        finally:
            await bus.broadcast_working("stop")
    payload: dict[str, Any] = {
        "speak": plan.speak,
        "steps": results,
        "raw": plan.raw_text,
    }
    if followup_prompt:
        payload["confirm"] = followup_prompt
    return payload


# ── WebSocket: live UI ────────────────────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    bus.register(ws)
    try:
        while True:
            payload_raw = await ws.receive_text()
            try:
                payload = json.loads(payload_raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "invalid JSON"})
                continue

            kind = payload.get("type")
            if kind == "ping":
                await ws.send_json({"type": "pong"})
                continue

            if kind == "user_text":
                text = (payload.get("text") or "").strip()
                history = payload.get("history") or []
                if not text:
                    await ws.send_json({"type": "error", "message": "empty text"})
                    continue

                await ws.send_json({"type": "transcript", "text": text})

                # plan (cursor halo: thinking)
                await bus.broadcast_working("start", "thinking")
                try:
                    plan = await asyncio.to_thread(planner().plan, text, history)
                finally:
                    await bus.broadcast_working("stop")
                await ws.send_json({"type": "speak", "text": plan.speak})

                # execute steps in order, streaming results
                for step in plan.steps:
                    if step.speak_before:
                        await ws.send_json({"type": "confirm", "text": step.speak_before})
                    await ws.send_json(
                        {"type": "skill_start", "name": step.skill, "args": step.arguments}
                    )
                    label = _label_for(step.skill)
                    await bus.broadcast_working("start", label)
                    try:
                        result = await asyncio.to_thread(
                            call_skill, step.skill, step.arguments
                        )
                        await ws.send_json(
                            {"type": "skill_result", "name": step.skill, "result": result}
                        )
                        # Read-style skills should be spoken aloud — the
                        # planner's preamble was just "Let me check…" and
                        # the Margaret-friendly summary lives in the
                        # skill result. ``analyze_email`` is excluded
                        # because the verdict bus already broadcasts a
                        # spoken alert with the warm GLM-4.6 paragraph.
                        if step.skill in {"read_emails", "find_file", "daily_brief"}:
                            await ws.send_json({"type": "speak", "text": result})
                        # Money-shot bridge: when ``analyze_email`` finishes,
                        # fan out the verdict to every overlay subscriber so
                        # the warning halo lights up automatically.
                        if step.skill == "read_screen":
                            for pt in _read_screen.pop_last_points():
                                await bus.broadcast_point(
                                    int(pt["x"]), int(pt["y"]), pt.get("label")
                                )
                        if step.skill == "analyze_email":
                            await bus.broadcast_verdict_if_any()
                            # Chained follow-up (Upgrade A): if the verdict
                            # was phishing/suspicious, ``analyze_email``
                            # stashed a suggestion to alert the family.
                            # Render it as a ``confirm`` bubble *before*
                            # the ``done`` frame so the panel asks Margaret
                            # in-line — a short "yes" then triggers the
                            # planner's early-return path.
                            followup = _analyze_email.peek_followup()
                            if followup and followup.get("prompt_user"):
                                await ws.send_json(
                                    {"type": "confirm", "text": followup["prompt_user"]}
                                )
                    except Exception as exc:  # noqa: BLE001
                        await ws.send_json(
                            {"type": "skill_error", "name": step.skill, "error": str(exc)}
                        )
                    finally:
                        await bus.broadcast_working("stop")

                await ws.send_json({"type": "done"})
                continue

            await ws.send_json({"type": "error", "message": f"unknown type {kind!r}"})

    except WebSocketDisconnect:
        return
    finally:
        bus.unregister(ws)
