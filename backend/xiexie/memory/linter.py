"""Wiki linter — the compounding-knowledge pass.

Run after each session (or on demand). Reads the wiki + recent transcripts +
``unhandled_asks.md``, asks the LLM for structured patches and skill
proposals (see ``WIKI_SCHEMA.md`` §5), and applies the high-confidence ones.

V1 status (J1): structure + entry point only — full LLM patching is on the
J2 morning task list. Demo-time we'll show a *pre-baked* linter diff if
needed.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..config import config
from ..llm import get_provider
from .wiki import Wiki

LINTER_SYSTEM = """\
You are the Xiexie wiki linter. Your job is to keep the user's markdown wiki
accurate, consistent, and growing across sessions.

Given the current wiki and recent raw inputs (transcripts, unhandled asks),
return STRICT JSON with this shape:

{
  "patches": [
    {"file": "wiki/<slug>.md", "kind": "add"|"update"|"remove",
     "anchor": "<heading or section>", "content": "<markdown>",
     "confidence": "high"|"medium"|"low",
     "evidence": "<short citation>"}
  ],
  "contradictions": [
    {"files": ["..."], "summary": "..."}
  ],
  "skill_proposals": [
    {"ask": "<verbatim>", "frequency": <int>, "name_hint": "<snake_case>"}
  ]
}

Rules:
- Only suggest 'high' confidence for explicit user statements.
- Never include plaintext secrets — point to Keychain refs.
- Cross-reference using [[wiki:slug#anchor]].
- If nothing to do, return {"patches": [], "contradictions": [], "skill_proposals": []}.
"""


def collect_recent_raw(limit_files: int = 10) -> str:
    raw_dir: Path = config.RAW_DIR
    parts: list[str] = []

    transcripts_dir = raw_dir / "transcripts"
    if transcripts_dir.exists():
        for path in sorted(transcripts_dir.glob("*.md"), reverse=True)[:limit_files]:
            parts.append(f"\n--- {path.name} ---\n{path.read_text(encoding='utf-8')}")

    unhandled = raw_dir / "unhandled_asks.md"
    if unhandled.exists():
        parts.append(f"\n--- unhandled_asks.md ---\n{unhandled.read_text(encoding='utf-8')}")

    return "\n".join(parts)


def lint_once(apply: bool = False) -> dict:
    wiki = Wiki()
    llm = get_provider()

    user_msg = (
        "## Current wiki\n"
        + wiki.as_planner_context(max_chars=8000)
        + "\n\n## Recent raw inputs\n"
        + collect_recent_raw()
    )

    resp = llm.chat(
        messages=[
            {"role": "system", "content": LINTER_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.1,
        max_tokens=2048,
    )

    try:
        report = json.loads(resp.text)
    except json.JSONDecodeError:
        return {"error": "linter returned non-JSON", "raw": resp.text}

    if apply:
        for patch in report.get("patches", []):
            if patch.get("confidence") == "high" and patch.get("kind") == "add":
                file_ref: str = patch.get("file", "")
                slug = Path(file_ref).stem
                if slug:
                    wiki.append_bullet(slug, patch.get("content", ""), by="linter")

    return report


if __name__ == "__main__":
    import sys

    apply_flag = "--apply" in sys.argv
    out = lint_once(apply=apply_flag)
    print(json.dumps(out, indent=2, ensure_ascii=False))
