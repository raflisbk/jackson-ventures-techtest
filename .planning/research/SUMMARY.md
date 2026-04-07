# Project Research Summary

**Project:** AI Company Research Agent
**Domain:** AI-powered data pipeline + REST API (Python / FastAPI / SQLite)
**Researched:** 2026-04-07
**Confidence:** HIGH

---

## Executive Summary

This is a collect→analyze→store→expose pipeline: scrape YC startup data, run each company through OpenAI for structured insights, persist to SQLite, and serve via FastAPI. The pattern is well-established in the Python ecosystem and all components have clear, opinionated best practices. The full working system is achievable in a single focused build session — total complexity is low.

The single most important research finding is that **Y Combinator exposes an undocumented but stable public REST API** at `api.ycombinator.com/v0.1/companies` that returns clean JSON (25 companies/page, ~234 pages). This completely eliminates the need for Playwright or any headless browser — the `requests` library suffices. This was discovered after the initial STACK.md recommendation of Playwright (which was based on correctly observing that the HTML page is JS-rendered with zero data). Use `requests` + the JSON API directly. The STACK.md Playwright recommendation is superseded by the PITFALLS.md finding.

The key risks are all avoidable with known patterns: SQLite threading in FastAPI requires two specific fixes (`check_same_thread=False` + per-request session via `Depends`); OpenAI JSON mode is unreliable without schema enforcement (use `beta.chat.completions.parse` with a Pydantic model); and LLM taxonomy drift must be addressed via a closed vocabulary in the prompt or a Pydantic enum. All three are well-understood and have 10-line fixes.

---

## Key Findings

### Recommended Stack

The stack is idiomatic Python for 2025/2026 AI data tooling. The only non-obvious choice is SQLModel (which unifies the SQLAlchemy ORM model and Pydantic response schema into a single class) — this eliminates the common "define it twice" boilerplate. All version pins are live-verified against PyPI.

**⚠️ CORRECTION FROM PITFALLS.md:** STACK.md recommends `playwright==1.58.0` as required for YC scraping. **This is wrong.** The YC JSON API (`api.ycombinator.com/v0.1/companies`) makes Playwright unnecessary. Remove Playwright from requirements entirely.

**Core technologies:**
- `requests` (stdlib / no pin needed): Fetch pages from YC JSON API — direct HTTP, no browser required
- `openai==2.30.0`: AI analysis — use `client.beta.chat.completions.parse()` with Pydantic model (Structured Outputs), NOT `json_object` mode
- `sqlmodel==0.0.38`: ORM + schema unification — single `Company` class serves DB table and API response model
- `fastapi[standard]==0.135.3`: REST API — auto-docs at `/docs`, native Pydantic v2, async support
- `uvicorn[standard]==0.44.0`: ASGI server bundled with `fastapi[standard]`
- `pydantic==2.12.5`: Data validation — write v2-native patterns only (`ConfigDict`, `field_validator`, `.model_dump()`)
- `pydantic-settings`: Typed config from `.env` — cleaner than `os.getenv()` scattered everywhere
- `tenacity==9.1.4`: Retry logic for OpenAI calls — exponential backoff on `RateLimitError`, `APIConnectionError`, `APITimeoutError`
- `python-dotenv==1.2.2`: Load `.env` at startup

**Do NOT use:**
- `playwright` / `beautifulsoup4` / `lxml` — YC JSON API makes these unnecessary
- `langchain` / `llama-index` / `openai-agents` — single prompt per company; no agent loop needed
- `alembic` — `SQLModel.metadata.create_all(engine)` is sufficient at this scale
- `tortoise-orm` / async SQLAlchemy — sync ORM is correct for this project

---

### Expected Features

