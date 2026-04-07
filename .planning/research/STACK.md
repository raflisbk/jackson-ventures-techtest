# Technology Stack

**Project:** AI Company Research Agent
**Researched:** 2026-04-07
**Source verification:** PyPI live version checks + YC site live HTTP analysis

---

## Critical Pre-Research Finding: YC Site Architecture

> **Before picking a scraping library, we verified the actual YC companies page.**
>
> Result: `ycombinator.com/companies` returns **zero company data in static HTML** (content length: ~18KB, all shell markup). The site uses **Inertia.js** (a Rails+React bridge) with **Algolia** powering the company directory. A bare `Invoke-WebRequest` or `httpx.get()` yields only the page skeleton.
>
> **Implication:** `requests` + `BeautifulSoup` alone **will not work**. JavaScript execution is required.

---

## Recommended Stack

### Layer 1: Web Scraping

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `playwright` | `1.58.0` | Headless browser, JS execution | **Required** — YC uses Inertia.js/React; static HTTP gives empty HTML. Playwright renders the page, waits for the company grid to populate, then extracts DOM nodes. |
| `beautifulsoup4` | `4.14.3` | HTML parsing after Playwright renders | After Playwright gives you `page.content()`, BS4 navigates the DOM cleanly. Use `lxml` as the parser backend for speed. |
| `lxml` | `6.0.2` | BS4 parser backend | 3-5x faster than Python's built-in `html.parser`; handles malformed HTML better. |

**Why not the alternatives:**
- `requests` / `httpx` alone — confirmed dead end for YC; static response has no company data.
- `scrapy` — heavyweight framework designed for large crawls; massive overkill for 10-50 records. Adds ~30 dependencies for zero benefit here.
- `selenium` — functional but slower and heavier than Playwright; Playwright has better async support and a cleaner Python API.

**Playwright setup note:** After `pip install playwright`, run `playwright install chromium` to download the browser binary. This is a one-time step that's easy to miss — document it in the README.

---

### Layer 2: OpenAI Client

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `openai` | `2.30.0` | OpenAI API client | Latest v2 SDK. Use `client.chat.completions.create()` with `response_format={"type": "json_object"}` for structured analysis output. |

**v1 → v2 migration note:** The SDK jumped from `1.109.x` to `2.0.0` — a significant restructuring. The new `client.responses.create()` API was introduced in v2, but `client.chat.completions.create()` is unchanged and still recommended for structured JSON tasks (more explicit control over the prompt + output format). Do **not** downgrade to v1; v2 is the current supported branch.

**Model:** `gpt-4o-mini` for batch analysis — well within JSON mode reliability threshold. Fall back to `gpt-4o` only if structured output quality is poor on ambiguous companies.

**Structured output pattern to use:**
```python
from openai import OpenAI

client = OpenAI()  # reads OPENAI_API_KEY from env automatically

response = client.chat.completions.create(
    model="gpt-4o-mini",
    response_format={"type": "json_object"},
    messages=[
        {"role": "system", "content": "You are a startup analyst. Always respond with valid JSON."},
        {"role": "user", "content": f"Analyze this company: {description}"}
    ]
)
result = json.loads(response.choices[0].message.content)
```

