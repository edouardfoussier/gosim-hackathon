"""read_screen — vision skill: capture the active screen and ask GLM about it.

Use cases (post Z.AI direct-key + ``ZAI_VISION_MODEL=glm-4.5v``):

- "What does this email say?" — Margaret has Mail.app focused.
- "Read the headline of this article."
- "What's that error message about?"

Architecture:

1. ``_capture_screen`` grabs a PNG via ``mss``. For ``scope="active_window"``
   we ask ``Quartz.CGWindowListCopyWindowInfo`` for the bounds of the
   front-most layer-0 window (same pattern Clicky uses) and crop to it.
   If Quartz is unavailable or the lookup is flaky, we silently fall back
   to the full primary monitor (logged in the skill description so the
   planner doesn't promise pixel-perfect cropping).
2. The screenshot is base64-encoded PNG and sent to
   ``LLMProvider.see(image_b64, prompt)`` with a system-flavoured prompt
   that prepends Margaret's ``wiki/preferences.md`` so the answer reads
   like Xiexie talking to a senior — slow, plain English, no acronyms,
   numbers repeated twice.
3. Returns the model's plain-text reply for the spoken response.

Vision is only available on direct Z.AI (``api.z.ai/api/paas/v4`` with
``ZAI_VISION_MODEL`` set). On the GOSIM proxy this skill raises a clear
``RuntimeError`` from ``LLMProvider.see``; the planner's fallback prints
the message so the demo Q&A degrades gracefully.
"""

from __future__ import annotations

import base64
import io
import re
from typing import Any

from ..llm import get_provider
from ..memory import Wiki
from .registry import Skill, register

# Sections of ``wiki/preferences.md`` that bias the spoken reply (text size,
# acronym avoidance, "repeat numbers twice"). We splice them into the
# vision prompt so GLM-4.5V's response reads like Xiexie speaking, not a
# generic chatbot describing pixels.
_PREFS_SECTIONS: tuple[str, ...] = ("Vision", "Hearing", "Interaction style")

_PROMPT_PREAMBLE = (
    "You are Xiexie, a calm AI helper for a senior named Margaret. "
    "You are looking at a screenshot of her entire Mac screen — there "
    "may be several windows open (Mail.app, Chrome, the Xiexie chat "
    "itself, the desktop wallpaper). Find the one part of the screen "
    "that answers Margaret's question and read THAT to her. Ignore "
    "the rest. If she asks about an email, look for a Mail.app window "
    "and read the visible message — even if it's not the front-most "
    "window. Reply in one short paragraph of plain English: no jargon, "
    "no acronyms (say 'main doctor' not 'PCP'), warm tone. If you read "
    "out a number, an amount, or an address, repeat it twice. Only say "
    "'I don't see anything matching that' when the relevant content is "
    "genuinely absent — never describe just the desktop wallpaper as "
    "your answer when there are app windows visible above it."
)


def _wiki_prefs_hint(wiki: Wiki) -> str:
    """Pull the Vision / Hearing / Interaction sections out of preferences.md.

    Returns a single newline-joined string suitable for splicing into the
    vision prompt. Empty string if the wiki page is missing — the demo
    must still run on a fresh checkout without the seed wiki.
    """
    page = wiki.get("preferences")
    if not page:
        return ""
    out: list[str] = []
    for header in _PREFS_SECTIONS:
        # Match "## <Header>\n<body>" up to the next "## " or end of file.
        match = re.search(
            rf"^##\s+{re.escape(header)}\s*\n(.+?)(?=\n##\s|\Z)",
            page.body,
            re.MULTILINE | re.DOTALL,
        )
        if match:
            body = match.group(1).strip()
            if body:
                out.append(f"{header}:\n{body[:400]}")
    return "\n\n".join(out)


def _capture_active_window_bounds() -> tuple[int, int, int, int] | None:
    """Return ``(left, top, width, height)`` of the front-most window or None.

    Wrapped in a broad try/except because ``Quartz`` is a PyObjC binding
    that is best-effort on every Mac (missing on Linux, occasionally
    flaky behind certain perms). Any failure → caller falls back to the
    whole primary monitor, which is a strictly larger capture (still
    useful, just less focused).
    """
    try:
        from Quartz import (  # type: ignore[import-not-found]
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListOptionOnScreenOnly,
        )
    except Exception:  # noqa: BLE001 — Quartz absent / import failure
        return None

    try:
        windows = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly, kCGNullWindowID
        )
    except Exception:  # noqa: BLE001 — runtime perms / Quartz blow-up
        return None

    if not windows:
        return None

    # Layer 0 = regular app window; the first match is the front-most.
    for win in windows:
        try:
            if int(win.get("kCGWindowLayer", 1)) != 0:
                continue
            if float(win.get("kCGWindowAlpha", 0.0)) <= 0.0:
                continue
            bounds = win.get("kCGWindowBounds")
            if not bounds:
                continue
            left = int(bounds.get("X", 0))
            top = int(bounds.get("Y", 0))
            width = int(bounds.get("Width", 0))
            height = int(bounds.get("Height", 0))
        except Exception:  # noqa: BLE001 — malformed entry, try the next one
            continue
        if width >= 200 and height >= 200:
            return (left, top, width, height)
    return None


