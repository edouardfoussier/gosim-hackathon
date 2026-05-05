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
    # Default base URL is the GOSIM proxy (api.r9s.ai/v1) which exposes
    # glm-5.1, glm-5, deepseek-v4-pro, deepseek-v4-flash. For direct Z.AI
    # (vision + audio), set ZAI_BASE_URL=https://api.z.ai/api/paas/v4 with
    # a key from the Z.AI mentor on-site.
    ZAI_API_KEY: str | None = os.getenv("ZAI_API_KEY")
    ZAI_BASE_URL: str = os.getenv("ZAI_BASE_URL", "https://api.r9s.ai/v1")
    ZAI_MODEL: str = os.getenv("ZAI_MODEL", "glm-5.1")
    # Empty string = vision unavailable on this provider; LLMProvider.see()
    # raises a clean error if called instead of silently calling a non-vision model.
    ZAI_VISION_MODEL: str = os.getenv("ZAI_VISION_MODEL", "")
    ZAI_FALLBACK_MODEL: str = os.getenv("ZAI_FALLBACK_MODEL", "deepseek-v4-pro")

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
