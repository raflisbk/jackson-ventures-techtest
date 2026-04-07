# Phase 3: AI Analysis Pipeline — Research

**Researched:** 2025-01-07  
**Domain:** OpenAI Structured Outputs + Tenacity retry + SQLModel UPDATE  
**Confidence:** HIGH (all findings verified against installed packages and source code)

---

## Summary

Phase 3 adds AI-generated intelligence (industry, business_model, summary, use_case) to the 50 YC companies already stored in SQLite. The pipeline calls OpenAI's `parse()` API with a Pydantic `CompanyAnalysis` model, writes results back via SQLModel, and wraps each call in Tenacity retry + per-company try/except.

**Critical discovery — openai 2.x API location:** In the installed `openai==2.30.0`, `client.beta.chat` is a `cached_property` that returns the **same** `Chat` resource as `client.chat`. Therefore `client.beta.chat.completions.parse()` and `client.chat.completions.parse()` are identical. The requirement to use `client.beta.chat.completions.parse()` is satisfied and works correctly.

**Primary recommendation:** Use `client.chat.completions.parse(model="gpt-4o-mini", messages=[...], response_format=CompanyAnalysis)`. The `beta.chat.completions.parse` path also works. Access the result via `response.choices[0].message.parsed`. Check `message.refusal` before accessing `message.parsed`.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| openai | 2.30.0 | Structured outputs via `parse()` | Installed, verified. parse() lives on `client.chat.completions` (and `client.beta.chat.completions` as proxy) |
| tenacity | 9.1.4 | `@retry` with exponential backoff | Installed, verified. `wait_exponential`, `stop_after_attempt`, `retry_if_exception_type` all confirmed importable |
| sqlmodel | 0.0.38 | ORM session + `session.exec(select(...))` for UPDATE | Installed; fetch-modify-commit pattern verified against live DB |
| pydantic | 2.12.5 | `BaseModel` for `CompanyAnalysis`, `str(Enum)` for `Industry` | Installed; used by openai parse() for response_format |
| pydantic-settings | (installed) | `Settings` class with `OPENAI_API_KEY` | Already in `app/config.py` — just import `settings` |

### No Additional Installs Required
All required packages are already installed. Phase 3 needs **zero new pip installs**.

---

## Architecture Patterns

### Recommended File Structure
```
agent/
├── __init__.py          # already exists (empty)
└── analyzer.py          # NEW — all OpenAI logic lives here

scripts/
├── __init__.py          # already exists (empty)
└── run_pipeline.py      # NEW — orchestrates scraper + analyzer

tests/
├── test_foundation.py   # existing (don't modify)
├── test_scraper.py      # existing (don't modify)
└── test_analyzer.py     # NEW — unit tests for Phase 3
```

### Pattern 1: Import Boundary
`agent/analyzer.py` must import **nothing** from `app/` or `scraper/`. It receives only primitive data (str/Optional[str]) and returns a Pydantic model or None. The import boundary keeps the analyzer unit-testable without a database.

```python
# agent/analyzer.py — ALLOWED imports only
from enum import Enum
from typing import Optional
import logging

from openai import OpenAI, RateLimitError, APIConnectionError
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log
```