**Must have (table stakes — v1):**
- Scrape ≥10 companies from YC JSON API: name, website, description, batch, oneLiner
- Idempotent re-runs: skip already-collected companies (check by URL/slug before insert)
- Per-company AI analysis: industry, business model, 1-sentence summary, potential use case
- Structured JSON output enforced via `CompanyAnalysis` Pydantic model + `beta.chat.completions.parse`
- Per-company error isolation: `try/except` in loop, log and continue — one failure must not abort the batch
- Retry on OpenAI 429 / transient errors via `tenacity`
- `GET /companies` — all records with AI insights
- `GET /companies/{id}` — single record, 404 on missing
- AI prompt documented with rationale for design choices
- `created_at` / `analyzed_at` timestamps on each record

**Should have (v1 extension, low effort):**
- `longDescription` fallback chain: `longDescription` → `oneLiner` → company name (avoids hallucination on ~8% of empty records)
- Structured logging summary: print "N scraped, N analyzed, N failed" at end of run
- Few-shot examples in system prompt (2-3 improves consistency markedly)
- Closed vocabulary for `industry` field (enum in Pydantic or explicit list in prompt)
- Output validation: Pydantic validates LLM response before DB insert
- `.env.example` with placeholder keys (self-documenting setup)

**Defer (v2+):**
- Filtering/search on API (`?industry=fintech`, `?q=payments`)
- Model fallback (gpt-4o-mini → gpt-4o on parse failure)
- `--force-reanalyze` / `--limit N` CLI flags
- Full-text search (SQLite FTS5)
- Exponential backoff with jitter (tenacity handles this already)

**Anti-features to explicitly avoid:**
- Real-time scraping on API request (latency: 5-30s; blocks thread)
- Authentication on the API (internal tool, out of scope)
- Pagination (< 100 records)
- Async LLM calls (sequential loop is fast enough for 50 companies)
- Docker/containerization (overkill for internal script)
- Frontend/UI (Swagger UI at `/docs` is sufficient)

---

### Architecture Approach

Two completely separate entrypoints sharing only the SQLite file. The FastAPI server never triggers scraping; the scraper never starts a web server. This separation is load-bearing — violating it (e.g., triggering scraping from an API endpoint) creates unpredictable latency and threading issues.

**Major components:**
1. `scraper/yc_scraper.py` — fetches from YC JSON API via `requests`, follows `nextPage` cursor pagination, returns `list[dict]`; imports nothing from `app/` or `agent/`
2. `agent/analyzer.py` — constructs OpenAI prompt, calls `client.beta.chat.completions.parse()` with `CompanyAnalysis` Pydantic model, returns typed result; imports nothing from `app/` or `scraper/`
3. `scripts/run_pipeline.py` — top-level orchestrator: calls scraper → calls analyzer per company → writes merged row to DB; this is the only file that imports from all three domains
4. `app/database.py` — engine with `check_same_thread=False`, `SessionLocal` factory, `get_db()` Depends function
5. `app/models.py` — SQLModel `Company` table (scraped fields + AI-generated fields + timestamps)
6. `app/routers/companies.py` — route handlers, reads from DB via `Depends(get_db)`, returns `CompanyResponse` schema
7. `app/main.py` — `FastAPI(lifespan=lifespan)` app instance, router registration, DB table creation on startup
8. `config.py` — `pydantic-settings` `Settings` class, loaded once, imported everywhere

**Data flow:**
```
Pipeline: YC API → scraper → analyzer (OpenAI) → SQLite companies.db
API:      HTTP client → FastAPI routes → SQLite companies.db (read-only)
```

---

### Critical Pitfalls

1. **Scraping YC HTML instead of using the JSON API** — `ycombinator.com/companies` returns an 18KB JS shell with zero company data (live-verified). Use `api.ycombinator.com/v0.1/companies?page=1` instead. Returns structured JSON: 25 companies/page, `nextPage` cursor for pagination. No Playwright, no BeautifulSoup.

2. **SQLite `check_same_thread` crash in FastAPI** — SQLite's Python binding raises `ProgrammingError` the moment a second concurrent request arrives. Two fixes required together: `create_engine(..., connect_args={"check_same_thread": False})` AND per-request session via `def get_db(): db = SessionLocal(); try: yield db; finally: db.close()` with `Depends(get_db)` in route signatures.