def _capture_screen(scope: str = "active_window") -> str:
    """Capture the screen and return a base64-encoded PNG string.

    ``scope`` is either ``"active_window"`` (front-most app window via
    Quartz, falls back to full primary monitor) or ``"full"`` (always
    primary monitor).
    """
    import mss  # local import: keeps cold-start cheap if skill never fires

    from PIL import Image

    bounds: tuple[int, int, int, int] | None = None
    if scope == "active_window":
        bounds = _capture_active_window_bounds()

    with mss.mss() as sct:
        if bounds is not None:
            left, top, width, height = bounds
            region = {"left": left, "top": top, "width": width, "height": height}
        else:
            # ``monitors[0]`` is the union of every screen — on multi-monitor
            # rigs it's enormous and noisy. ``monitors[1]`` is the primary,
            # which is what Margaret stares at in the demo.
            region = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        sct_img = sct.grab(region)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

    buf = io.BytesIO()
    # ``optimize=True`` shaves ~30% off the payload at no quality cost —
    # vision endpoints accept much larger images than this but the request
    # is faster (and cheaper) when the PNG is tight.
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _build_prompt(question: str, prefs_hint: str) -> str:
    parts = [_PROMPT_PREAMBLE]
    if prefs_hint:
        parts.append("User preferences (apply when answering):\n" + prefs_hint)
    parts.append("Margaret's question: " + question.strip())
    return "\n\n".join(parts)


def run(args: dict[str, Any]) -> str:
    question = str(args.get("question", "")).strip()
    if not question:
        return "What would you like me to read for you?"

    # Default to "full" (whole primary monitor) — same strategy Clicky
    # uses. Cropping to the active window often misses the very thing
    # the user is asking about (e.g. an email visible in a non-focused
    # Mail.app window behind the chat panel). The vision model handles
    # cluttered screens just fine; the upside of seeing everything
    # outweighs the cost of a slightly larger payload.
    scope = str(args.get("scope") or "full").strip().lower()
    if scope not in ("active_window", "full"):
        scope = "full"

    print(f"[read_screen] question={question!r} scope={scope}", flush=True)

    image_b64 = _capture_screen(scope)
    bounds = _capture_active_window_bounds() if scope == "active_window" else None
    if bounds:
        print(
            f"[read_screen] captured active window bounds={bounds} "
            f"({len(image_b64) // 1024} KB png)",
            flush=True,
        )
    else:
        print(
            f"[read_screen] captured full primary monitor (active window "
            f"bounds unavailable; {len(image_b64) // 1024} KB png)",
            flush=True,
        )

    prefs_hint = _wiki_prefs_hint(Wiki())
    prompt = _build_prompt(question, prefs_hint)

    llm = get_provider()
    print(
        f"[read_screen] sending to vision model={llm.vision_model or '(unset)'}",
        flush=True,
    )

    try:
        # ``LLMProvider.see`` raises ``RuntimeError`` when no vision model is
        # configured — that's the proxy-only configuration. Let it propagate;
        # the planner's exception path turns it into a spoken explanation.
        reply = (llm.see(image_b64, prompt) or "").strip()
    except RuntimeError as exc:
        # Surface the missing-vision-model case as a clear spoken sentence
        # rather than letting the realtime tool path swallow it.
        print(f"[read_screen] vision unavailable: {exc}", flush=True)
        return (
            "I can't look at your screen right now — vision is only available "
            "on the direct Z.AI key, and we're on the proxy. Would you like "
            "me to read your inbox instead?"
        )

    print(f"[read_screen] reply={reply[:120]!r}…", flush=True)
    return reply or (
        "I looked at your screen but couldn't make out an answer to that."
    )


SKILL = register(
    Skill(
        name="read_screen",
        description=(
            "Capture the user's active screen and answer a question about "
            "what's on it. Use ONLY when the user references something "
            "visible right now (this, the screen, the headline, the message "
            "I'm looking at). Never use when the user just wants help with "
            "something not visibly shown. Falls back to the full primary "
            "monitor if the active window's bounds can't be read."
        ),
        parameters={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": (
                        "Specific question to ask about the screen contents."
                    ),
                },
                "scope": {
                    "type": "string",
                    "enum": ["full", "active_window"],
                    "default": "active_window",
                    "description": (
                        "Capture the front-most window (default) or the "
                        "whole primary monitor."
                    ),
                },
            },
            "required": ["question"],
        },
        run=run,
        destructive=False,
        tags=["vision", "breadth"],
    )
)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--question", required=True)
    p.add_argument(
        "--scope",
        default="active_window",
        choices=["active_window", "full"],
    )
    a = p.parse_args()
    print(run({"question": a.question, "scope": a.scope}))
