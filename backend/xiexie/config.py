"""Environment + path configuration. Loaded once at startup."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Walk up from this file to find a .env at the repo root. Works in dev
# (`uv run uvicorn …` from the repo) but breaks once we're frozen by
# PyInstaller and shipped inside Xiexie.app — ``__file__`` then points
# at a temp directory under the .app bundle, not Edouard's clone.
_REPO_ROOT = Path(__file__).resolve().parents[2]

# When packaged via PyInstaller (Tauri sidecar), ``sys.frozen`` is True
# and Tauri's ``child::start_backend`` exports ``XIEXIE_DATA_DIR`` =
# ``~/Library/Application Support/ai.xiexie.desktop/data``. We look
# there for the user's API keys first, then fall back to the repo
# .env (dev-time path).
_FROZEN = bool(getattr(sys, "frozen", False))
_DATA_DIR_ENV = os.environ.get("XIEXIE_DATA_DIR")

# Resolution order — first hit wins (load_dotenv doesn't override
# already-set env vars, so the most-specific path goes first).
_dotenv_candidates: list[Path] = []
if _DATA_DIR_ENV:
    _dotenv_candidates.append(Path(_DATA_DIR_ENV) / ".env")
_dotenv_candidates.append(_REPO_ROOT / ".env")

for _candidate in _dotenv_candidates:
    if _candidate.exists():
        load_dotenv(_candidate)
        # Don't break — load_dotenv silently leaves existing env vars
        # untouched, so chaining multiple files is harmless and gives
        # the user-data .env precedence over repo dev defaults.


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
    ZAI_MODEL: str = os.getenv("ZAI_MODEL", "glm-5.1")
    # Empty string = vision unavailable on this provider; LLMProvider.see()
    # raises a clean error if called instead of silently calling a non-vision model.
    ZAI_VISION_MODEL: str = os.getenv("ZAI_VISION_MODEL", "")
    ZAI_FALLBACK_MODEL: str = os.getenv("ZAI_FALLBACK_MODEL", "deepseek-v4-flash")

    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

    # ─── Backend ──────────────────────────────────────────────────────────
    BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8787"))

    # ─── Paths ────────────────────────────────────────────────────────────
    # When frozen + Tauri-spawned, XIEXIE_DATA_DIR points at a writable
    # ``~/Library/Application Support/ai.xiexie.desktop/data`` location.
    # In dev we keep using the repo's data/ tree so the wiki seed + the
    # demo inbox fixture are discoverable without an env-var dance.
    REPO_ROOT: Path = _REPO_ROOT
    _DATA_DEFAULT: Path = (
        Path(_DATA_DIR_ENV) if _DATA_DIR_ENV else _REPO_ROOT / "data"
    )
    WIKI_DIR: Path = Path(os.getenv("WIKI_DIR", _DATA_DEFAULT / "wiki")).resolve()
    RAW_DIR: Path = Path(os.getenv("RAW_DIR", _DATA_DEFAULT / "raw")).resolve()

    @classmethod
    def primary_provider(cls) -> str:
        """Which LLM provider should we route to right now?"""
        if cls.ZAI_API_KEY:
            return "zai"
        if cls.OPENAI_API_KEY:
            return "openai"
        return "none"


config = Config()
