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

PLANNER_SYSTEM = """\
You are Xiexie's planner. The user is a senior speaking out loud to their Mac.

Your job: read the user's transcript and decide which named skill (if any) to
call, with what arguments. You can chain up to 3 skill calls if needed.

Hard rules:
- Speak warmly, in plain English. Avoid jargon and acronyms.
- If a skill is marked `destructive`, ask the user to confirm before calling it.
- If no skill matches, do NOT invent one. Reply with a short sentence and let
  the runtime log it to unhandled_asks.md so the linter can propose a new skill.
- When the user references a person, place, or fact, look in the WIKI below
  before asking again ("you told me Dr. Smith last week — same one?").
- For time-based skills (set_reminder), resolve natural-language times into
  ISO 8601 yourself before calling.

USER WIKI (compact projection, source of truth):

{wiki}
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
    def __init__(self, wiki: Wiki | None = None):
        self.wiki = wiki or Wiki()
        self.llm = get_provider()

    def plan(self, transcript: str, history: list[dict[str, Any]] | None = None) -> PlanResult:
        sys_prompt = PLANNER_SYSTEM.format(wiki=self.wiki.as_planner_context())
        messages: list[dict[str, Any]] = [{"role": "system", "content": sys_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": transcript})

        resp = self.llm.chat(
            messages=messages,
            tools=all_tool_schemas(),
            temperature=0.2,
            max_tokens=600,
        )

        steps: list[PlanStep] = []
        for tc in resp.tool_calls:
            try:
                args = json.loads(tc.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            skill_obj = SKILLS.get(tc["name"])
            speak_before = None
            if skill_obj and skill_obj.destructive:
                speak_before = f"I'm about to {skill_obj.description.split('.')[0].lower()}. Should I go ahead?"
            steps.append(PlanStep(skill=tc["name"], arguments=args, speak_before=speak_before))

        spoken = resp.text.strip() or (
            "Let me work on that." if steps else "I don't know how to do that yet — taking a note."
        )
        return PlanResult(speak=spoken, steps=steps, raw_text=resp.text)
