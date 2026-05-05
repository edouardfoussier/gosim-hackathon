"""Read/write the LLM-Wiki — plain markdown files in ``data/wiki/``.

Implements the three-layer pattern described in ``WIKI_SCHEMA.md``:

- Layer 1 (raw)  → ``data/raw/``  — append-only, untouched here
- Layer 2 (wiki) → ``data/wiki/`` — *this* module reads and writes it
- Layer 3 (schema) → ``WIKI_SCHEMA.md`` — conventions only, not code

Each wiki file is markdown with YAML front matter parsed by
``python-frontmatter``. The page slug equals the file name (without .md).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import frontmatter

from ..config import config


@dataclass
class WikiPage:
    slug: str
    path: Path
    metadata: dict
    body: str

    def render(self) -> str:
        """Markdown rendering with up-to-date front matter."""
        post = frontmatter.Post(self.body, **self.metadata)
        return frontmatter.dumps(post)


class Wiki:
    """Tiny key-value-ish view over ``data/wiki/`` — load/save/search."""

    def __init__(self, root: Path | None = None):
        self.root = (root or config.WIKI_DIR).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    # ── read ──────────────────────────────────────────────────────────────
    def list_slugs(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.md") if p.stem != "INDEX")

    def get(self, slug: str) -> WikiPage | None:
        path = self.root / f"{slug}.md"
        if not path.exists():
            return None
        post = frontmatter.load(path)
        return WikiPage(slug=slug, path=path, metadata=dict(post.metadata), body=post.content)

    def all_pages(self, exclude_index: bool = True) -> list[WikiPage]:
        pages: list[WikiPage] = []
        for slug in self.list_slugs():
            if exclude_index and slug == "INDEX":
                continue
            page = self.get(slug)
            if page:
                pages.append(page)
        return pages

    # ── search (cheap substring; planner uses LLM grounding for the rest) ──
    def search(self, query: str) -> list[tuple[WikiPage, list[str]]]:
        out: list[tuple[WikiPage, list[str]]] = []
        q = query.lower()
        for page in self.all_pages():
            hits = [line.strip() for line in page.body.splitlines() if q in line.lower()]
            if hits:
                out.append((page, hits))
        return out

    # ── write ─────────────────────────────────────────────────────────────
    def save(self, page: WikiPage, *, by: str = "agent") -> None:
        page.metadata["last_updated"] = dt.datetime.now(dt.timezone.utc).isoformat(
            timespec="seconds"
        )
        page.metadata["last_updated_by"] = by
        page.path.write_text(page.render(), encoding="utf-8")

    def append_bullet(self, slug: str, bullet: str, *, by: str = "agent") -> WikiPage:
        """Append a single bullet at the end of the page (creates the page if missing)."""
        page = self.get(slug)
        if page is None:
            path = self.root / f"{slug}.md"
            page = WikiPage(
                slug=slug,
                path=path,
                metadata={"slug": slug, "title": slug.replace("_", " ").title()},
                body="",
            )
        body = page.body.rstrip()
        bullet = bullet.lstrip("- ").strip()
        page.body = f"{body}\n- {bullet}\n" if body else f"- {bullet}\n"
        self.save(page, by=by)
        return page

    # ── prompt rendering — used by the planner ────────────────────────────
    def as_planner_context(self, slugs: list[str] | None = None, max_chars: int = 4000) -> str:
        """Compact wiki dump suitable for the planner system prompt."""
        slugs = slugs or self.list_slugs()
        chunks: list[str] = []
        total = 0
        for slug in slugs:
            page = self.get(slug)
            if not page:
                continue
            block = f"### {page.metadata.get('title', slug)}\n{page.body.strip()}\n"
            if total + len(block) > max_chars:
                chunks.append(f"### {slug} … (truncated)\n")
                break
            chunks.append(block)
            total += len(block)
        return "\n".join(chunks)
