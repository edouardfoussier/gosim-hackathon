"""Skill registry — declarative, JSON-schema-friendly, planner-ready.

A *skill* is the smallest unit Xiexie can do. Each skill exposes:

- ``name``         — snake_case identifier (also tool name for the LLM)
- ``description``  — one sentence the planner uses to pick it
- ``parameters``   — JSON Schema for arguments
- ``destructive``  — whether the confirmation gate must trigger
- ``run(args)``    — synchronous Python function returning a string result

The registry is a flat dict and serialises to OpenAI/Z.AI-style ``tools`` so
the planner can call skills via tool-calling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

SkillFn = Callable[[dict[str, Any]], str]


@dataclass
class Skill:
    name: str
    description: str
    parameters: dict[str, Any]
    run: SkillFn
    destructive: bool = False
    tags: list[str] = field(default_factory=list)

    def to_tool_schema(self) -> dict[str, Any]:
        """Serialise to OpenAI/Z.AI tool-calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


SKILLS: dict[str, Skill] = {}


def register(skill: Skill) -> Skill:
    if skill.name in SKILLS:
        raise ValueError(f"Skill {skill.name!r} already registered")
    SKILLS[skill.name] = skill
    return skill


def all_tool_schemas() -> list[dict[str, Any]]:
    return [s.to_tool_schema() for s in SKILLS.values()]


def call(name: str, arguments: dict[str, Any]) -> str:
    skill = SKILLS.get(name)
    if skill is None:
        raise KeyError(f"Unknown skill: {name}")
    return skill.run(arguments)
