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
from typing import Any

from fastapi import FastAPI, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import bus
from . import skills as _skills_pkg  # noqa: F401  # ensures registration side-effects
from .config import config
from .memory import Wiki
from .planner import Planner
from .skills.registry import SKILLS, call as call_skill
from .voice.stt import transcribe_bytes

# Re-export the broadcast helper so the ``backend.main`` module remains the
# documented entry point for callers who want to push their own alerts
# (e.g. the wiki linter publishing a fresh ``scam_alerts.md`` summary).
broadcast_alert = bus.broadcast_alert

app = FastAPI(title="Xiexie", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


# ── plan-and-run (synchronous) ────────────────────────────────────────────
class PlanRunRequest(BaseModel):
    text: str
    history: list[dict[str, Any]] = []


@app.post("/plan-and-run")
def plan_and_run(req: PlanRunRequest) -> dict[str, Any]:
    plan = planner().plan(req.text, history=req.history)
    results: list[dict[str, Any]] = []
    for step in plan.steps:
        try:
            output = call_skill(step.skill, step.arguments)
            results.append({"skill": step.skill, "args": step.arguments, "result": output})
        except Exception as exc:  # noqa: BLE001
            results.append(
                {"skill": step.skill, "args": step.arguments, "error": str(exc)}
            )
    return {"speak": plan.speak, "steps": results, "raw": plan.raw_text}


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

                # plan
                plan = await asyncio.to_thread(planner().plan, text, history)
                await ws.send_json({"type": "speak", "text": plan.speak})

                # execute steps in order, streaming results
                for step in plan.steps:
                    if step.speak_before:
                        await ws.send_json({"type": "confirm", "text": step.speak_before})
                    await ws.send_json(
                        {"type": "skill_start", "name": step.skill, "args": step.arguments}
                    )
                    try:
                        result = await asyncio.to_thread(
                            call_skill, step.skill, step.arguments
                        )
                        await ws.send_json(
                            {"type": "skill_result", "name": step.skill, "result": result}
                        )
                        # Money-shot bridge: when ``analyze_email`` finishes,
                        # fan out the verdict to every overlay subscriber so
                        # the warning halo lights up automatically.
                        if step.skill == "analyze_email":
                            await bus.broadcast_verdict_if_any()
                    except Exception as exc:  # noqa: BLE001
                        await ws.send_json(
                            {"type": "skill_error", "name": step.skill, "error": str(exc)}
                        )

                await ws.send_json({"type": "done"})
                continue

            await ws.send_json({"type": "error", "message": f"unknown type {kind!r}"})

    except WebSocketDisconnect:
        return
    finally:
        bus.unregister(ws)
