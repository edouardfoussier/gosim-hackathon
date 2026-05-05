"""find_file — search Margaret's Mac for files via Spotlight.

Reads the wiki ``files.md`` so it knows where things live. Falls back to a
broad ``mdfind`` if no scope hint applies.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from ..memory import Wiki
from .registry import Skill, register


def _mdfind(query: str, scope: Path | None = None, limit: int = 5) -> list[str]:
    cmd = ["mdfind", query]
    if scope is not None:
        cmd = ["mdfind", "-onlyin", str(scope), query]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
    paths = [line for line in out.stdout.splitlines() if line.strip()]
    return paths[:limit]


def run(args: dict[str, Any]) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        return "What should I look for?"

    # Hint scope from the wiki: e.g. invoices live in ~/Documents/Invoices/
    wiki = Wiki()
    files_page = wiki.get("files")
    scope: Path | None = None
    INVOICE_HINTS = ("invoice", "bill", "edf", "pg&e", "pge", "att", "aetna")
    if files_page and any(h in query.lower() for h in INVOICE_HINTS):
        # very lightweight heuristic — the linter can refine over time
        candidate = Path.home() / "Documents" / "Invoices"
        if candidate.exists():
            scope = candidate

    matches = _mdfind(query, scope=scope, limit=5)
    if not matches:
        return f"I couldn't find anything matching {query!r}."

    head = matches[0]
    if len(matches) == 1:
        return f"Found one: {head}"
    others = "\n".join(f"  - {m}" for m in matches[1:])
    return f"Found {len(matches)} files. Most recent:\n{head}\nOthers:\n{others}"


SKILL = register(
    Skill(
        name="find_file",
        description=(
            "Search the user's Mac for files matching a free-text query (e.g. 'EDF bill', "
            "'last passport scan'). Uses Spotlight (`mdfind`) and the wiki's `files.md` "
            "for scope hints."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for, in plain language (e.g. 'EDF', 'tax 2025').",
                }
            },
            "required": ["query"],
        },
        run=run,
        destructive=False,
        tags=["files", "spotlight"],
    )
)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--query", required=True)
    a = p.parse_args()
    print(run({"query": a.query}))
