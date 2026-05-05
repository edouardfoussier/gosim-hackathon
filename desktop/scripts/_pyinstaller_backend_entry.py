"""Entry script wrapped by PyInstaller into ``xiexie-backend``.

PyInstaller needs a single ``.py`` file as the freeze entry point. The
backend's actual ``main.py`` is a FastAPI ``app`` object — not a CLI —
so we trampoline through here: read the host/port from env vars (set by
the Tauri Rust shell in ``child::start_backend``) and call uvicorn
directly.

This file lives next to ``build-python-binaries.sh`` and only ever runs
inside the frozen bundle.
"""

from __future__ import annotations

import os
import sys


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    host = os.environ.get("XIEXIE_HOST", "127.0.0.1")
    port = int(os.environ.get("XIEXIE_PORT", "8787"))
    reload = _bool_env("XIEXIE_RELOAD", default=False)

    # Lazily import uvicorn here so PyInstaller's static analyser
    # threads the right import graph through this entry script.
    import uvicorn  # noqa: WPS433  — intentional late import

    # Importing ``xiexie.main`` triggers the skill registry side effects
    # (see ``backend/xiexie/skills/__init__.py``) before uvicorn boots
    # the server, so the first ``/skills`` request is instant.
    from xiexie.main import app  # noqa: WPS433  — intentional late import

    print(f"[xiexie-backend] starting uvicorn on {host}:{port} (pid {os.getpid()})", flush=True)
    uvicorn.run(app, host=host, port=port, reload=reload, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
