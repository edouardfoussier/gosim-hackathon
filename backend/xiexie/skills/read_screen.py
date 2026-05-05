"""read_screen — vision skill: capture the screen and ask GLM about it.

Use cases (post Z.AI direct-key + ``ZAI_VISION_MODEL=glm-4.5v``):

- "What does this email say?" → planner sets ``app="Mail"``.
- "Read the article on this page" → planner sets ``app="Google Chrome"``.
- "What does the screen show?" → ``scope="full"``.

Architecture:

1. **Per-app window capture (Clicky parity).** When ``app`` is specified we
   ask ``Quartz.CGWindowListCopyWindowInfo`` for that application's
   biggest on-screen layer-0 window and capture its pixels via
   ``CGWindowListCreateImage`` with ``kCGWindowImageBoundsIgnoreFraming``.
   Critically, this works **even when the window is occluded by another
   app** (e.g. Mail.app behind the Chrome tab running Xiexie). Cocoa
   refuses to capture windows on inactive Spaces or minimized — those
   degrade to the next branch.
2. **Active-window or full-monitor fallback** via ``mss``: layer-0
   front-most window's bounds, or the whole primary monitor if Quartz
   bounds aren't available.
3. The capture is downscaled to ``_MAX_SCREENSHOT_DIM`` px (longest side)
   and JPEG-encoded — Retina full-screen PNG (~2.3 MB) silently lost
   GLM-4.5V replies in early tests; 1600 px JPEG-82 is ~150-300 KB and
   reliably round-trips.
4. The screenshot is base64-encoded JPEG and sent to
   ``LLMProvider.see(image_b64, prompt, mime="image/jpeg")`` with a
   prompt that splices Margaret's ``wiki/preferences.md`` so the answer
   reads like Xiexie speaking — plain English, no acronyms, numbers
   repeated twice.
5. Returns the model's plain-text reply for the spoken response.

Vision is only available on direct Z.AI (``api.z.ai/api/paas/v4`` with
``ZAI_VISION_MODEL`` set). On the GOSIM proxy this skill raises a clear
``RuntimeError`` from ``LLMProvider.see`` so the demo degrades gracefully.
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
    "You are looking at a screenshot of one of her Mac windows. "
    "Read the relevant content and answer her question directly. "
    "Reply in one short paragraph of plain English: no jargon, no "
    "acronyms (say 'main doctor' not 'PCP'), warm tone. If you read "
    "out a number, an amount, or an address, repeat it twice for "
    "clarity. If the screenshot truly does not contain anything that "
    "answers the question, say so honestly — but never describe just "
    "a desktop wallpaper or background image as your answer when "
    "real app content (an email, a webpage, a document) is visible."
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


_MAX_SCREENSHOT_DIM = 1600  # px on the longest side; vision sweet spot
_JPEG_QUALITY = 82          # near-imperceptible compression for screen UI

# When the planner asks for ``app="email"`` (and similar generic terms) we
# expand to the canonical macOS bundle name. Anything not in this map is
# matched as-is against ``kCGWindowOwnerName`` (substring, case-insensitive),
# so callers can pass "Mail", "Google Chrome", "Music", "Notes" verbatim.
_APP_ALIASES: dict[str, tuple[str, ...]] = {
    "email": ("Mail",),
    "mail": ("Mail",),
    "browser": ("Arc", "Safari", "Google Chrome", "Brave Browser", "Firefox"),
    "chrome": ("Google Chrome",),
    "safari": ("Safari",),
    "music": ("Music",),
    "notes": ("Notes",),
    "messages": ("Messages",),
    "reminders": ("Reminders",),
    "whatsapp": ("WhatsApp",),
    "calendar": ("Calendar",),
}


def _find_app_window(
    app: str, *, include_offscreen: bool = True
) -> tuple[int, tuple[int, int, int, int], str, bool] | None:
    """Locate the biggest layer-0 window owned by ``app``.

    Returns ``(window_id, (left, top, width, height), owner_name,
    on_screen)`` or None.

    We try **on-screen only** first (preferred — these windows are
    guaranteed renderable). When nothing matches and ``include_offscreen``
    is True we re-query with ``kCGWindowListOptionAll``: Quartz can still
    capture pixels for windows on inactive macOS Spaces or behind other
    apps, just not for *minimised* windows (those have no backing store).
    """
    try:
        from Quartz import (  # type: ignore[import-not-found]
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListExcludeDesktopElements,
            kCGWindowListOptionAll,
            kCGWindowListOptionOnScreenOnly,
        )
    except Exception:  # noqa: BLE001
        return None

    candidates = _APP_ALIASES.get(app.lower(), (app,))

    def _query(option_flags: int) -> tuple[int, tuple[int, int, int, int], str] | None:
        try:
            windows = CGWindowListCopyWindowInfo(option_flags, kCGNullWindowID)
        except Exception:  # noqa: BLE001
            return None
        if not windows:
            return None

        best: tuple[int, tuple[int, int, int, int], str] | None = None
        best_area = 0
        for win in windows:
            try:
                owner = str(win.get("kCGWindowOwnerName", "") or "")
                if not owner:
                    continue
                owner_lc = owner.lower()
                if not any(c.lower() in owner_lc for c in candidates):
                    continue
                if int(win.get("kCGWindowLayer", 1)) != 0:
                    continue
                bounds = win.get("kCGWindowBounds")
                if not bounds:
                    continue
                width = int(bounds.get("Width", 0))
                height = int(bounds.get("Height", 0))
                if width < 200 or height < 200:
                    continue
                wid = int(win.get("kCGWindowNumber", 0))
                if not wid:
                    continue
            except Exception:  # noqa: BLE001
                continue
            area = width * height
            if area > best_area:
                best_area = area
                best = (
                    wid,
                    (
                        int(bounds.get("X", 0)),
                        int(bounds.get("Y", 0)),
                        width,
                        height,
                    ),
                    owner,
                )
        return best

    on_screen = _query(
        kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements
    )
    if on_screen is not None:
        return (*on_screen, True)

    if include_offscreen:
        any_win = _query(
            kCGWindowListOptionAll | kCGWindowListExcludeDesktopElements
        )
        if any_win is not None:
            return (*any_win, False)
    return None


def _cgimage_to_pil(image_ref):  # type: ignore[no-untyped-def]
    """Convert a Quartz ``CGImageRef`` into a Pillow ``Image`` (RGB).

    Reads the raw pixel buffer via ``CGImageGetDataProvider`` →
    ``CGDataProviderCopyData``. macOS hands back BGRA premultiplied;
    we take the RGB channels. Avoids round-tripping through a temp
    PNG file (saves ~30-50 ms per capture).
    """
    from PIL import Image
    from Quartz import (  # type: ignore[import-not-found]
        CGDataProviderCopyData,
        CGImageGetBytesPerRow,
        CGImageGetDataProvider,
        CGImageGetHeight,
        CGImageGetWidth,
    )

    width = int(CGImageGetWidth(image_ref))
    height = int(CGImageGetHeight(image_ref))
    bytes_per_row = int(CGImageGetBytesPerRow(image_ref))
    provider = CGImageGetDataProvider(image_ref)
    cf_data = CGDataProviderCopyData(provider)
    raw = bytes(cf_data)
    img = Image.frombuffer(
        "RGBA", (width, height), raw, "raw", "BGRA", bytes_per_row, 1
    )
    return img.convert("RGB")


def _activate_app_and_grab(
    app: str, bounds: tuple[int, int, int, int] | None
) -> tuple[Any, str] | None:
    """Last-resort fallback: bring ``app`` to the front, then mss-capture.

    Used when ``CGWindowListCreateImage`` returns nil — typically because
    Terminal lacks the **Screen Recording** privacy permission on
    macOS 14+. We `osascript`-activate the app (which brings the right
    Space to the front and pops its window above the others), give the
    WindowServer ~250 ms to redraw, then capture either the recorded
    window bounds or the whole primary monitor.

    Side effect Edouard should expect during the demo: the active Space
    may switch to Mail's Space. With Screen Recording granted to
    Terminal, this fallback is never reached.
    """
    import subprocess
    import time

    import mss

    from PIL import Image

    candidates = _APP_ALIASES.get(app.lower(), (app,))
    osa_app = candidates[0]  # e.g. "Mail" or "Google Chrome"

    # Two-step force-front:
    # 1. activate — focuses the app within its current Space
    # 2. System Events frontmost — pops the window above any modal Chrome
    #    even when "Switch to Space with open windows" Mission Control
    #    setting is disabled.
    activate_script = (
        f'tell application "{osa_app}" to activate\n'
        f'delay 0.15\n'
        f'tell application "System Events" to tell process "{osa_app}" '
        f'to set frontmost to true'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", activate_script],
            check=False,
            timeout=4,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(
                f"[read_screen] osascript activate exit={result.returncode}: "
                f"{result.stderr.strip()!r}",
                flush=True,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[read_screen] osascript activate failed: {exc}", flush=True)
        return None
    time.sleep(0.45)  # let WindowServer + Mission Control redraw

    # Re-query bounds — the window may have moved when it came forward.
    found = _find_app_window(app, include_offscreen=False)
    if found is not None:
        _wid, fresh_bounds, owner, _on_screen = found
        bounds = fresh_bounds
        print(
            f"[read_screen] post-activate bounds={fresh_bounds} owner={owner!r}",
            flush=True,
        )
    else:
        owner = osa_app
        print(
            f"[read_screen] {osa_app} still not on-screen after activate; "
            f"capturing whole monitor",
            flush=True,
        )
        bounds = None

    with mss.mss() as sct:
        if bounds is not None:
            left, top, width, height = bounds
            region = {"left": left, "top": top, "width": width, "height": height}
        else:
            region = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        sct_img = sct.grab(region)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

    return img, f"{owner} window (activate-then-grab fallback)"


def _capture_app_window(app: str) -> tuple[Any, str] | None:
    """Capture a specific app's window into a PIL Image (Clicky parity).

    Uses ``CGWindowListCreateImage`` with ``kCGWindowImageBoundsIgnoreFraming``,
    which pulls the window's pixels straight from the WindowServer — even
    when another app is occluding it on screen. If that returns nil
    (almost always: Screen Recording permission not granted to the
    Python host on macOS 14+) we fall back to
    ``_activate_app_and_grab`` which forces the app to the front and
    mss-captures.

    Returns ``(PIL.Image, source_label)`` or None.
    """
    try:
        from Quartz import (  # type: ignore[import-not-found]
            CGRectNull,
            CGWindowListCreateImage,
            kCGWindowImageBoundsIgnoreFraming,
            kCGWindowListOptionIncludingWindow,
        )
    except Exception:  # noqa: BLE001
        return None

    found = _find_app_window(app)
    if not found:
        return None
    window_id, bounds, owner, on_screen = found

    try:
        image_ref = CGWindowListCreateImage(
            CGRectNull,
            kCGWindowListOptionIncludingWindow,
            window_id,
            kCGWindowImageBoundsIgnoreFraming,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[read_screen] CGWindowListCreateImage raised: {exc}", flush=True)
        image_ref = None

    if image_ref is None:
        print(
            f"[read_screen] CGWindowListCreateImage returned nil for "
            f"{owner!r} (id={window_id}). Likely missing 'Screen Recording' "
            f"permission for the Python host. Trying activate-then-grab.",
            flush=True,
        )
        return _activate_app_and_grab(app, bounds if on_screen else None)

    try:
        img = _cgimage_to_pil(image_ref)
    except Exception as exc:  # noqa: BLE001
        print(f"[read_screen] CGImage decode failed: {exc}", flush=True)
        return _activate_app_and_grab(app, bounds if on_screen else None)

    if img.width <= 4 or img.height <= 4:
        print(
            f"[read_screen] {owner} window appears minimised "
            f"({img.width}x{img.height}); trying activate-then-grab",
            flush=True,
        )
        return _activate_app_and_grab(app, None)

    suffix = " (on-screen)" if on_screen else " (off-screen, pulled from WindowServer)"
    return img, f"{owner} window{suffix}"


def _encode_for_vision(img) -> str:  # type: ignore[no-untyped-def]
    """Down-scale + JPEG-encode + base64 for the vision endpoint."""
    from PIL import Image

    if img.width > _MAX_SCREENSHOT_DIM or img.height > _MAX_SCREENSHOT_DIM:
        ratio = _MAX_SCREENSHOT_DIM / max(img.width, img.height)
        new_size = (
            max(1, int(img.width * ratio)),
            max(1, int(img.height * ratio)),
        )
        img = img.resize(new_size, Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _capture_via_mss(scope: str) -> Any:
    """Fallback path: full primary monitor or front-most window via mss."""
    import mss

    from PIL import Image

    bounds: tuple[int, int, int, int] | None = None
    if scope == "active_window":
        bounds = _capture_active_window_bounds()

    with mss.mss() as sct:
        if bounds is not None:
            left, top, width, height = bounds
            region = {"left": left, "top": top, "width": width, "height": height}
        else:
            region = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        sct_img = sct.grab(region)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
    return img


def _capture_screen(
    scope: str = "active_window", app: str | None = None
) -> tuple[str, str]:
    """Capture and return ``(base64_jpeg, source_label)``.

    Resolution order:
    1. ``app`` set → Quartz window-ID capture (occluded-friendly, the
       Clicky way). On failure we fall through.
    2. ``scope="active_window"`` → mss crop to front-most window bounds.
    3. ``scope="full"`` (or any fallback) → mss whole primary monitor.

    ``source_label`` describes what was captured — surfaced in logs and
    optionally prepended to the prompt so GLM-4.5V knows the context.
    """
    if app:
        captured = _capture_app_window(app)
        if captured is not None:
            img, label = captured
            return _encode_for_vision(img), label
        print(
            f"[read_screen] no window matched app={app!r} (not running, "
            f"or minimised); falling back to {scope}",
            flush=True,
        )

    img = _capture_via_mss(scope)
    label = "front-most window" if scope == "active_window" else "full primary monitor"
    return _encode_for_vision(img), label


def _build_prompt(question: str, prefs_hint: str, source_label: str) -> str:
    parts = [_PROMPT_PREAMBLE]
    parts.append(f"This screenshot is: {source_label}.")
    if prefs_hint:
        parts.append("User preferences (apply when answering):\n" + prefs_hint)
    parts.append("Margaret's question: " + question.strip())
    return "\n\n".join(parts)


def run(args: dict[str, Any]) -> str:
    question = str(args.get("question", "")).strip()
    if not question:
        return "What would you like me to read for you?"

    # ``app`` is the preferred targeting knob: we use Quartz to grab that
    # specific window's pixels even when another app is occluding it
    # (think Mail.app behind the Chrome tab running Xiexie). Falls back
    # to scope-based mss capture when ``app`` is None or unmatched.
    app_arg = args.get("app")
    app = str(app_arg).strip() if app_arg else ""

    scope = str(args.get("scope") or "full").strip().lower()
    if scope not in ("active_window", "full"):
        scope = "full"

    print(
        f"[read_screen] question={question!r} app={app or '-'} scope={scope}",
        flush=True,
    )

    image_b64, source_label = _capture_screen(scope, app or None)
    print(
        f"[read_screen] captured {source_label} "
        f"({len(image_b64) * 3 // 4 // 1024} KB jpeg, base64={len(image_b64) // 1024} KB)",
        flush=True,
    )

    prefs_hint = _wiki_prefs_hint(Wiki())
    prompt = _build_prompt(question, prefs_hint, source_label)

    llm = get_provider()
    print(
        f"[read_screen] sending to vision model={llm.vision_model or '(unset)'}",
        flush=True,
    )

    try:
        # ``LLMProvider.see`` raises ``RuntimeError`` when no vision model is
        # configured — that's the proxy-only configuration. Let it propagate;
        # the planner's exception path turns it into a spoken explanation.
        reply = (llm.see(image_b64, prompt, mime="image/jpeg") or "").strip()
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
            "Capture a Mac window or the screen and answer a question about "
            "what is visible. Use ONLY when the user references something "
            "they're looking at right now (this email, this page, this "
            "message, the screen). ALWAYS set the `app` argument when the "
            "user names or implies one — examples: 'this email' / 'my "
            "inbox' → app='Mail'; 'this page' / 'this article' → "
            "app='Google Chrome' (or 'Safari' / 'Arc'); 'my Notes' → "
            "app='Notes'; 'this song' → app='Music'. With `app` set we "
            "capture that specific window even when it's behind the "
            "Xiexie chat. Only omit `app` when the user explicitly asks "
            "about the whole screen."
        ),
        parameters={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": (
                        "Specific question to ask about the captured contents."
                    ),
                },
                "app": {
                    "type": "string",
                    "description": (
                        "macOS application name to capture (substring match "
                        "against window owner). Examples: 'Mail', "
                        "'Google Chrome', 'Safari', 'Arc', 'Music', 'Notes', "
                        "'Messages', 'Reminders', 'Calendar'. Aliases also "
                        "accepted: 'email' → Mail, 'browser' → first found "
                        "browser. Leave empty for full-screen capture."
                    ),
                },
                "scope": {
                    "type": "string",
                    "enum": ["full", "active_window"],
                    "default": "full",
                    "description": (
                        "Fallback when `app` isn't set or no matching window "
                        "was found: 'full' = primary monitor, "
                        "'active_window' = front-most app window."
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
    p.add_argument("--app", default="")
    p.add_argument(
        "--scope",
        default="full",
        choices=["active_window", "full"],
    )
    a = p.parse_args()
    print(run({"question": a.question, "app": a.app, "scope": a.scope}))
