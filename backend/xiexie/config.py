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
    # deepseek-v4-{pro,flash} and glm-5{,.1}. We default to deepseek-v4-pro
    # because GLM-5.x runs in Thinking Mode on this proxy and bleeds CoT
    # into ``message.content`` (suppression flags are stripped). For direct
    # Z.AI (with proper Thinking Mode control + vision + audio), set
    # ZAI_BASE_URL=https://api.z.ai/api/paas/v4 with a key from the Z.AI
    # mentor on-site. See ADR in CLAUDE.md for the full reasoning.
    ZAI_API_KEY: str | None = os.getenv("ZAI_API_KEY")
    ZAI_BASE_URL: str = os.getenv("ZAI_BASE_URL", "https://api.r9s.ai/v1")
    ZAI_MODEL: str = os.getenv("ZAI_MODEL", "deepseek-v4-pro")
    # Empty string = vision unavailable on this provider; LLMProvider.see()
    # raises a clean error if called instead of silently calling a non-vision model.
    ZAI_VISION_MODEL: str = os.getenv("ZAI_VISION_MODEL", "")
    ZAI_FALLBACK_MODEL: str = os.getenv("ZAI_FALLBACK_MODEL", "deepseek-v4-flash")

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
