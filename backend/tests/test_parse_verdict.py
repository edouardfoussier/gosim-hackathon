"""Smoke tests for ``analyze_email.parse_verdict`` (no LLM, no network).

Hackathon-grade: just `print` + `assert`. Run with::

    cd backend && uv run python -m tests.test_parse_verdict
"""

from __future__ import annotations

from xiexie.skills.analyze_email import (
    ALLOWED_CONFIDENCE,
    ALLOWED_VERDICTS,
    DEFAULT_VERDICT,
    parse_verdict,
)


def _check_shape(v: dict) -> None:
    assert v["verdict"] in ALLOWED_VERDICTS, v
    assert v["confidence"] in ALLOWED_CONFIDENCE, v
    assert isinstance(v["signs"], list) and v["signs"], v
    assert isinstance(v["recommended_actions"], list) and v["recommended_actions"], v
    assert isinstance(v["speak_aloud"], str) and v["speak_aloud"], v


def test_happy_path_plain_json() -> None:
    raw = (
        '{"verdict": "phishing", "confidence": "high", '
        '"signs": ["typo domain", "asks for SSN"], '
        '"recommended_actions": ["Don\'t click."], '
        '"speak_aloud": "This one looks like a scam."}'
    )
    v = parse_verdict(raw)
    _check_shape(v)
    assert v["verdict"] == "phishing"
    assert v["confidence"] == "high"
    assert "typo domain" in v["signs"]
    print("ok happy_path_plain_json")


def test_strips_code_fence() -> None:
    raw = (
        "```json\n"
        '{"verdict": "suspicious", "confidence": "medium", '
        '"signs": ["s"], "recommended_actions": ["a"], "speak_aloud": "x"}\n'
        "```"
    )
    v = parse_verdict(raw)
    _check_shape(v)
    assert v["verdict"] == "suspicious"
    print("ok strips_code_fence")


def test_unwraps_output_envelope() -> None:
    raw = (
        '{"output": {"verdict": "safe", "confidence": "high", '
        '"signs": ["clean"], "recommended_actions": ["No action."], '
        '"speak_aloud": "Looks fine to me."}}'
    )
    v = parse_verdict(raw)
    _check_shape(v)
    assert v["verdict"] == "safe"
    print("ok unwraps_output_envelope")


def test_unwraps_nested_verdict_envelope() -> None:
    raw = (
        '{"verdict": {"verdict": "phishing", "confidence": "high", '
        '"signs": ["x"], "recommended_actions": ["a"], "speak_aloud": "s"}}'
    )
    v = parse_verdict(raw)
    _check_shape(v)
    assert v["verdict"] == "phishing"
    print("ok unwraps_nested_verdict_envelope")


def test_unwraps_data_envelope() -> None:
    raw = (
        '{"data": {"verdict": "unclear", "confidence": "low", '
        '"signs": ["uncertain"], "recommended_actions": ["Ask Lisa."], '
        '"speak_aloud": "I am not sure."}}'
    )
    v = parse_verdict(raw)
    _check_shape(v)
    assert v["verdict"] == "unclear"
    print("ok unwraps_data_envelope")


def test_repair_handles_trailing_comma_and_smart_quotes() -> None:
    raw = (
        "{\u201cverdict\u201d: \u201cphishing\u201d, \u201cconfidence\u201d: \u201chigh\u201d, "
        '"signs": ["typo domain",], '
        '"recommended_actions": ["Don\'t click."], '
        '"speak_aloud": "This is a scam."}'
    )
    v = parse_verdict(raw)
    _check_shape(v)
    # json_repair should still arrive at phishing/high
    assert v["verdict"] == "phishing"
    assert v["confidence"] == "high"
    print("ok repair_handles_trailing_comma_and_smart_quotes")


def test_missing_keys_get_defaults() -> None:
    raw = '{"verdict": "phishing"}'
    v = parse_verdict(raw)
    _check_shape(v)
    assert v["verdict"] == "phishing"
    assert v["confidence"] == DEFAULT_VERDICT["confidence"]
    assert v["signs"] == DEFAULT_VERDICT["signs"]
    print("ok missing_keys_get_defaults")


def test_garbage_input_returns_default() -> None:
    v = parse_verdict("not json at all, just a sentence")
    # json_repair may return an empty dict; either way we want defaults
    _check_shape(v)
    assert v["verdict"] == "unclear"
    print("ok garbage_input_returns_default")


def test_verdict_label_normalised() -> None:
    raw = (
        '{"verdict": "PHISHING", "confidence": "HIGH", '
        '"signs": ["x"], "recommended_actions": ["a"], "speak_aloud": "s"}'
    )
    v = parse_verdict(raw)
    assert v["verdict"] == "phishing"
    assert v["confidence"] == "high"
    print("ok verdict_label_normalised")


def test_extracts_json_from_prose() -> None:
    """GLM-5.x sometimes prepends/appends commentary; we rescue the JSON."""
    raw = (
        "Here is the analysis you asked for:\n\n"
        '{"verdict": "phishing", "confidence": "high", '
        '"signs": ["typo domain"], "recommended_actions": ["Don\'t click."], '
        '"speak_aloud": "This is a scam."}\n\n'
        "Let me know if you want more detail."
    )
    v = parse_verdict(raw)
    _check_shape(v)
    assert v["verdict"] == "phishing"
    assert v["confidence"] == "high"
    print("ok extracts_json_from_prose")


def test_recovers_verdict_from_pure_prose() -> None:
    """When the model dumps a markdown analysis without any JSON, the prose
    extractor must still recover a phishing verdict."""
    raw = (
        "**Sender domain:** aetnna-secure.com - this is a typosquatted domain.\n\n"
        "**Authentication:** SPF=fail, DKIM=none, DMARC=fail.\n\n"
        "**Confidence:** This is clearly phishing with high confidence.\n\n"
        "1. Typosquatted domain (aetnna vs aetna)\n"
        "2. All authentication checks failed\n"
        "3. Asks for SSN and credit card together\n"
    )
    v = parse_verdict(raw)
    _check_shape(v)
    assert v["verdict"] == "phishing", v
    assert v["confidence"] == "high", v
    # At least one sign should mention typosquat or SSN.
    assert any(
        "typo" in s.lower() or "ssn" in s.lower() or "auth" in s.lower()
        for s in v["signs"]
    ), v["signs"]
    print("ok recovers_verdict_from_pure_prose")


def test_recovers_safe_from_prose() -> None:
    raw = (
        "After reviewing the email, this looks safe with high confidence.\n"
        "- Sender matches the user's known account\n"
        "- No urgent language\n"
        "- Link points back to the same domain\n"
    )
    v = parse_verdict(raw)
    _check_shape(v)
    assert v["verdict"] == "safe", v
    assert v["confidence"] == "high", v
    print("ok recovers_safe_from_prose")


def main() -> None:
    test_happy_path_plain_json()
    test_strips_code_fence()
    test_unwraps_output_envelope()
    test_unwraps_nested_verdict_envelope()
    test_unwraps_data_envelope()
    test_repair_handles_trailing_comma_and_smart_quotes()
    test_missing_keys_get_defaults()
    test_garbage_input_returns_default()
    test_verdict_label_normalised()
    test_extracts_json_from_prose()
    test_recovers_verdict_from_pure_prose()
    test_recovers_safe_from_prose()
    print("all parse_verdict tests passed")


if __name__ == "__main__":
    main()
