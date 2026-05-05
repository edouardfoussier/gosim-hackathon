"""Smoke test for the chained ``report_to_family`` follow-up.

Verifies the Upgrade A path end-to-end *without* paying for an LLM call:

1. Stash a fake phishing follow-up the way ``analyze_email`` would.
2. Construct a ``Planner`` with a mocked ``get_provider`` so its
   ``__init__`` doesn't try to read a real API key.
3. Call ``Planner.plan("yes please")`` and assert the planner's
   early-return path emits a single ``report_to_family`` step with the
   pre-drafted args (no LLM dispatch).
4. Verify ``consume_followup`` actually emptied the stash so a stray
   subsequent "yes" does NOT fire ``report_to_family`` a second time.
5. Restore module state on the way out so other tests aren't poisoned.

Run with::

    cd backend && uv run python tests/test_followup.py
"""

from __future__ import annotations

import sys
import unittest.mock as mock
from pathlib import Path

# Allow running this file directly (``python tests/test_followup.py``)
# without ``-m`` by injecting the backend root into sys.path.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from xiexie.skills import analyze_email as _ae  # noqa: E402


_FAKE_FOLLOWUP = {
    "skill": "report_to_family",
    "args": {
        "summary": {
            "text": (
                "An email from aetnna-secure.com tried to get Mom's "
                "Social Security Number."
            ),
            "signs": [
                "Sender domain typosquats aetna.com.",
                "Link redirects through 4 hops to a Russian IP.",
                "Pattern matches FTC alert from last week.",
            ],
        },
        "recipient_hint": "Lisa",
    },
    "prompt_user": "Want me to send Lisa a heads-up about this?",
}


def _build_planner():
    """Construct a ``Planner`` with a stubbed LLM provider.

    The early-return path never calls ``self.llm.chat``, so a no-op
    MagicMock is enough. We still need ``name`` + ``client.base_url``
    because ``Planner.__init__`` reads them to decide on the dispatch
    model — wrong values just mean the dispatch model defaults to
    ``None`` (fine, never used here).
    """
    from xiexie.planner import Planner

    fake_llm = mock.MagicMock()
    fake_llm.name = "openai"
    fake_llm.client.base_url = "https://api.openai.com/v1"
    with mock.patch("xiexie.planner.planner.get_provider", return_value=fake_llm):
        return Planner()


def test_yes_after_phishing_dispatches_report_to_family() -> None:
    _ae.clear_followup()
    _ae.stash_followup(_FAKE_FOLLOWUP)

    planner = _build_planner()
    result = planner.plan("yes please")

    assert result.steps, f"expected one planned step, got: {result.steps!r}"
    assert len(result.steps) == 1, f"expected exactly one step, got: {result.steps!r}"

    step = result.steps[0]
    assert step.skill == "report_to_family", (
        f"expected report_to_family, got {step.skill!r}"
    )
    assert step.arguments["recipient_hint"] == "Lisa"
    assert step.arguments["summary"]["signs"][0].startswith("Sender domain")
    # Speak_before must be ``None`` — the user just confirmed the gate.
    assert step.speak_before is None, step.speak_before
    print("ok yes_after_phishing_dispatches_report_to_family")


def test_followup_consumed_only_once() -> None:
    _ae.clear_followup()
    _ae.stash_followup(_FAKE_FOLLOWUP)

    planner = _build_planner()
    first = planner.plan("yes")
    assert first.steps and first.steps[0].skill == "report_to_family"

    # Second affirmative with no fresh stash → nothing to short-circuit on.
    # The early-return path bails out, so we expect no steps without
    # falling through to the (mocked) LLM dispatch.
    second = planner.plan("yes")
    assert second.steps == [], (
        f"expected no steps after stash drained, got: {second.steps!r}"
    )
    print("ok followup_consumed_only_once")


def test_long_yes_does_not_short_circuit() -> None:
    _ae.clear_followup()
    _ae.stash_followup(_FAKE_FOLLOWUP)

    # A multi-clause sentence — even one starting with "yes" — should NOT
    # trigger the early-return. Otherwise "yes also open WhatsApp" would
    # silently drop the WhatsApp request and only fire report_to_family.
    planner = _build_planner()
    # Stub the LLM call so the long sentence path doesn't hit the network.
    planner.llm.chat = mock.MagicMock(
        return_value=mock.MagicMock(text="", tool_calls=[])
    )
    result = planner.plan("yes also open WhatsApp for me please thanks")
    assert all(s.skill != "report_to_family" for s in result.steps), (
        f"long sentence wrongly fired follow-up: {result.steps!r}"
    )
    # Stash must still be intact for an actual short "yes" later.
    assert _ae.peek_followup() is not None, "long-form yes wrongly drained stash"
    _ae.clear_followup()
    print("ok long_yes_does_not_short_circuit")


def test_drafted_email_includes_signs() -> None:
    """The dict-shaped summary is rendered with the three signs as bullets.

    We patch ``subprocess.run`` (the ``open`` call that pops the mail
    client) to keep the test environment hermetic.
    """
    from xiexie.skills import report_to_family

    captured: dict = {}

    def _fake_open(cmd, *_, **__):
        captured["cmd"] = cmd
        return mock.MagicMock(returncode=0)

    with mock.patch.object(report_to_family.subprocess, "run", side_effect=_fake_open):
        out = report_to_family.run(
            {
                "summary": {
                    "text": "Quick heads-up about a suspicious email.",
                    "signs": ["sign one.", "sign two.", "sign three."],
                },
                "recipient_hint": "Lisa",
            }
        )
    assert "Lisa" in out, out
    mailto_url = captured["cmd"][1] if captured.get("cmd") else ""
    assert "sign%20one" in mailto_url, "sign 1 missing from drafted body"
    assert "sign%20two" in mailto_url, "sign 2 missing from drafted body"
    assert "sign%20three" in mailto_url, "sign 3 missing from drafted body"
    assert "What%20looked%20off" in mailto_url, (
        "structured summary should add the 'What looked off' header"
    )
    print("ok drafted_email_includes_signs")


def test_string_summary_still_works() -> None:
    """Backward-compat: bare string summaries draft fine, no signs section."""
    from xiexie.skills import report_to_family

    captured: dict = {}

    def _fake_open(cmd, *_, **__):
        captured["cmd"] = cmd
        return mock.MagicMock(returncode=0)

    with mock.patch.object(report_to_family.subprocess, "run", side_effect=_fake_open):
        out = report_to_family.run(
            {"summary": "Quick heads-up about a suspicious email.", "recipient_hint": "Lisa"}
        )
    assert "Lisa" in out, out
    mailto_url = captured["cmd"][1] if captured.get("cmd") else ""
    assert "What%20looked%20off" not in mailto_url, (
        "string-only summary should NOT add the signs header"
    )
    print("ok string_summary_still_works")


def main() -> None:
    try:
        test_yes_after_phishing_dispatches_report_to_family()
        test_followup_consumed_only_once()
        test_long_yes_does_not_short_circuit()
        test_drafted_email_includes_signs()
        test_string_summary_still_works()
        print("all followup tests passed")
    finally:
        _ae.clear_followup()


if __name__ == "__main__":
    main()
