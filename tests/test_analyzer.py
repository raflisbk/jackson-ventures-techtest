"""
Unit tests for agent/analyzer.py.

Isolation strategy:
  - patch("agent.analyzer.OpenAI", return_value=mock_client) — replaces the
    OpenAI class at the module boundary. analyze_company() calls OpenAI(api_key=...)
    and gets mock_client back. No real HTTP requests, no API key needed.
  - mock_client.beta.chat.completions.parse.return_value = mock_response — makes
    the chained parse() call return our synthetic ParsedChatCompletion.

All 7 tests target the public API: analyze_company(name, description, api_key=...).
"""
import os
from unittest.mock import MagicMock, patch

import pytest

from agent.analyzer import CompanyAnalysis, Industry, analyze_company


# ---------------------------------------------------------------------------
# Mock builders
# ---------------------------------------------------------------------------


def _make_mock_client(analysis: CompanyAnalysis) -> MagicMock:
    """Build a mock OpenAI client whose beta.chat.completions.parse() returns
    a synthetic ParsedChatCompletion wrapping the given CompanyAnalysis.

    Structure mirrors the real openai response chain:
      response.choices[0].message.parsed -> CompanyAnalysis
      response.choices[0].message.refusal -> None
    """
    mock_msg = MagicMock()
    mock_msg.parsed = analysis
    mock_msg.refusal = None

    mock_choice = MagicMock()
    mock_choice.message = mock_msg

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.beta.chat.completions.parse.return_value = mock_response

    return mock_client


# ---------------------------------------------------------------------------
# Test 1: Happy path — valid CompanyAnalysis returned (AI-01, AI-02)
# ---------------------------------------------------------------------------


def test_analyze_company_returns_analysis():
    """Happy path: mocked client returns a valid CompanyAnalysis.

    Verifies AI-01 (all four fields populated) and AI-02 (parse() called
    with response_format=CompanyAnalysis — enforced by mock chain setup).
    """
    expected = CompanyAnalysis(
        industry=Industry.FINTECH,
        business_model="B2B SaaS",
        summary="Kimpton is an AI investment research platform.",
        use_case="Analysts use it to automate equity research reports.",
    )
    mock_client = _make_mock_client(expected)

    with patch("agent.analyzer.OpenAI", return_value=mock_client):
        result = analyze_company(
            "Kimpton AI",
            "AI-native investment research platform.",
            api_key="test-key",
        )

    assert result is not None
    assert result.industry == Industry.FINTECH
    assert result.business_model == "B2B SaaS"
    assert result.summary == "Kimpton is an AI investment research platform."
    assert result.use_case == "Analysts use it to automate equity research reports."


# ---------------------------------------------------------------------------
# Test 2: Industry is always a valid enum member (AI-03)
# ---------------------------------------------------------------------------


def test_industry_is_enum_value():
    """The industry field on the result is always a member of Industry.

    Validates AI-03: structured outputs with response_format=CompanyAnalysis
    guarantee the industry string is constrained to the 13 enum values.
    """
    expected = CompanyAnalysis(
        industry=Industry.AI_ML,
        business_model="API/Platform",
        summary="An AI-native productivity tool for developers.",
        use_case="Developers use it to generate production-ready code automatically.",
    )
    mock_client = _make_mock_client(expected)

    with patch("agent.analyzer.OpenAI", return_value=mock_client):
        result = analyze_company(
            "SmolMachines",
            "AI agents for DevOps automation.",
            api_key="test-key",
        )

    assert result is not None
    assert result.industry in list(Industry), (
        f"{result.industry!r} is not a member of the Industry enum"
    )
    assert isinstance(result.industry, Industry), (
        f"Expected Industry instance, got {type(result.industry)}"
    )


# ---------------------------------------------------------------------------
# Test 3: No API key → None returned before OpenAI is instantiated (AI-04)
# ---------------------------------------------------------------------------


def test_analyze_company_returns_none_when_no_api_key():
    """No api_key arg and no OPENAI_API_KEY env var → None returned immediately.

    Validates AI-04 (fault tolerance): the function returns None cleanly
    and never attempts to instantiate the OpenAI client.
    """
    env_without_key = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}

    with patch.dict(os.environ, env_without_key, clear=True):
        with patch("agent.analyzer.OpenAI") as mock_openai_cls:
            result = analyze_company("Acme Corp", "Makes widgets.")

    assert result is None, "Expected None when no API key is available"
    mock_openai_cls.assert_not_called()  # OpenAI() must never be called


# ---------------------------------------------------------------------------
# Test 4: Generic exception from parse() → None returned, not propagated (AI-04)
# ---------------------------------------------------------------------------


