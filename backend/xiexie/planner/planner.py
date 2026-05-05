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
import random
import re
from dataclasses import dataclass
from typing import Any

from ..llm import get_provider
from ..memory import Wiki
from ..skills import SKILLS, analyze_email as _analyze_email
from ..skills.registry import all_tool_schemas

# Varied warm preambles spoken WHILE a skill runs. The model is supposed
# to emit one in ``content`` alongside its ``tool_calls``, but in
# practice GLM-4.6 returns empty content half the time when the system
# prompt is long. Falling back to a generic "Let me work on that" makes
# Xiexie sound robotic, so we pick a per-skill warm preamble client-side
# whenever the model leaves ``content`` empty.
_SKILL_PREAMBLES: dict[str, list[str]] = {
    "open_app": [
        "Sure, opening {name} for you now.",
        "Of course — let me bring up {name}.",
        "Yes of course, opening {name} right now.",
    ],
    "read_emails": [
        "Of course, let me check your inbox.",
        "Sure thing — looking at your unread emails now.",
        "Yes — let me see what came in.",
    ],
    "analyze_email": [
        "Yes of course, let me have a closer look at that one.",
        "Sure, I'll go through it carefully for you.",
        "Of course — checking it now, this'll just take a moment.",
    ],
    "archive_email": [
        "Of course, archiving it for you.",
        "Sure, moving it out of your inbox.",
        "Yes — getting that out of the way.",
    ],
    "report_to_family": [
        "Of course, drafting a note to your family right now.",
        "Sure — let me put together a heads-up.",
        "Yes, I'll write to them for you.",
    ],
    "set_reminder": [
        "Of course, adding that reminder for you.",
        "Sure — let me set that up.",
        "Yes, I'll make a note of it.",
    ],
    "find_file": [
        "Sure, let me look for that on your computer.",
        "Of course — searching for it now.",
        "Yes — let me find it for you.",
    ],
    "zoom_text": [
        "Sure, making things bigger for you.",
        "Of course — easier on the eyes coming up.",
        "Yes, let me adjust that.",
    ],
    "read_screen": [
        "Of course, let me have a look at what's on your screen.",
        "Sure — looking at it now.",
        "Yes, I'll check it for you.",
    ],
    "daily_brief": [
        "Of course, let me put together your morning briefing.",
        "Sure — gathering everything for you.",
    ],
}


def _generate_preamble(skill: str, args: dict[str, Any]) -> str:
    """Pick a warm conversational preamble for a skill, formatted with args."""
    options = _SKILL_PREAMBLES.get(skill)
    if not options:
        return "Of course, let me work on that for you."
    template = random.choice(options)
    try:
        return template.format(**args)
    except (KeyError, IndexError, ValueError):
        # ``args`` doesn't have the keys the template expected — fall back
        # to the format string unrendered.
        return template.replace("{name}", "that").replace("{recipient_hint}", "your family")

# Short affirmative phrases that mean "fire the pending follow-up". Kept
# permissive on punctuation/casing so "Yes please." and "yeah, go ahead!"
# both match. Anything longer than ~6 words goes through the regular
# GLM-routed path so we never short-circuit a real instruction.
_AFFIRMATIVE_RE = re.compile(
    r"""^\s*(?:
        yes(?:\s*please)?(?:\s+(?:do(?:\s+it)?|go(?:\s+ahead)?))?
      | yes(?:\s+(?:she|he|them|that|sure))?
      | yeah | yep | yup
      | sure(?:\s+(?:thing|please))?
      | okay | ok | k
      | go(?:\s+ahead)?
      | do\s+it
      | please\s+do
      | sounds\s+good
    )\s*[.!?]?\s*$""",
    re.IGNORECASE | re.VERBOSE,
)


def _is_short_affirmative(text: str) -> bool:
    """Return True for ~6-word-or-less affirmative replies (yes / go ahead / …).

    Used by ``Planner.plan`` to short-circuit a pending follow-up suggestion
    without paying a second LLM round-trip on every "yes please".
    """
    if not text:
        return False
    cleaned = text.strip()
    if not cleaned or len(cleaned.split()) > 6:
        return False
    return _AFFIRMATIVE_RE.match(cleaned) is not None

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
        # ── Early return: short affirmative + a pending follow-up ──────────
        # ``analyze_email`` stashes a single-shot follow-up suggestion when
        # the verdict is phishing/suspicious. The WS endpoint shows the
        # user a ``confirm`` bubble like "Want me to send Lisa a heads-up?".
        # When the user replies with a short "yes" / "go ahead", we don't
        # need to round-trip through GLM — we already know the exact
        # skill+args. Skip the destructive confirmation gate too: the user
        # just answered the gate when they said yes.
        if _is_short_affirmative(transcript):
            followup = _analyze_email.consume_followup()
            if followup and followup.get("skill") in SKILLS:
                steps = [
                    PlanStep(
                        skill=followup["skill"],
                        arguments=dict(followup.get("args") or {}),
                        speak_before=None,
                    )
                ]
                spoken = "On it — drafting that note now."
                return PlanResult(speak=spoken, steps=steps, raw_text="")

        sys_prompt = PLANNER_SYSTEM.format(wiki=self.wiki.as_planner_context())
        messages: list[dict[str, Any]] = [{"role": "system", "content": sys_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": transcript})

        # Tool list = real skills + the narrate sentinel.
        tools = all_tool_schemas() + [_NARRATE_TOOL]

        # On the *proxy* (api.r9s.ai) GLM-5.x ignores ``tool_choice="auto"``
        # so we forced ``required``. On *direct* Z.AI (api.z.ai) GLM-4.6
        # dispatches cleanly *and* emits a conversational preamble in the
        # ``content`` field when ``auto`` is used — exactly what we want
        # ("I'll check your inbox for you" instead of the generic
        # "Let me work on that" fallback). Detect by base URL.
        base_url = str(getattr(self.llm.client, "base_url", "")).lower()
        on_proxy = "r9s.ai" in base_url
        choice = "required" if on_proxy else "auto"

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
        # 1. Real text from the model (the warm preamble it generated alongside the tool_calls)
        # 2. The narrate sentinel's reply (when no real skill matched)
        # 3. A varied per-skill preamble — keeps Xiexie sounding human even
        #    when GLM-4.6 leaves ``content`` empty (which it does roughly
        #    50% of the time on long system prompts). Picks based on the
        #    first skill the planner is about to run.
        # 4. Last-resort fallback narration.
        spoken = resp.text.strip() or narrate_reply
        if not spoken and steps:
            spoken = _generate_preamble(steps[0].skill, steps[0].arguments)
        if not spoken:
            spoken = "I don't know how to do that yet — taking a note."
        return PlanResult(speak=spoken, steps=steps, raw_text=resp.text)