3. **OpenAI JSON mode returns inconsistent field names/values** — `response_format={"type": "json_object"}` guarantees valid JSON syntax but NOT schema adherence. The model will vary `"industry"` vs `"Industry"` vs `"sector"` across calls, omit fields, or use inconsistent vocabularies. Use `client.beta.chat.completions.parse(response_format=CompanyAnalysis)` with a Pydantic model instead — enforces schema at the API level.

4. **LLM taxonomy drift on `industry` field** — even with Structured Outputs, free-text `industry` values across 50 companies produce semantically overlapping labels (`"B2B SaaS"`, `"Enterprise Software"`, `"SaaS"`) that make grouping unreliable. Define a closed vocabulary in the system prompt or use `class Industry(str, Enum)` in the Pydantic model.

5. **SQLite DB file path resolves to different directories** — `"sqlite:///companies.db"` creates the file relative to CWD at startup. Running the scraper from `scripts/` and the API from the project root means two different DB files, zero shared data. Fix: `BASE_DIR = Path(__file__).resolve().parent; DATABASE_URL = f"sqlite:///{BASE_DIR}/../companies.db"` (or a shared `config.py` value).

**Additional pitfalls to avoid:**
- `@app.on_event("startup")` is deprecated in FastAPI 0.135.x — use `lifespan` context manager
- Pydantic v1 patterns (`orm_mode`, `@validator`, `.dict()`) emit warnings under v2.12.5 — write v2-native from day one
- Empty `longDescription` on ~8% of YC companies — implement fallback chain before calling OpenAI
- No retry logic on OpenAI calls — use `tenacity` with `retry_if_exception_type((RateLimitError, APIConnectionError, APITimeoutError))`
- Missing `.env` validation — check `OPENAI_API_KEY` at script start, before any scraping work begins

---

## Implications for Roadmap

Based on the research, a 4-phase structure with clear dependency ordering:

### Phase 1: Foundation — Schema + Config + DB Setup
**Rationale:** Every other component depends on the DB schema and config. Build this first so scraper and API both import from the same source of truth.
**Delivers:** Working SQLite DB, `Company` SQLModel table, engine with threading fix, `config.py` with `pydantic-settings`, `.env.example`
**Key patterns:** `check_same_thread=False`, `Path(__file__).resolve()` for DB path, `SQLModel.metadata.create_all(engine)`
**Avoids:** Pitfall #5 (relative path), Pitfall #2 (threading setup done correctly from the start)

### Phase 2: Scraper — YC JSON API Fetch
**Rationale:** Can be built and tested independently once schema exists. Validates data shape before AI costs are incurred.
**Delivers:** `scraper/yc_scraper.py` that calls `api.ycombinator.com/v0.1/companies`, follows `nextPage` cursor, normalizes to `list[dict]`, handles empty `longDescription` with fallback chain
**Key patterns:** `requests` + pagination cursor, 0.5s polite delay, no Playwright
**Avoids:** Pitfall #1 (JSON API not HTML), Pitfall #13/#14 (rate limiting, cursor pagination)
**Research flag:** Standard pattern, no phase research needed

### Phase 3: AI Analyzer + Pipeline Script
**Rationale:** Depends on scraper output shape (Phase 2) and DB schema (Phase 1). This is the core "agentic" capability.
**Delivers:** `agent/analyzer.py` with `CompanyAnalysis` Pydantic model, Structured Outputs via `beta.chat.completions.parse`, tenacity retry decorator, closed-vocabulary `industry` enum; `scripts/run_pipeline.py` orchestrator with per-company error isolation and progress logging
**Key patterns:** `client.beta.chat.completions.parse(response_format=CompanyAnalysis)`, `@retry(retry=retry_if_exception_type(...), wait=wait_exponential(...))`, commit-per-company (not batch commit)
**Avoids:** Pitfall #3 (JSON mode), Pitfall #4 (taxonomy drift), Pitfall #8 (no retry)
**Research flag:** Prompt engineering for structured outputs is well-documented; no phase research needed

