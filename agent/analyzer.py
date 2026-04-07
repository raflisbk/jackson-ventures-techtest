"""
AI analysis module for YC companies.

Isolation contract: this file imports NOTHING from app/ or scraper/.
It receives raw primitives (str) and returns a Pydantic model or None.

Public interface:
    analyze_company(company_name, description, api_key=None) -> Optional[CompanyAnalysis]
"""
import logging
import os
from enum import Enum
from typing import Optional

from openai import APIConnectionError, OpenAI, RateLimitError
from pydantic import BaseModel
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert startup analyst specializing in Y Combinator companies.
Analyze the provided company name and description, then return structured JSON matching the schema exactly.

Rules:
- industry: pick the SINGLE best-fit category from the enum. For AI-native companies in a vertical \
(health, finance, etc.), use the vertical category, not AI/ML.
- business_model: use concise labels like "B2B SaaS", "API/Platform", "Marketplace", "B2C App", \
"B2B Enterprise"
- summary: 1-2 sentences, plain English, no marketing language, focus on what the product actually does
- use_case: one concrete sentence describing the primary user action, \
e.g. "Sales reps use it to get pre-call notes automatically"
- If the description is vague or a placeholder, make your best reasonable inference from the company \
name and any available context"""


# ---------------------------------------------------------------------------
# Structured output types (live in analyzer.py — NOT in app/models.py)
# ---------------------------------------------------------------------------


class Industry(str, Enum):
    """Controlled taxonomy for YC company verticals (AI-03).

    13 values derived from analysis of 50 S25 companies.
    OTHER is the fallback for genuinely ambiguous cases.
    Storing .value (the string) ensures DB column stays as clean text.
    """

    FINTECH = "FinTech"
    HEALTHTECH = "HealthTech"
    AI_ML = "AI/ML"
    DEVTOOLS = "DevTools"
    ENTERPRISE_SAAS = "Enterprise SaaS"
    ECOMMERCE = "E-Commerce"
    EDTECH = "EdTech"
    DEFENSE = "Defense/Security"
    ROBOTICS = "Robotics/Hardware"
    BIOTECH = "Biotech"
    MEDIA_ENTERTAINMENT = "Media/Entertainment"
    MARKETPLACE = "Marketplace"
    OTHER = "Other"


class CompanyAnalysis(BaseModel):
    """Pydantic model used as response_format= in client.beta.chat.completions.parse().

    OpenAI SDK converts this class to a JSON schema automatically.
    All fields are required — the model must populate every field.
    """

    industry: Industry
    business_model: str  # e.g. "B2B SaaS", "Marketplace", "API/Platform"
    summary: str         # ≤ 2 sentences, plain English
    use_case: str        # concrete end-user action, ≤ 1 sentence


# ---------------------------------------------------------------------------
# OpenAI call — wrapped by tenacity (AI-02, AI-05)
# ---------------------------------------------------------------------------


@retry(
    retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(5),
    reraise=True,
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def _call_openai(client: OpenAI, company_name: str, description: str) -> CompanyAnalysis:
    """Call OpenAI structured outputs API with retry on transient errors.

    Decorating only this inner function (not the loop) means one 429 retries
    only the single company call — not the entire batch (AI-05, anti-pattern AI-P3).

    reraise=True: after 5 exhausted attempts the exception propagates to the
    outer try/except in analyze_company(), which logs and returns None (AI-04).
    """
    response = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Company: {company_name}\nDescription: {description}",
            },
        ],
        response_format=CompanyAnalysis,
        temperature=0.2,
    )
    msg = response.choices[0].message
    if msg.refusal:
        # refusal means msg.parsed is None — raise to trigger outer except, not retry
        raise ValueError(
            f"OpenAI refused to analyze {company_name!r}: {msg.refusal}"
        )
    return msg.parsed


# ---------------------------------------------------------------------------
# Public API (AI-01, AI-04)
# ---------------------------------------------------------------------------


def analyze_company(
    company_name: str,
    description: str,
    api_key: Optional[str] = None,
) -> Optional[CompanyAnalysis]:
    """Analyze a single company using OpenAI Structured Outputs.

    Returns CompanyAnalysis on success, None on any failure.
    NEVER raises — all exceptions are caught and logged here.

    Import boundary: this function imports nothing from app/ or scraper/.
    It receives primitives and returns a Pydantic model or None.

    Args:
        company_name: Company display name (e.g. "Kimpton AI").
        description:  Raw description string from the DB (may be a placeholder).
        api_key:      Optional override — falls back to OPENAI_API_KEY env var.

    Returns:
        CompanyAnalysis with all four fields populated, or None on any error.
    """
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        logger.error(
            "OPENAI_API_KEY not set — skipping analysis for %r", company_name
        )
        return None

    client = OpenAI(api_key=key)
    try:
        return _call_openai(client, company_name, description)
    except Exception as exc:
        logger.error("Failed to analyze %r: %s", company_name, exc)
        return None
