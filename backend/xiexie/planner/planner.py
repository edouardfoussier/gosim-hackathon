"""Planner — turn a voice transcript into a sequence of skill calls.

V1 strategy: single-turn tool-calling against GLM-4.6. The system prompt
gives the planner:
- the user's wiki (compact projection from ``Wiki.as_planner_context``)
- the registered skills (auto-serialised to OpenAI tool schemas)
- guardrails on confirmations and tone

Output: zero or more ``PlanStep`` items. The runtime executes them in order,
inserting confirmation prompts for ``destructive`` skills.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..llm import get_provider
from ..memory import Wiki
from ..skills import SKILLS
from ..skills.registry import all_tool_schemas

# Sentinel tool: GLM-5.1 on the GOSIM proxy ignores ``tool_choice="auto"``
# and never dispatches when given the choice — it always narrates instead.
# We force ``tool_choice="required"`` and add this no-op sentinel so the
# model has a clean way to say "no skill matches" without inventing one.
_NARRATE_TOOL = {
    "type": "function",
    "function": {
        "name": "narrate",
        "description": (
            "Use ONLY when no other tool matches the user's request. "
            "This emits a short spoken reply WITHOUT taking any action. "
            "Never use this for requests that match a real skill."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reply": {
                    "type": "string",
                    "description": "One-sentence spoken reply to the user.",
                }
            },
            "required": ["reply"],
        },
    },
}

PLANNER_SYSTEM = """\
You are Xiexie's planner. The user is a senior speaking out loud to their Mac.

# Tone
Warm, plain English, no jargon, no acronyms.

# USER WIKI (compact projection, source of truth)

{wiki}

# CRITICAL — TOOL DISPATCH (read carefully, this is the most important part)

You **act through tools**, never through narration. If the user's request
matches any registered skill, you MUST emit a tool_call for that skill.

The text you return is **only** the SPOKEN preamble the user hears *while*
the tool runs (e.g. "Sure, let me take a look…"). It is NOT a description
of what you are about to do, and it is NOT a substitute for emitting a
tool_call.

CORRECT examples:
- User: "Did I get any new emails?"
  → tool_call(read_emails)  +  speak: "Let me check."
- User: "Take a closer look at the suspicious one."
  → tool_call(analyze_email, message_id="msg-003")  +  speak: "On it."
- User: "Open WhatsApp."
  → tool_call(open_app, name="WhatsApp")  +  speak: "Opening WhatsApp."
- User: "Set a reminder for 3 pm to call Lisa."
  → tool_call(set_reminder, what="Call Lisa", when_iso="2026-05-05T15:00:00")
    + speak: "Reminder set."

INCORRECT (never do this):
- speak: "I'll analyze that email for you right away."  (WHERE IS THE TOOL CALL?)
- speak: "Let me check your inbox."  (WHERE IS THE TOOL CALL?)

# Other hard rules

- If a skill is marked `destructive`, briefly ask the user to confirm
  before emitting the tool_call (single short question; you still emit
  the call when they say yes on the next turn).
- If no skill matches, do NOT invent one. Reply with one short sentence
  so the runtime can log it for the linter to propose a new skill.
- When the user references a person, place, or fact, look in the WIKI
  above before asking again ("you told me Dr. Smith last week — same
  one?").
- For time-based skills, resolve natural-language times into ISO 8601
  yourself before calling.
- You may chain up to 3 skill calls in one turn.
"""


@dataclass
class PlanStep:
    skill: str
    arguments: dict[str, Any]
    speak_before: str | None = None  # optional confirmation/preamble


@dataclass
class PlanResult:
    speak: str  # what Xiexie should say (TTS)
    steps: list[PlanStep]
    raw_text: str


class Planner:
    def __init__(self, wiki: Wiki | None = None, dispatch_model: str | None = None):
        self.wiki = wiki or Wiki()
        self.llm = get_provider()
        # On direct Z.AI (``api.z.ai/api/paas/v4``) GLM-4.6 dispatches
        # tool_calls cleanly — no override needed. The GOSIM proxy
        # (``api.r9s.ai/v1``) has a buggy tool-call relay for GLM, so on
        # that base URL we route the planner through DeepSeek-V4-Pro
        # which dispatches every skill reliably. ``XIEXIE_PLANNER_MODEL``
        # forces a specific dispatch model regardless of base URL.
        import os

        base_url = str(getattr(self.llm.client, "base_url", "")).lower()
        proxy_dispatch_default = (
            "deepseek-v4-pro" if "r9s.ai" in base_url else None
        )
        self.dispatch_model = (
            dispatch_model
            or os.getenv("XIEXIE_PLANNER_MODEL")
            or proxy_dispatch_default
        )

    def plan(self, transcript: str, history: list[dict[str, Any]] | None = None) -> PlanResult:
        sys_prompt = PLANNER_SYSTEM.format(wiki=self.wiki.as_planner_context())
        messages: list[dict[str, Any]] = [{"role": "system", "content": sys_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": transcript})

        # Tool list = real skills + the narrate sentinel.
        tools = all_tool_schemas() + [_NARRATE_TOOL]

        # On Z.AI proxies (GLM-5.x) ``tool_choice="auto"`` reliably yields
        # narration with no tool_calls. Forcing ``required`` + the
        # ``narrate`` sentinel gives the model a clean escape hatch.
        choice = "required" if self.llm.name == "zai" else "auto"

        resp = self.llm.chat(
            messages=messages,
            tools=tools,
            temperature=0.2,
            max_tokens=600,
            tool_choice=choice,
            model=self.dispatch_model,
        )

        steps: list[PlanStep] = []
        narrate_reply: str | None = None

        for tc in resp.tool_calls:
            try:
                args = json.loads(tc.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}

            if tc["name"] == "narrate":
                narrate_reply = str(args.get("reply") or "").strip()
                continue

            skill_obj = SKILLS.get(tc["name"])
            if skill_obj is None:
                continue  # ignore hallucinated tool names

            speak_before = None
            if skill_obj.destructive:
                speak_before = f"I'm about to {skill_obj.description.split('.')[0].lower()}. Should I go ahead?"
            steps.append(PlanStep(skill=tc["name"], arguments=args, speak_before=speak_before))

        # Order of preference for the spoken reply:
        # 1. Real text from the model (rare on GLM in required mode)
        # 2. The narrate sentinel's reply
        # 3. Default preamble depending on whether we have steps to run
        spoken = (
            resp.text.strip()
            or narrate_reply
            or ("Let me work on that." if steps else "I don't know how to do that yet — taking a note.")
        )
        return PlanResult(speak=spoken, steps=steps, raw_text=resp.text)
