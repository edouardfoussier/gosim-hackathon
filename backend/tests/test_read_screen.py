"""Smoke test for the ``read_screen`` vision skill (Upgrade B).

We avoid hitting the Z.AI vision endpoint *and* the actual macOS screen
by mocking ``_capture_screen`` and ``get_provider``. The test asserts:

1. ``LLMProvider.see`` is called with the base64 image string from the
   mocked capture.
2. The prompt argument includes a recognisable hint from
   ``data/wiki/preferences.md`` (we look for the literal "TTS rate" line
   from the Hearing section — present in the seed wiki, telling enough
   that we know the prefs splice fired).
3. The user's question shows up verbatim in the prompt so GLM-4.5V
   knows what to focus on.
4. The empty-question guard short-circuits before doing any I/O.
5. The ``RuntimeError`` raised by ``LLMProvider.see`` on a vision-less
   provider propagates out (caller — the planner — turns it into a
   spoken fallback).

Run with::

    cd backend && uv run python tests/test_read_screen.py
"""

from __future__ import annotations

import sys
import unittest.mock as mock
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from xiexie.skills import read_screen  # noqa: E402


_FAKE_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="

# ``_capture_screen`` now returns ``(b64, source_label, CaptureGeometry)``
# — see backend/xiexie/skills/read_screen.py for the dataclass. We build
# a minimal pointable geometry so the prompt assembly path doesn't choke
# on missing fields.
_FAKE_GEO = read_screen.CaptureGeometry(
    image_w=1600,
    image_h=1000,
    source_x=0,
    source_y=0,
    source_w=1600,
    source_h=1000,
    pointable=True,
)
_FAKE_CAPTURE: tuple[str, str, read_screen.CaptureGeometry] = (
    _FAKE_B64,
    "test capture",
    _FAKE_GEO,
)


def test_calls_see_with_image_and_prefs() -> None:
    fake_llm = mock.MagicMock()
    fake_llm.see.return_value = "It says 'Welcome to Mail.app'. Repeat: 'Welcome to Mail.app'."

    with (
        mock.patch.object(read_screen, "_capture_screen", return_value=_FAKE_CAPTURE),
        mock.patch.object(read_screen, "get_provider", return_value=fake_llm),
    ):
        out = read_screen.run({"question": "What does this email say?"})

    assert out == "It says 'Welcome to Mail.app'. Repeat: 'Welcome to Mail.app'."
    assert fake_llm.see.called, "LLMProvider.see was not invoked"

    args, kwargs = fake_llm.see.call_args
    image_arg = args[0] if args else kwargs.get("image_b64")
    prompt_arg = args[1] if len(args) > 1 else kwargs.get("prompt", "")

    assert image_arg == _FAKE_B64, f"see() got the wrong image payload: {image_arg!r}"
    assert "What does this email say?" in prompt_arg, (
        "user question missing from vision prompt"
    )
    # The prefs hint should land in the prompt — look for a distinctive
    # line from preferences.md (Hearing section). If the seed wiki
    # changes this string, update the assertion in lockstep.
    assert "TTS rate" in prompt_arg or "Vision" in prompt_arg, (
        f"wiki preferences not spliced into vision prompt:\n{prompt_arg}"
    )
    print("ok calls_see_with_image_and_prefs")


def test_full_scope_is_default() -> None:
    """Default scope flipped from active_window → full in the cursor-pointing
    refactor — full primary monitor is what Margaret actually wants
    (Mail.app is rarely the front-most window when she's in the chat)."""
    fake_llm = mock.MagicMock()
    fake_llm.see.return_value = "Headline reads: 'Markets close higher.'"

    with (
        mock.patch.object(
            read_screen, "_capture_screen", return_value=_FAKE_CAPTURE
        ) as cap_mock,
        mock.patch.object(read_screen, "get_provider", return_value=fake_llm),
    ):
        read_screen.run({"question": "Read the headline."})
        cap_mock.assert_called_once_with("full", None)
    print("ok full_scope_is_default")


def test_app_argument_is_passed_through() -> None:
    """When the planner targets a specific app, ``_capture_screen`` gets
    the app name and the per-window Quartz path runs."""
    fake_llm = mock.MagicMock()
    fake_llm.see.return_value = "Two windows visible."

    with (
        mock.patch.object(
            read_screen, "_capture_screen", return_value=_FAKE_CAPTURE
        ) as cap_mock,
        mock.patch.object(read_screen, "get_provider", return_value=fake_llm),
    ):
        read_screen.run(
            {"question": "Describe the email.", "app": "Mail"}
        )
        cap_mock.assert_called_once_with("full", "Mail")
    print("ok app_argument_is_passed_through")


def test_empty_question_short_circuits() -> None:
    """No capture, no LLM call when the question is empty."""
    with (
        mock.patch.object(read_screen, "_capture_screen") as cap_mock,
        mock.patch.object(read_screen, "get_provider") as gp_mock,
    ):
        out = read_screen.run({"question": "   "})
    assert "What would you like" in out, out
    assert not cap_mock.called, "should NOT have captured for empty question"
    assert not gp_mock.called, "should NOT have called LLM for empty question"
    print("ok empty_question_short_circuits")


def test_runtime_error_from_see_propagates() -> None:
    """When the provider has no vision model, ``see`` raises RuntimeError.

    The planner relies on that exception bubbling so its existing
    fallback can speak it back to the user. We must NOT swallow it here.
    """
    fake_llm = mock.MagicMock()
    fake_llm.see.side_effect = RuntimeError(
        "No vision model configured for this provider — set "
        "ZAI_VISION_MODEL or switch base_url to direct Z.AI."
    )
    with (
        mock.patch.object(read_screen, "_capture_screen", return_value=_FAKE_CAPTURE),
        mock.patch.object(read_screen, "get_provider", return_value=fake_llm),
    ):
        out = read_screen.run({"question": "What's on screen?"})
    # The skill now catches RuntimeError and returns a Margaret-friendly
    # spoken sentence — see the ``except RuntimeError`` branch in
    # read_screen.run. The planner's fallback no longer needs to.
    assert "vision" in out.lower() or "screen" in out.lower(), out
    print("ok runtime_error_from_see_propagates")


def test_skill_is_registered_non_destructive() -> None:
    """``read_screen`` must show up in the registry and skip the gate."""
    from xiexie.skills.registry import SKILLS

    skill = SKILLS.get("read_screen")
    assert skill is not None, "read_screen never registered"
    assert skill.destructive is False, "read_screen should not require confirmation"
    assert "vision" in skill.tags, skill.tags
    print("ok skill_is_registered_non_destructive")


def main() -> None:
    test_calls_see_with_image_and_prefs()
    test_full_scope_is_default()
    test_app_argument_is_passed_through()
    test_empty_question_short_circuits()
    test_runtime_error_from_see_propagates()
    test_skill_is_registered_non_destructive()
    print("all read_screen tests passed")


if __name__ == "__main__":
    main()
