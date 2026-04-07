<!-- GSD:project-start source:PROJECT.md -->
## Project

**AI Company Research Agent**

An internal tool that automates company/startup research and analysis. It scrapes company data from Y Combinator's startup directory, runs each company through an OpenAI-powered agent to generate structured insights (industry, business model, summary, use case), stores everything in a SQLite database, and exposes the results through a FastAPI REST API.

**Core Value:** Any company in the database can be instantly retrieved with AI-generated insights — no manual research needed.

### Constraints

- **LLM:** OpenAI API — requires `OPENAI_API_KEY` environment variable
- **Scale:** ~10–50 companies (batch), not high-throughput
- **Stack:** Python-only backend — no Node.js or separate services
- **Scraping:** Y Combinator public directory only — no login-walled content
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Critical Pre-Research Finding: YC Site Architecture
## Recommended Stack
### Layer 1: Web Scraping
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `playwright` | `1.58.0` | Headless browser, JS execution | **Required** — YC uses Inertia.js/React; static HTTP gives empty HTML. Playwright renders the page, waits for the company grid to populate, then extracts DOM nodes. |
| `beautifulsoup4` | `4.14.3` | HTML parsing after Playwright renders | After Playwright gives you `page.content()`, BS4 navigates the DOM cleanly. Use `lxml` as the parser backend for speed. |
| `lxml` | `6.0.2` | BS4 parser backend | 3-5x faster than Python's built-in `html.parser`; handles malformed HTML better. |
- `requests` / `httpx` alone — confirmed dead end for YC; static response has no company data.
- `scrapy` — heavyweight framework designed for large crawls; massive overkill for 10-50 records. Adds ~30 dependencies for zero benefit here.
- `selenium` — functional but slower and heavier than Playwright; Playwright has better async support and a cleaner Python API.
### Layer 2: OpenAI Client
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `openai` | `2.30.0` | OpenAI API client | Latest v2 SDK. Use `client.chat.completions.create()` with `response_format={"type": "json_object"}` for structured analysis output. |
- `LangChain` — heavyweight, abstracts away the OpenAI API with layers that obscure what's happening, massive dependency tree (~50+ packages). For a single structured-output prompt, it's pure overhead.
- `LlamaIndex` — built for RAG and document indexing. Not relevant to this use case.
- `openai-agents` (OpenAI's new SDK) — designed for multi-step agentic loops. This system has one prompt per company; no loop needed.
- **Verdict: Raw `openai` client is correct.** This is a single-prompt-per-record pattern, not a multi-step agent.
### Layer 3: Database (SQLite ORM)
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `sqlmodel` | `0.0.38` | ORM + Pydantic model unification | Single class definition serves as both the DB table schema and the FastAPI response model. Eliminates the "define it twice" problem (one Pydantic model for API, one SQLAlchemy model for DB). |
- `sqlalchemy` (Core/ORM alone) — more verbose; requires separate Pydantic models for FastAPI responses. Use it under the hood (SQLModel wraps it), but don't use it directly.
- `raw sqlite3` — tempting for simplicity, but you lose Pydantic validation on insert and must manually map rows to dicts/objects for FastAPI responses. The boilerplate outweighs the "no dependency" benefit at this project size.
- `tortoise-orm` — async-only ORM. Async SQLite with FastAPI requires `aiosqlite` and complicates the project for no real throughput benefit at 50 records.
- `alembic` (migrations) — unnecessary for SQLite at this scale. Use `SQLModel.metadata.create_all(engine)` to create tables on first run.
### Layer 4: API Layer
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `fastapi` | `0.135.3` | REST API framework | Auto-generated OpenAPI docs, native Pydantic v2, async support. Standard for Python AI/data APIs in 2025/2026. |
| `uvicorn[standard]` | `0.44.0` | ASGI server | The standard FastAPI server. The `[standard]` extra includes `uvloop` (faster event loop on Linux/Mac) and `httptools` (faster HTTP parser). |
| `pydantic` | `2.12.5` | Data validation | FastAPI v0.100+ requires Pydantic v2. Do **not** use Pydantic v1 — it's unsupported by modern FastAPI. |
### Layer 5: Supporting Libraries
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `python-dotenv` | `1.2.2` | Load `OPENAI_API_KEY` from `.env` | Always — keeps secrets out of source code. Call `load_dotenv()` at startup. |
| `tenacity` | `9.1.4` | Retry logic for OpenAI calls | Wrap the OpenAI call with `@retry(wait=wait_exponential(...), stop=stop_after_attempt(3))` — prevents rate limit failures from killing the batch. |
| `httpx` | `0.28.1` | FastAPI test client | Required for `fastapi.testclient.TestClient` in pytest. Also doubles as the async HTTP client if you need it. |
### Layer 6: Testing
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `pytest` | `9.0.2` | Test runner | Standard Python test runner. v9 is the latest major; API is stable and backward compatible with v8.x patterns. |
| `pytest-asyncio` | `1.3.0` | Async test support | Required if any tests call `async` functions directly (e.g., testing Playwright coroutines). **v1.x breaking change**: must set `asyncio_mode = "auto"` in `pytest.ini` or `pyproject.toml`. |
| `httpx` | `0.28.1` | FastAPI `TestClient` | Used via `from fastapi.testclient import TestClient` — no separate install needed if httpx is already in deps. |
## Complete `requirements.txt`
# Scraping
# AI
# Database
# API
# Supporting
# Testing (dev only)
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
## Installation
# Create virtual environment
# or: source .venv/bin/activate  # Unix/Mac
# Install dependencies
# CRITICAL: install Playwright browser binary (one-time)
# Dev/test deps
## Sources
- PyPI live version queries (verified 2026-04-07 on this machine)
- YC companies page live HTTP analysis: confirmed Inertia.js + Algolia, zero static company data
- OpenAI SDK v2 changelog: verified `client.chat.completions` still stable in v2; `client.responses` is the new alternative
- FastAPI docs: `fastapi[standard]` bundle is the recommended install since v0.111+
- SQLModel GitHub: 0.0.38 is current release; actively maintained by FastAPI author
- pytest-asyncio v1.x: breaking change confirmed — `asyncio_mode = "auto"` required in config
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