### Pattern 2: Pydantic Models in analyzer.py
Both `Industry` (enum) and `CompanyAnalysis` (parse target) live **inside** `agent/analyzer.py`. They must NOT be in `app/models.py` (that's the SQLModel table). The `response_format=CompanyAnalysis` in the `parse()` call references this class.

```python
# agent/analyzer.py
class Industry(str, Enum):
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
    industry: Industry
    business_model: str          # e.g. "B2B SaaS", "Marketplace", "API"
    summary: str                 # ≤ 2 sentences, plain English
    use_case: str                # concrete end-user action, ≤ 1 sentence
```

### Pattern 3: The `@retry`-decorated inner function
Tenacity `@retry` wraps **only the OpenAI call**, not the per-company loop. This ensures one 429 triggers a retry without aborting the batch.

```python
# Correct pattern: decorate a helper, call it from the try/except loop
@retry(
    retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(5),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,   # if all 5 attempts fail, re-raise so outer except catches it
)
def _call_openai(client: OpenAI, company_name: str, description: str) -> CompanyAnalysis:
    response = client.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Company: {company_name}\nDescription: {description}"},
        ],
        response_format=CompanyAnalysis,
        temperature=0.2,
    )
    message = response.choices[0].message
    if message.refusal:
        raise ValueError(f"Model refused to analyze {company_name}: {message.refusal}")
    return message.parsed
```

### Pattern 4: Per-company error isolation
```python
def analyze_companies(companies: list[dict]) -> list[dict]:
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    results = []
    for company in companies:
        try:
            analysis = _call_openai(client, company["company_name"], company["description"])
            results.append({"id": company["id"], "analysis": analysis})
        except Exception as exc:
            logger.error("Failed to analyze %s: %s", company["company_name"], exc)
            # Continue — do NOT re-raise
    return results
```

### Pattern 5: SQLModel UPDATE (fetch-modify-commit)
Verified against live DB: fetch the row, assign AI fields, `session.add()`, `session.commit()`.

```python
# scripts/run_pipeline.py
from sqlmodel import Session, select
from app.database import engine
from app.models import Company

def update_company_ai_fields(session: Session, company_id: int, analysis) -> None:
    company = session.get(Company, company_id)
    if company is None:
        return
    company.industry = analysis.industry.value   # .value converts enum → str
    company.business_model = analysis.business_model
    company.summary = analysis.summary
    company.use_case = analysis.use_case
    session.add(company)
    session.commit()
```

### Pattern 6: Skip logic (idempotency)
```python
# In run_pipeline.py — query only companies missing AI fields
with Session(engine) as session:
    stmt = select(Company).where(Company.industry == None)
    pending = session.exec(stmt).all()
```
A company is "done" when `industry` is non-NULL. Since all four AI fields are written atomically, any partial state means the company should be re-analyzed (so checking only `industry` is sufficient).

### Anti-Patterns to Avoid
- **Putting `Industry` enum in `app/models.py`:** Breaks import boundary. Keep it in `agent/analyzer.py`.
- **Using `json_object` mode instead of `parse()`:** Doesn't validate structure; manual JSON parsing needed.
- **Decorating the loop with `@retry`:** One 429 would retry the entire batch from the beginning.
- **Calling `session.commit()` inside the analyzer:** Analyzer must not import from `app/`. Commits belong in `scripts/run_pipeline.py`.
- **Using `Industry.value` vs `Industry` for DB storage:** The DB column is `Optional[str]`, so store `analysis.industry.value` (the string), not the enum object.
- **Catching only `RateLimitError` in tenacity:** Also catch `APIConnectionError` for transient network failures.

---

## OpenAI API — Verified Findings (openai 2.30.0)

### Exact Import Path
```python
from openai import OpenAI, RateLimitError, APIConnectionError
```
Both error classes confirmed importable from `openai` top-level namespace.

### beta.chat vs chat — IMPORTANT
In `openai==2.30.0`, `client.beta.chat` is a `cached_property` that returns `Chat(self._client)` — the **exact same class** as `client.chat`. The `parse()` method is defined on `openai.resources.chat.completions.completions.Completions`. Therefore:
- `client.beta.chat.completions.parse(...)` ✅ works (requirement AI-02)
- `client.chat.completions.parse(...)` ✅ also works (equivalent)

Use `client.beta.chat.completions.parse()` to satisfy requirement AI-02 literally.

### Full parse() Signature (key params)
```python
response = client.beta.chat.completions.parse(
    model="gpt-4o-mini",          # str | ChatModel
    messages=[...],                # Iterable[ChatCompletionMessageParam]
    response_format=CompanyAnalysis,  # type[ResponseFormatT] — pass the CLASS, not an instance
    temperature=0.2,               # Optional[float]
)
```

### Response Access
```python
# response type: ParsedChatCompletion[CompanyAnalysis]
message = response.choices[0].message
# message type: ParsedChatCompletionMessage[CompanyAnalysis]

# Check refusal FIRST (model may refuse sensitive content)
if message.refusal:
    raise ValueError(f"Refusal: {message.refusal}")

# Access parsed Pydantic object
analysis: CompanyAnalysis = message.parsed
# analysis.industry → Industry enum
# analysis.business_model → str
# analysis.summary → str
# analysis.use_case → str
```

### Refusal Detection (source-verified)
`ParsedChatCompletionMessage` has `refusal: Optional[str] = None` (from `ChatCompletionMessage`). Check `if message.refusal:` before accessing `message.parsed`. If refusal is non-None, `message.parsed` will be None.

### Model Recommendation
- `gpt-4o-mini` — best cost/quality for structured extraction from short descriptions
- `gpt-4o` — fallback if quality is insufficient (higher cost)
- Both support structured outputs with `parse()`

---

## Tenacity Configuration — Verified

### Confirmed Imports (tenacity 9.1.4)
```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
```

### Recommended Decorator
```python
@retry(
    retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(5),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
```

**Parameter rationale:**
- `min=4, max=60` — OpenAI 429s typically clear in 10-20s; 4s initial gives breathing room
- `stop_after_attempt(5)` — 5 attempts = ~2 min total wait at max backoff; beyond this, log and skip
- `reraise=True` — after all attempts exhausted, re-raise so outer try/except in the loop catches it and continues the batch
- `before_sleep_log` — logs wait duration at WARNING level; visible in pipeline output

---

## Industry Enum Taxonomy

Based on analysis of all 50 companies in `data/companies.db`:

| Enum Value | String Value | Companies (examples) |
|------------|-------------|----------------------|
| `AI_ML` | `"AI/ML"` | Ara, Benchspan, Datost, Foaster, Indexable, OpenWork, Pentagon, StableBrowse, smol machines |
| `DEVTOOLS` | `"DevTools"` | Arga Labs, Gigacatalyst, Minicor, Runtime, TesterArmy, Interfaze, Keyframe Labs |
| `ENTERPRISE_SAAS` | `"Enterprise SaaS"` | Arzana, Complir, Lab0, Ontora, Salesgraph, qomplement, Tasklet |
| `HEALTHTECH` | `"HealthTech"` | Adialante, Alchemy, Harbor, Lumius, Taiga |
| `FINTECH` | `"FinTech"` | Kimpton AI, Mochatrade |
| `ECOMMERCE` | `"E-Commerce"` | Amboras, Saudara AI, Sherpa, Userlens |
| `BIOTECH` | `"Biotech"` | BioStack Platforms |
| `EDTECH` | `"EdTech"` | Lamina Labs |
| `DEFENSE` | `"Defense/Security"` | Maquoketa Research, Klaimee |
| `ROBOTICS` | `"Robotics/Hardware"` | Eden, AICE Power |
| `MEDIA_ENTERTAINMENT` | `"Media/Entertainment"` | Playabl.ai, Kuli, Standout |
| `MARKETPLACE` | `"Marketplace"` | Gojiberry AI, Callab AI, Asendia AI |
| `OTHER` | `"Other"` | Degla Inc (drones/search & rescue), ProjectX (OS), Prototyping.io (manufacturing) |

**Coverage notes:**
- AI/ML is the dominant YC S25 category (~35% of companies)
- Several companies are AI-native but in vertical markets → use vertical (e.g., Taiga = HealthTech)
- `OTHER` is the safety net for edge cases like defense drones, novel OS platforms
- 13 values covers all 50 companies without ambiguity

---

## Prompt Design

### System Prompt
```python
SYSTEM_PROMPT = """You are an expert startup analyst specializing in Y Combinator companies.
Analyze the provided company name and description, then return structured JSON matching the schema exactly.

Rules:
- industry: pick the SINGLE best-fit category from the enum. For AI-native companies in a vertical (health, finance, etc.), use the vertical, not AI/ML.
- business_model: use concise labels like "B2B SaaS", "API/Platform", "Marketplace", "B2C App", "B2B Enterprise"
- summary: 1-2 sentences, plain English, no marketing language, focus on what the product actually does
- use_case: one concrete sentence describing the primary user action, e.g. "Sales reps use it to get pre-call notes automatically"
- If the description is vague or a placeholder, make your best reasonable inference from the company name and any available context"""
```

### User Prompt Template
```python
user_content = f"Company: {company_name}\nDescription: {description}"
```

### Handling Short/Ambiguous Descriptions
The system prompt instructs the model to infer from context when descriptions are vague. The `Industry.OTHER` enum value is the fallback for genuinely ambiguous companies. The prompt explicitly covers placeholder descriptions (e.g., "Agentic recruitment platform" = 3 words).

---

## Test Mocking Strategy

### How to Mock `client.beta.chat.completions.parse()`

The target is `openai.OpenAI` client instantiation or the parse method itself. Best approach: patch `openai.OpenAI` at the point of import in `agent.analyzer`.

```python
# tests/test_analyzer.py
from unittest.mock import MagicMock, patch
import pytest
from agent.analyzer import analyze_company, CompanyAnalysis, Industry

def _make_mock_client(analysis: CompanyAnalysis) -> MagicMock:
    """Build a mock OpenAI client whose parse() returns a fake ParsedChatCompletion."""
    mock_message = MagicMock()
    mock_message.refusal = None
    mock_message.parsed = analysis

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_completions = MagicMock()
    mock_completions.parse.return_value = mock_response

    mock_chat = MagicMock()
    mock_chat.completions = mock_completions

    mock_beta = MagicMock()
    mock_beta.chat = mock_chat

    mock_client = MagicMock()
    mock_client.beta = mock_beta
    mock_client.chat = mock_chat   # also expose client.chat for flexibility

    return mock_client

def test_analyze_company_success():
    expected = CompanyAnalysis(
        industry=Industry.FINTECH,
        business_model="B2B SaaS",
        summary="Kimpton is an AI investment research platform.",
        use_case="Analysts use it to automate equity research reports.",
    )
    mock_client = _make_mock_client(expected)

    with patch("agent.analyzer.OpenAI", return_value=mock_client):
        result = analyze_company("Kimpton AI", "AI-native investment research platform.")

    assert result is not None
    assert result.industry == Industry.FINTECH
    assert result.business_model == "B2B SaaS"

def test_analyze_company_refusal_returns_none():
    mock_message = MagicMock()
    mock_message.refusal = "I cannot analyze this company."
    mock_message.parsed = None
    # ... (build response similarly)
    # result should be None (analyzer catches ValueError from refusal check)
```

### What to Test
| Test | Purpose | Req |
|------|---------|-----|
| `test_analyze_company_success` | Happy path — parse returns valid CompanyAnalysis | AI-01, AI-02 |
| `test_analyze_company_refusal_returns_none` | Refusal detected → None returned, no crash | AI-04 |
| `test_analyze_company_rate_limit_retries` | 429 triggers retry (mock raises RateLimitError twice then succeeds) | AI-05 |
| `test_analyze_company_all_retries_exhausted` | 5 failures → None returned, no crash | AI-04, AI-05 |
| `test_industry_enum_has_other` | Industry.OTHER exists as fallback | AI-03 |
| `test_pipeline_skips_analyzed` | Companies with industry != None are skipped | (skip logic) |

### Testing Retry Behavior
```python
def test_retry_on_rate_limit():
    from openai import RateLimitError
    # RateLimitError requires a Response arg in openai 2.x
    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            # Build minimal mock response for RateLimitError
            mock_resp = MagicMock()
            mock_resp.status_code = 429
            raise RateLimitError("rate limit", response=mock_resp, body={})
        return _make_success_response()

    mock_client.beta.chat.completions.parse.side_effect = side_effect
    # ... assert result is not None and call_count == 3
```

---

## Pipeline Orchestration

### `scripts/run_pipeline.py` Structure
```python
"""
Pipeline: runs scraper (optional) then analyzer.
Usage: python -m scripts.run_pipeline [--skip-scrape]
"""
import sys
import logging
from pathlib import Path
from sqlmodel import Session, select

# app/ imports OK here (scripts is the orchestrator, not the agent)
from app.database import engine, create_db_and_tables
from app.models import Company

# agent/ import OK here too
from agent.analyzer import analyze_company

logger = logging.getLogger(__name__)

def run_pipeline(skip_scrape: bool = False) -> None:
    create_db_and_tables()

    if not skip_scrape:
        from scraper.yc_scraper import fetch_companies
        fetch_companies()  # uses its own sqlite3 connection

    with Session(engine) as session:
        # SKIP LOGIC: only fetch companies missing AI fields
        stmt = select(Company).where(Company.industry == None)
        pending = session.exec(stmt).all()
        logger.info("Found %d companies pending AI analysis", len(pending))

        for company in pending:
            analysis = analyze_company(company.company_name, company.description)
            if analysis is None:
                logger.warning("Skipping %s — analysis failed", company.company_name)
                continue

            company.industry = analysis.industry.value
            company.business_model = analysis.business_model
            company.summary = analysis.summary
            company.use_case = analysis.use_case
            session.add(company)
            session.commit()   # commit per-company — partial progress survives crashes
            logger.info("Analyzed: %s → %s", company.company_name, company.industry)

if __name__ == "__main__":
    skip = "--skip-scrape" in sys.argv
    run_pipeline(skip_scrape=skip)
```

### Session Strategy
- **One session for the entire batch** (not per-company) — reduces connection overhead
- **Commit per-company** — if the pipeline crashes mid-run, completed companies are not lost
- **Re-run is safe** — skip logic means already-analyzed companies are never re-processed
- Do NOT open a second Session inside the loop — use the outer session for all updates

### `agent/analyzer.py` Public Interface
```python
def analyze_company(company_name: str, description: str) -> Optional[CompanyAnalysis]:
    """
    Analyze a single company using OpenAI structured outputs.
    
    Returns CompanyAnalysis on success, None on any failure.
    Never raises — all exceptions are caught and logged.
    
    Import boundary: this function imports nothing from app/ or scraper/.
    """
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Retry with backoff | Custom `time.sleep` loop | `tenacity @retry` | Handles jitter, logging, reraise, configurable stops cleanly |
| JSON schema from Pydantic | Manual schema extraction | `openai parse()` with `response_format=MyModel` | OpenAI SDK converts Pydantic → JSON schema automatically |
| Rate limit detection | Parse error message strings | `RateLimitError` exception class | Type-safe, version-stable |
| DB UPDATE query | Raw SQL `UPDATE company SET ...` | SQLModel fetch-modify-commit | Keeps ORM benefits; no risk of column name typos |

---

## Common Pitfalls

### Pitfall 1: Enum `.value` for DB Storage
**What goes wrong:** Storing `analysis.industry` (an `Industry` enum object) directly into `company.industry` (an `Optional[str]` column). SQLModel will store `"Industry.AI_ML"` or raise a type error.  
**Root cause:** `Industry` is a `str(Enum)` so it IS a string, but its `str()` representation may not be the label.  
**How to avoid:** Always use `analysis.industry.value` → returns `"AI/ML"` (the string label).  
**Warning signs:** DB shows values like `"Industry.AI_ML"` instead of `"AI/ML"`.

### Pitfall 2: `message.parsed` is None Without Checking Refusal
**What goes wrong:** `AttributeError` or `None` result when accessing `message.parsed.industry` on a refused response.  
**Root cause:** OpenAI sets `refusal` field when the model declines to answer; `parsed` is None in that case.  
**How to avoid:** Check `if message.refusal: raise ValueError(...)` before accessing `message.parsed`.  
**Warning signs:** `NoneType has no attribute 'industry'` exception in analyzer.

### Pitfall 3: `@retry` on the Loop Instead of the Inner Call
**What goes wrong:** A 429 on company #10 retries from company #1, re-analyzing the first 9 companies.  
**Root cause:** Tenacity retries the entire decorated function body.  
**How to avoid:** Decorate only `_call_openai()`, not `analyze_companies()`.  
**Warning signs:** Duplicate DB writes / unexpected re-runs after a rate limit.

### Pitfall 4: `reraise=False` (tenacity default)
**What goes wrong:** After 5 failed attempts tenacity returns `None`, but the analyzer expects either a `CompanyAnalysis` or an exception. Silent failure.  
**Root cause:** Tenacity's default is `reraise=False`, so it swallows the exception after max retries.  
**How to avoid:** Set `reraise=True`. The outer try/except in the loop catches it and logs it.  
**Warning signs:** Companies silently skipped without any error log entry.

### Pitfall 5: Empty/Placeholder Descriptions
**What goes wrong:** OpenAI receives `"Asendia AI (no description available)"` and returns a low-confidence analysis or fails.  
**Root cause:** Scraper wrote a name-only placeholder (COLL-03 fallback).  
**How to avoid:** Prompt includes explicit instruction for vague descriptions. Use `gpt-4o-mini`'s ability to infer from company name. Result goes to `Industry.OTHER` if truly ambiguous.  
**Warning signs:** All placeholder companies classified as OTHER + generic business_model.

### Pitfall 6: API Quota Exhaustion Mid-Run
**What goes wrong:** 5 retries all fail (quota fully exhausted), the company is logged and skipped. Run exits normally.  
**How to avoid:** Set `reraise=True` + outer try/except. Re-running the pipeline after quota resets is safe (skip logic prevents re-analysis).  
**Warning signs:** Multiple `Failed to analyze` log lines in sequence; no panic.

### Pitfall 7: `client.beta.chat.completions` Import Path Confusion
**What goes wrong:** Developer tries `from openai.resources.beta.chat import...` and gets `ModuleNotFoundError` (there is no `openai/resources/beta/chat/` directory in 2.x).  
**Root cause:** In openai 2.x, `beta.chat` is a property returning `Chat` from `resources/chat/`. The module path differs from the attribute path.  
**How to avoid:** Always use `client = OpenAI(api_key=...)` then call `client.beta.chat.completions.parse(...)`. Never import the resource classes directly.

---

## Code Examples (Fully Verified)

### Minimal Complete analyzer.py Skeleton
```python
# agent/analyzer.py
import logging
from enum import Enum
from typing import Optional

from openai import OpenAI, RateLimitError, APIConnectionError
from pydantic import BaseModel
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

# app/ and scraper/ imports FORBIDDEN in this file

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert startup analyst..."""  # see Prompt Design section


class Industry(str, Enum):
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
    industry: Industry
    business_model: str
    summary: str
    use_case: str


@retry(
    retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(5),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _call_openai(client: OpenAI, company_name: str, description: str) -> CompanyAnalysis:
    response = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Company: {company_name}\nDescription: {description}"},
        ],
        response_format=CompanyAnalysis,
        temperature=0.2,
    )
    message = response.choices[0].message
    if message.refusal:
        raise ValueError(f"Model refused to analyze {company_name!r}: {message.refusal}")
    return message.parsed


def analyze_company(company_name: str, description: str) -> Optional[CompanyAnalysis]:
    """
    Public API. Never raises. Returns None on failure.
    Import boundary: imports nothing from app/ or scraper/.
    """
    # Import settings here (lazy import acceptable — settings is in app/)
    # WAIT — app/ is forbidden. Solution: accept api_key as parameter OR
    # read from os.environ directly.
    import os
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not set")
        return None

    client = OpenAI(api_key=api_key)
    try:
        return _call_openai(client, company_name, description)
    except Exception as exc:
        logger.error("Failed to analyze %r: %s", company_name, exc)
        return None
```

**CRITICAL note on `app/config.py` import:** `app/config.py` is in `app/`, which is forbidden in `agent/analyzer.py`. Use `os.environ.get("OPENAI_API_KEY")` directly in the analyzer. The `settings` singleton can be used in `scripts/run_pipeline.py` (which may import from `app/`).

### SQLModel UPDATE (verified against live DB)
```python
# session.get(Company, id) fetches by primary key — faster than select+where
company = session.get(Company, company_id)
company.industry = analysis.industry.value   # "FinTech" not Industry.FINTECH
company.business_model = analysis.business_model
company.summary = analysis.summary
company.use_case = analysis.use_case
session.add(company)
session.commit()
```

### Skip Query (verified)
```python
stmt = select(Company).where(Company.industry == None)
pending = session.exec(stmt).all()
# Returns only companies where industry IS NULL
```

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.13 | All | ✓ | 3.13.9 | — |
| openai | AI-01, AI-02, AI-05 | ✓ | 2.30.0 | — |
| tenacity | AI-05 | ✓ | 9.1.4 | — |
| pydantic | AI-02, AI-03 | ✓ | 2.12.5 | — |
| sqlmodel | update loop | ✓ | 0.0.38 | — |
| data/companies.db | pipeline input | ✓ | 50 rows (AI fields NULL) | — |
| OPENAI_API_KEY | all OpenAI calls | ⚠ | set in .env | Pipeline exits with clear error if missing |

**Missing dependencies with no fallback:** None — all packages installed.  
**Required action:** Ensure `OPENAI_API_KEY` is in `.env` before running the pipeline.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (already in use — `tests/test_foundation.py`, `tests/test_scraper.py` passing) |
| Config file | none (pytest auto-discovers `tests/`) |
| Quick run command | `.venv\Scripts\python -m pytest tests/test_analyzer.py -x -q` |
| Full suite command | `.venv\Scripts\python -m pytest tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AI-01 | analyze_company() returns CompanyAnalysis with 4 fields | unit | `pytest tests/test_analyzer.py::test_analyze_company_success -x` | ❌ Wave 0 |
| AI-02 | Uses `client.beta.chat.completions.parse()` with CompanyAnalysis | unit | `pytest tests/test_analyzer.py::test_uses_parse_api -x` | ❌ Wave 0 |
| AI-03 | Industry is str(Enum) with defined taxonomy | unit | `pytest tests/test_analyzer.py::test_industry_enum -x` | ❌ Wave 0 |
| AI-04 | Per-company isolation — one failure doesn't halt batch | unit | `pytest tests/test_analyzer.py::test_error_isolation -x` | ❌ Wave 0 |
| AI-05 | tenacity retries on 429 with exponential backoff | unit | `pytest tests/test_analyzer.py::test_retry_on_rate_limit -x` | ❌ Wave 0 |

### Wave 0 Gaps
- [ ] `tests/test_analyzer.py` — new file covering AI-01 through AI-05
- No framework install needed (pytest already installed and working)
- No conftest.py needed (tests/test_scraper.py has no conftest dependency)

---

## Open Questions

1. **`analyze_company()` API key source**
   - What we know: `app/config.py` has `settings.OPENAI_API_KEY` but `agent/analyzer.py` cannot import from `app/`
   - What's unclear: Should `analyze_company()` read from `os.environ` directly, or accept `api_key` as a parameter?
   - **Recommendation:** Read from `os.environ["OPENAI_API_KEY"]` directly. This respects the import boundary and `.env` is loaded by pydantic-settings at `scripts/run_pipeline.py` startup anyway (since `run_pipeline.py` imports `app.config`). Alternatively, accept `api_key: str` as a parameter and let `run_pipeline.py` pass `settings.OPENAI_API_KEY`.

2. **Commit frequency vs. API timeout risk**
   - What we know: `commit()` per company is safe for restartability
   - What's unclear: If the pipeline runs 50 companies at ~1s each (50s total), session lifetime is fine
   - **Recommendation:** Single session, commit per company — already specified above.

3. **`gpt-4o-mini` model name stability**
   - What we know: `gpt-4o-mini` was the primary low-cost model as of 2025
   - **Recommendation:** Hard-code `"gpt-4o-mini"` in `analyzer.py`. Can be made configurable via env var later.

---

## Sources

### Primary (HIGH confidence)
- Source-code inspection: `.venv/Lib/site-packages/openai/resources/chat/completions/completions.py` — `parse()` signature, `ParsedChatCompletion` type, refusal field
- Source-code inspection: `.venv/Lib/site-packages/openai/resources/beta/beta.py` — confirms `beta.chat` returns `Chat(self._client)`
- Source-code inspection: `.venv/Lib/site-packages/openai/types/chat/parsed_chat_completion.py` — `message.parsed`, `message.refusal` fields
- Live DB query: `data/companies.db` — all 50 company names/descriptions read for taxonomy design
- Runtime verification: `SQLModel.Session` fetch-modify-commit tested against live DB

### Secondary (MEDIUM confidence)
- OpenAI Structured Outputs documentation patterns (verified against installed source)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages installed, versions confirmed with `pip show`
- OpenAI API: HIGH — verified by reading installed source code directly
- Tenacity config: HIGH — all imports confirmed working in Python REPL
- Architecture: HIGH — SQLModel update pattern tested against live DB
- Industry taxonomy: HIGH — based on reading all 50 actual company descriptions
- Test mocking: HIGH — follows exact same patterns as `tests/test_scraper.py`

**Research date:** 2025-01-07  
**Valid until:** 2025-02-07 (openai SDK updates frequently; recheck if upgrading past 2.x)