### Phase 4: FastAPI REST API
**Rationale:** Read-only API — can only be built after DB has data. Simplest phase.
**Delivers:** `app/main.py` with `lifespan` context manager, `app/routers/companies.py` with `GET /companies` + `GET /companies/{id}`, `CompanyResponse` Pydantic v2 schema, auto-docs at `/docs`
**Key patterns:** `def` (not `async def`) for sync routes, `Depends(get_db)` per-request sessions, `model_config = ConfigDict(from_attributes=True)`, `HTTPException(status_code=404)`
**Avoids:** Pitfall #2/#3 (session management), Pitfall #6 (`on_event` deprecation), Pitfall #4 (Pydantic v2 patterns)
**Research flag:** Fully standard FastAPI CRUD; no phase research needed

### Phase Ordering Rationale
- **Schema first** because both pipeline and API import from it — avoids rework if shape changes
- **Scraper before analyzer** because you need real data shape to design the AI prompt effectively (know which fields are often empty, how descriptions read)
- **Analyzer + pipeline together** because they're tightly coupled (pipeline orchestrates analyzer) and share no code with the API
- **API last** because it's read-only and can only be meaningfully tested against real data

### Research Flags
- **No phases require `/gsd-research-phase`** — all patterns are well-documented, live-verified, and high-confidence
- The one non-obvious area is prompt engineering for the AI analyzer (few-shot examples, vocabulary constraints), but this is implementation detail, not architecture risk

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions live-verified on PyPI 2026-04-07; YC API confirmed live with JSON response |
| Features | HIGH | Core patterns drawn from established startup intelligence products; YC-specific scraping verified live |
| Architecture | HIGH | Standard FastAPI + SQLite patterns, well-documented; component boundaries clearly established |
| Pitfalls | HIGH | All critical pitfalls live-verified with exact error messages captured; not theoretical |

**Overall confidence: HIGH**

### Gaps to Address

- **YC API stability:** The API at `api.ycombinator.com/v0.1/companies` is undocumented. It's been stable in practice but could change without notice. Mitigation: store `raw_yc_data` as JSON blob alongside normalized fields so re-parsing is possible without re-scraping.
- **OpenAI model pricing:** Cost estimate of ~$0.007 for 50 companies (gpt-4o-mini) is calculated from published pricing and subject to change. Not a build risk.
- **gpt-4o-mini rate limits:** Tier 1 is 500 RPM / 200k TPM — confirmed from training data but should be verified at `platform.openai.com/docs/guides/rate-limits` if running large batches.

---

## Sources

### Primary (HIGH confidence — live-verified)
- YC HTML page live HTTP analysis: confirmed Inertia.js/React shell, zero company data in first 5KB
- YC JSON API live request: `api.ycombinator.com/v0.1/companies?page=1` → 200 OK, 25 companies, `totalPages: 234`
- PyPI live version queries: all package versions verified 2026-04-07
- SQLite `check_same_thread` threading test: `ProgrammingError` exact message captured
- SQLAlchemy shared session concurrency test: 3/5 threads failed with `InvalidRequestError`
- Pydantic v2.12.5 `orm_mode` deprecation: exact `UserWarning` captured
- FastAPI v0.135.2 `@app.on_event` deprecation: exact `DeprecationWarning` captured
- OpenAI SDK 2.30.0: `beta.chat.completions.parse` availability confirmed

### Secondary (MEDIUM confidence)
- OpenAI gpt-4o-mini Tier 1 rate limits: 500 RPM, 200k TPM (training data; verify at platform.openai.com)
- YC API pagination: `nextPage`/`prevPage` cursor pattern (live-verified on page 2)
- ~8% of YC companies have empty `longDescription`: 2/25 on page 1 (statistically small sample)

---

*Research completed: 2026-04-07*
*Ready for roadmap: yes*
