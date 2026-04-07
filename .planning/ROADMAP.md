# Roadmap: AI Company Research Agent

## Overview

Four phases deliver the collect→analyze→store→expose pipeline. Schema and config land first so both the scraper and API share one source of truth. The YC JSON API scraper ships second to validate real data shape before any OpenAI costs are incurred. The AI analysis pipeline and orchestration script follow, building on the confirmed data shape. The read-only FastAPI layer closes the loop — it can only be meaningfully tested against real data, so it comes last.

## Phases

- [ ] **Phase 1: Foundation** - Schema, config, SQLite engine with threading fix
- [ ] **Phase 2: Data Collection** - YC JSON API scraper with idempotent upserts
- [ ] **Phase 3: AI Analysis Pipeline** - OpenAI Structured Outputs + run_pipeline.py orchestrator
- [ ] **Phase 4: REST API** - FastAPI endpoints exposing stored company insights

## Phase Details

### Phase 1: Foundation
**Goal**: Project skeleton exists with correct DB schema, config loading, and SQLite threading fix — every downstream component can import from a single shared source of truth
**Depends on**: Nothing (first phase)
**Requirements**: CFG-01, CFG-02, DB-01, DB-02, DB-03, DB-04
**Success Criteria** (what must be TRUE):
  1. `Company` SQLModel table is created automatically in `data/companies.db` on first import — no manual migration step
  2. App startup (or pipeline run) fails immediately with a clear error message if `OPENAI_API_KEY` is missing from the environment
  3. Database file path resolves consistently regardless of which directory the process starts from (absolute path via `Path(__file__).resolve()`)
  4. Importing `app.database` in a multi-threaded context does not raise `ProgrammingError` (`check_same_thread=False` is set and `get_db()` yields per-request sessions)
**Plans**: TBD
**Technical notes**: `check_same_thread=False` + `Depends(get_db)` both required. SQLModel unifies DB table + Pydantic schema into single `Company` class. `pydantic-settings` loads `OPENAI_API_KEY` and `DATABASE_URL` with fail-fast validation.

---

### Phase 2: Data Collection
**Goal**: A script fetches real company data from the YC JSON API and stores it in SQLite — ≥10 clean records ready for AI analysis
**Depends on**: Phase 1
**Requirements**: COLL-01, COLL-02, COLL-03, COLL-04
**Success Criteria** (what must be TRUE):
  1. Running `scraper/yc_scraper.py` populates the database with ≥10 company records, each containing name, website URL, and description
  2. Each stored record has a non-empty description — companies with missing `longDescription` use the fallback chain (`shortDescription` → `oneLiner` → name-only placeholder)
  3. Running the scraper twice produces no duplicate records (upsert by company name prevents re-insertion)
**Plans**: TBD
**Technical notes**: Fetch from `api.ycombinator.com/v0.1/companies` (public JSON, no auth). Follow `nextPage` cursor. Use `requests` — no Playwright needed. Add 0.5s polite delay between pages. Do NOT scrape `ycombinator.com/companies` HTML (JS shell, zero data).

---

### Phase 3: AI Analysis Pipeline
**Goal**: Every collected company has AI-generated insights (industry, business model, summary, use case) stored in SQLite — produced by a structured, fault-tolerant OpenAI pipeline
**Depends on**: Phase 2
**Requirements**: AI-01, AI-02, AI-03, AI-04, AI-05
**Success Criteria** (what must be TRUE):
  1. Running `python scripts/run_pipeline.py` produces records with `industry`, `business_model`, `summary`, and `use_case` fields populated for every company in the DB
  2. The `industry` field always contains one of the predefined enum values — never free-form or inconsistent text
  3. A single company failing OpenAI analysis is logged and skipped; the remaining batch completes without interruption
  4. OpenAI 429 rate-limit errors trigger automatic retries with exponential backoff — the pipeline does not crash on transient API errors
**Plans**: TBD
**Technical notes**: Use `client.beta.chat.completions.parse(response_format=CompanyAnalysis)` — NOT `json_object` mode (schema not enforced). `class Industry(str, Enum)` in Pydantic model prevents taxonomy drift. `tenacity` `@retry` with `retry_if_exception_type((RateLimitError, APIConnectionError))`. Commit per-company (not batch) to survive partial runs. `run_pipeline.py` is the only file that imports from all three domains.

---

### Phase 4: REST API
**Goal**: Any company in the database can be instantly retrieved with AI-generated insights via a clean REST API with auto-generated documentation
**Depends on**: Phase 3
**Requirements**: API-01, API-02, API-03, API-04
**Success Criteria** (what must be TRUE):
  1. `GET /companies` returns a JSON array of all companies including all AI-generated fields (`industry`, `business_model`, `summary`, `use_case`)
  2. `GET /companies/{id}` returns full company details for a valid ID; requesting a non-existent ID returns HTTP 404
  3. FastAPI auto-docs load at `/docs` with correct Pydantic v2 response schemas and no deprecation warnings in the server logs
**Plans**: TBD
**Technical notes**: `FastAPI(lifespan=lifespan)` — not deprecated `@app.on_event`. `model_config = ConfigDict(from_attributes=True)` — not `orm_mode`. Use `def` (not `async def`) for sync routes. `Depends(get_db)` per-request session in all route signatures.

---

## Progress

**Execution Order:** 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 0/? | Not started | - |
| 2. Data Collection | 0/? | Not started | - |
| 3. AI Analysis Pipeline | 0/? | Not started | - |
| 4. REST API | 0/? | Not started | - |