**Why not agent frameworks:**
- `LangChain` — heavyweight, abstracts away the OpenAI API with layers that obscure what's happening, massive dependency tree (~50+ packages). For a single structured-output prompt, it's pure overhead.
- `LlamaIndex` — built for RAG and document indexing. Not relevant to this use case.
- `openai-agents` (OpenAI's new SDK) — designed for multi-step agentic loops. This system has one prompt per company; no loop needed.
- **Verdict: Raw `openai` client is correct.** This is a single-prompt-per-record pattern, not a multi-step agent.

---

### Layer 3: Database (SQLite ORM)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `sqlmodel` | `0.0.38` | ORM + Pydantic model unification | Single class definition serves as both the DB table schema and the FastAPI response model. Eliminates the "define it twice" problem (one Pydantic model for API, one SQLAlchemy model for DB). |

**SQLModel caveat:** It is still pre-1.0 (`0.0.x`), but it has been stable in practice since 0.0.14+ and is actively maintained by the FastAPI author (Sebastián Ramírez). At 50 records and no complex queries, stability risk is negligible.

**Why not the alternatives:**
- `sqlalchemy` (Core/ORM alone) — more verbose; requires separate Pydantic models for FastAPI responses. Use it under the hood (SQLModel wraps it), but don't use it directly.
- `raw sqlite3` — tempting for simplicity, but you lose Pydantic validation on insert and must manually map rows to dicts/objects for FastAPI responses. The boilerplate outweighs the "no dependency" benefit at this project size.
- `tortoise-orm` — async-only ORM. Async SQLite with FastAPI requires `aiosqlite` and complicates the project for no real throughput benefit at 50 records.
- `alembic` (migrations) — unnecessary for SQLite at this scale. Use `SQLModel.metadata.create_all(engine)` to create tables on first run.

**SQLModel + FastAPI pattern:**
```python
from sqlmodel import SQLModel, Field, create_engine, Session

class Company(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    website: str
    description: str
    industry: str | None = None
    business_model: str | None = None
    summary: str | None = None
    use_case: str | None = None
```

---

### Layer 4: API Layer

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `fastapi` | `0.135.3` | REST API framework | Auto-generated OpenAPI docs, native Pydantic v2, async support. Standard for Python AI/data APIs in 2025/2026. |
| `uvicorn[standard]` | `0.44.0` | ASGI server | The standard FastAPI server. The `[standard]` extra includes `uvloop` (faster event loop on Linux/Mac) and `httptools` (faster HTTP parser). |
| `pydantic` | `2.12.5` | Data validation | FastAPI v0.100+ requires Pydantic v2. Do **not** use Pydantic v1 — it's unsupported by modern FastAPI. |

**Install as:**
```bash
pip install "fastapi[standard]"  # bundles fastapi + uvicorn[standard] + pydantic v2
```

**Key FastAPI patterns for this project:**
```python
from fastapi import FastAPI, HTTPException
from sqlmodel import Session, select

app = FastAPI()

@app.get("/companies", response_model=list[Company])
def get_companies():
    with Session(engine) as session:
        return session.exec(select(Company)).all()

@app.get("/companies/{company_id}", response_model=Company)
def get_company(company_id: int):
    with Session(engine) as session:
        company = session.get(Company, company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        return company
```

---

### Layer 5: Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `python-dotenv` | `1.2.2` | Load `OPENAI_API_KEY` from `.env` | Always — keeps secrets out of source code. Call `load_dotenv()` at startup. |
| `tenacity` | `9.1.4` | Retry logic for OpenAI calls | Wrap the OpenAI call with `@retry(wait=wait_exponential(...), stop=stop_after_attempt(3))` — prevents rate limit failures from killing the batch. |
| `httpx` | `0.28.1` | FastAPI test client | Required for `fastapi.testclient.TestClient` in pytest. Also doubles as the async HTTP client if you need it. |

---

### Layer 6: Testing

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `pytest` | `9.0.2` | Test runner | Standard Python test runner. v9 is the latest major; API is stable and backward compatible with v8.x patterns. |
| `pytest-asyncio` | `1.3.0` | Async test support | Required if any tests call `async` functions directly (e.g., testing Playwright coroutines). **v1.x breaking change**: must set `asyncio_mode = "auto"` in `pytest.ini` or `pyproject.toml`. |
| `httpx` | `0.28.1` | FastAPI `TestClient` | Used via `from fastapi.testclient import TestClient` — no separate install needed if httpx is already in deps. |

**pytest config (`pyproject.toml`):**
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"  # required for pytest-asyncio v1.x
```

---

## Complete `requirements.txt`

```txt
# Scraping
playwright==1.58.0
beautifulsoup4==4.14.3
lxml==6.0.2

# AI
openai==2.30.0

# Database
sqlmodel==0.0.38

# API
fastapi[standard]==0.135.3

# Supporting
python-dotenv==1.2.2
tenacity==9.1.4

# Testing (dev only)
pytest==9.0.2
pytest-asyncio==1.3.0
httpx==0.28.1
```

Or split into `requirements.txt` + `requirements-dev.txt` for cleaner separation.

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Scraping | `playwright` | `requests` + `httpx` | YC site is Inertia.js/React — static HTTP returns empty HTML shell |
| Scraping | `playwright` | `scrapy` | Overkill framework for 10-50 records; no JS support out of the box |
| Scraping | `playwright` | `selenium` | Slower, heavier, worse async API than Playwright |
| ORM | `sqlmodel` | `raw sqlite3` | sqlite3 forces manual row-to-dict mapping and separate Pydantic models |
| ORM | `sqlmodel` | `sqlalchemy` direct | More verbose, same problem as sqlite3 re: dual model definitions |
| ORM | `sqlmodel` | `tortoise-orm` | Async-only ORM adds complexity without benefit at 50 records |
| AI client | raw `openai` | `langchain` | 50+ transitive dependencies, 4 layers of abstraction for one prompt call |
| AI client | raw `openai` | `llama-index` | RAG/document indexing tool — wrong use case |

---

## Installation

```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# or: source .venv/bin/activate  # Unix/Mac

# Install dependencies
pip install playwright==1.58.0 beautifulsoup4==4.14.3 lxml==6.0.2
pip install openai==2.30.0
pip install sqlmodel==0.0.38
pip install "fastapi[standard]==0.135.3"
pip install python-dotenv==1.2.2 tenacity==9.1.4

# CRITICAL: install Playwright browser binary (one-time)
playwright install chromium

# Dev/test deps
pip install pytest==9.0.2 pytest-asyncio==1.3.0 httpx==0.28.1
```

---

## Sources

- PyPI live version queries (verified 2026-04-07 on this machine)
- YC companies page live HTTP analysis: confirmed Inertia.js + Algolia, zero static company data
- OpenAI SDK v2 changelog: verified `client.chat.completions` still stable in v2; `client.responses` is the new alternative
- FastAPI docs: `fastapi[standard]` bundle is the recommended install since v0.111+
- SQLModel GitHub: 0.0.38 is current release; actively maintained by FastAPI author
- pytest-asyncio v1.x: breaking change confirmed — `asyncio_mode = "auto"` required in config
