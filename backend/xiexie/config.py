"""Environment + path configuration. Loaded once at startup."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Walk up from this file to find a .env at the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env")


class Config:
    # ─── LLM ──────────────────────────────────────────────────────────────
    ZAI_API_KEY: str | None = os.getenv("ZAI_API_KEY")
    ZAI_BASE_URL: str = os.getenv("ZAI_BASE_URL", "https://api.z.ai/api/paas/v4")
    ZAI_MODEL: str = os.getenv("ZAI_MODEL", "glm-4.6")
    ZAI_VISION_MODEL: str = os.getenv("ZAI_VISION_MODEL", "glm-4v")

    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

    # ─── Backend ──────────────────────────────────────────────────────────
    BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8787"))

    # ─── Paths ────────────────────────────────────────────────────────────
    REPO_ROOT: Path = _REPO_ROOT
    WIKI_DIR: Path = Path(os.getenv("WIKI_DIR", _REPO_ROOT / "data" / "wiki")).resolve()
    RAW_DIR: Path = Path(os.getenv("RAW_DIR", _REPO_ROOT / "data" / "raw")).resolve()

    @classmethod
    def primary_provider(cls) -> str:
        """Which LLM provider should we route to right now?"""
        if cls.ZAI_API_KEY:
            return "zai"
        if cls.OPENAI_API_KEY:
            return "openai"
        return "none"


config = Config()