def test_analyze_company_returns_none_on_exception():
    """Generic Exception raised inside parse() is caught → None returned.

    Validates AI-04 (per-company error isolation): one company failing must
    not propagate the exception — the caller receives None and can continue.

    Note: generic Exception does NOT trigger tenacity retry (retry condition
    is retry_if_exception_type((RateLimitError, APIConnectionError))). The
    exception propagates directly from _call_openai to the outer except in
    analyze_company, which logs it and returns None.
    """
    mock_client = MagicMock()
    mock_client.beta.chat.completions.parse.side_effect = Exception(
        "Unexpected internal server error"
    )

    with patch("agent.analyzer.OpenAI", return_value=mock_client):
        result = analyze_company("Acme Corp", "Makes widgets.", api_key="test-key")

    assert result is None, (
        "Expected None when parse() raises a generic Exception"
    )


# ---------------------------------------------------------------------------
# Test 5: Model refusal → ValueError → caught → None returned (AI-04)
# ---------------------------------------------------------------------------


def test_refusal_returns_none():
    """Model sets msg.refusal → _call_openai raises ValueError → analyze_company returns None.

    Validates AI-04: a refusal is a non-retried failure path. ValueError is
    not in retry_if_exception_type, so it propagates immediately to the outer
    except block, which logs and returns None.
    """
    mock_msg = MagicMock()
    mock_msg.refusal = "I cannot analyze this content as requested."
    mock_msg.parsed = None  # refusal means parsed is None

    mock_choice = MagicMock()
    mock_choice.message = mock_msg

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.beta.chat.completions.parse.return_value = mock_response

    with patch("agent.analyzer.OpenAI", return_value=mock_client):
        result = analyze_company(
            "BadCorp", "Suspicious description.", api_key="test-key"
        )

    assert result is None, (
        "Expected None when OpenAI returns a refusal message"
    )


# ---------------------------------------------------------------------------
# Test 6: parse() is called with company_name and description (AI-02)
# ---------------------------------------------------------------------------


def test_analyze_company_passes_name_and_description():
    """parse() is called with both company_name and description in the user message.

    Validates AI-02: the structured output call must receive the correct input
    data. Asserts that the user message content string contains both values.
    """
    expected = CompanyAnalysis(
        industry=Industry.DEVTOOLS,
        business_model="B2B SaaS",
        summary="A developer observability platform.",
        use_case="Engineers use it to debug production issues in real time.",
    )
    mock_client = _make_mock_client(expected)

    with patch("agent.analyzer.OpenAI", return_value=mock_client):
        analyze_company(
            "Arga Labs",
            "Developer observability platform.",
            api_key="test-key",
        )

    # Retrieve the actual call arguments made to parse()
    parse_call = mock_client.beta.chat.completions.parse.call_args
    assert parse_call is not None, "parse() was never called"

    # parse() is called with keyword args: model=, messages=, response_format=, temperature=
    messages = parse_call.kwargs["messages"]
    user_messages = [m for m in messages if m.get("role") == "user"]
    assert len(user_messages) == 1, (
        f"Expected exactly 1 user message, found {len(user_messages)}"
    )

    user_content = user_messages[0]["content"]
    assert "Arga Labs" in user_content, (
        f"company_name 'Arga Labs' not found in user message: {user_content!r}"
    )
    assert "Developer observability platform." in user_content, (
        f"description not found in user message: {user_content!r}"
    )


# ---------------------------------------------------------------------------
# Test 7 (bonus): All 13 Industry enum string values are correct (AI-03)
# ---------------------------------------------------------------------------


def test_industry_enum_values():
    """All 13 Industry enum members have the correct string values.

    Validates AI-03: the taxonomy is precise. A typo in a value (e.g.
    "Fintech" vs "FinTech") would break downstream filtering and display.
    """
    expected_values = {
        "FinTech",
        "HealthTech",
        "AI/ML",
        "DevTools",
        "Enterprise SaaS",
        "E-Commerce",
        "EdTech",
        "Defense/Security",
        "Robotics/Hardware",
        "Biotech",
        "Media/Entertainment",
        "Marketplace",
        "Other",
    }

    actual_values = {member.value for member in Industry}

    assert actual_values == expected_values, (
        f"Taxonomy mismatch.\n"
        f"  Missing: {expected_values - actual_values}\n"
        f"  Extra:   {actual_values - expected_values}"
    )
    assert len(actual_values) == 13, (
        f"Expected 13 industry values, found {len(actual_values)}: {sorted(actual_values)}"
    )
