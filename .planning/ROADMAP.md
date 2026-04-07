# Roadmap: AI Company Research Agent

## Overview

**v1.0** — Four phases deliver the collect→analyze→store→expose pipeline. Schema and config land first so both the scraper and API share one source of truth. The YC JSON API scraper ships second to validate real data shape before any OpenAI costs are incurred. The AI analysis pipeline and orchestration script follow, building on the confirmed data shape. The read-only FastAPI layer closes the loop — it can only be meaningfully tested against real data, so it comes last.

**v1.1** — Five phases extend the platform: AI response caching eliminates redundant OpenAI calls; filtering/search makes the REST API useful for real queries; the MCP server exposes company data as callable tools for AI agent clients; the static frontend lets humans browse and filter results in a browser; and CI/CD automation brings agentic code review to every pull request.

## Phases

- [x] **Phase 1: Foundation** - Schema, config, SQLite engine with threading fix
- [ ] **Phase 2: Data Collection** - YC JSON API scraper with idempotent upserts
- [ ] **Phase 3: AI Analysis Pipeline** - OpenAI Structured Outputs + run_pipeline.py orchestrator
- [ ] **Phase 4: REST API** - FastAPI endpoints exposing stored company insights

### v1.1 Phases

- [ ] **Phase 5: AI Caching** - SHA-256 description hash column + cache-aware pipeline skip logic
- [ ] **Phase 6: Filtering & Search** - `?industry=` and `?q=` query params on `GET /companies`
- [ ] **Phase 7: MCP Server** - Standalone FastMCP stdio server exposing three company tools
- [ ] **Phase 8: Static Frontend** - HTML/JS company card browser served at `/ui`
- [ ] **Phase 9: CI/CD Pipeline** - GitHub Actions workflow with agentic OpenAI PR code review

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
**Plans**: 2 plans

Plans:
- [x] phase-1-01-PLAN.md — Project scaffold + core modules (config.py, models.py, database.py)
- [x] phase-1-02-PLAN.md — Test suite validating all 4 success criteria

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

**Execution Order:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 0/? | Not started | - |
| 2. Data Collection | 0/? | Not started | - |
| 3. AI Analysis Pipeline | 0/? | Not started | - |
| 4. REST API | 0/? | Not started | - |
| 5. AI Caching | 0/? | Not started | - |
| 6. Filtering & Search | 0/? | Not started | - |
| 7. MCP Server | 0/? | Not started | - |
| 8. Static Frontend | 0/? | Not started | - |
| 9. CI/CD Pipeline | 0/? | Not started | - |

---

## v1.1 Phase Details

### Phase 5: AI Caching
**Goal**: The analysis pipeline never calls OpenAI for a company it has already analyzed — cached results are served instantly via a SHA-256 description hash stored on each record
**Depends on**: Phase 4
**Requirements**: CACHE-01, CACHE-02, CACHE-03
**Success Criteria** (what must be TRUE):
  1. Running `python scripts/run_pipeline.py` twice produces no duplicate OpenAI calls — second run logs `[CACHE HIT]` for every already-analyzed company
  2. Each `Company` row in the database has a populated `description_hash` column (64-char hex string) after the pipeline runs
  3. Running `python scripts/migrate_add_hash.py` twice raises no error on the second run (idempotent `ALTER TABLE` with `IF NOT EXISTS` guard)
  4. A company record with a matching hash but `industry IS NULL` (partial write) is NOT treated as a cache hit — pipeline re-analyzes it
**Plans**: TBD
**Technical notes**:
  - **HASH-1 (migration required):** `SQLModel.metadata.create_all()` silently skips new columns on existing tables — use `ALTER TABLE company ADD COLUMN description_hash TEXT` in `scripts/migrate_add_hash.py` wrapped in `try/except OperationalError` to handle "duplicate column" idempotently
  - **HASH-2 (two-condition cache check):** Cache hit = `description_hash == computed_hash AND industry IS NOT NULL` — single-condition check on hash alone misses partial-write records
  - `.strip()` the description before hashing — trailing whitespace causes hash drift between runs; `compute_description_hash(desc)` returns `None` for empty/None input
  - New files: `scripts/migrate_add_hash.py`; modified: `app/models.py` (add `description_hash` field), `agent/analyzer.py` (cache check + hash write)

---

### Phase 6: Filtering & Search
**Goal**: `GET /companies` accepts `?industry=` and `?q=` query params that filter results server-side — users and AI agents can retrieve targeted subsets without fetching the full dataset
**Depends on**: Phase 5
**Requirements**: FILTER-01, FILTER-02, FILTER-03, FILTER-04
**Success Criteria** (what must be TRUE):
  1. `GET /companies?industry=fintech` returns only FinTech companies (case-insensitive — `fintech`, `FinTech`, `FINTECH` all match)
  2. `GET /companies?q=payments` returns companies whose name or description contains "payments" (case-insensitive substring match)
  3. `GET /companies` (no params) and `GET /companies?industry=` (empty param) both return all companies unchanged
  4. `GET /companies?q=100%25` (URL-encoded `%`) returns results without a SQL error — wildcard characters are escaped before use in LIKE clauses
**Plans**: TBD
**Technical notes**:
  - **FILTER-1 (empty string ≠ None):** FastAPI passes `?industry=` as `""` not `None` — guard with `if industry` (truthy check) not `if industry is not None`
  - **FILTER-2 (wildcard injection):** Escape `%` and `_` in `?q=` values before building LIKE clause — replace `%` → `\%`, `_` → `\_`, then add `ESCAPE '\'` to the SQL predicate
  - Use `LOWER()` for case-insensitive industry match: `func.lower(Company.industry) == industry.lower()` — SQLite's LIKE is case-insensitive for ASCII but `==` is not
  - Modified file: `app/routers/companies.py` (add `industry: Optional[str] = None` and `q: Optional[str] = None` query params, build conditional WHERE clauses)

---

### Phase 7: MCP Server
**Goal**: AI agent clients (Claude Desktop, Cursor, etc.) can call three company tools over stdio MCP — `search_companies`, `get_company`, `list_industries` — reading live data from the shared SQLite database
**Depends on**: Phase 4
**Requirements**: MCP-01, MCP-02, MCP-03
**Success Criteria** (what must be TRUE):
  1. `python mcp_server/server.py` starts without errors and is listed as a valid MCP server when registered in a Claude Desktop config
  2. Calling `list_industries` via an MCP client returns a JSON array of distinct industry values from the database
  3. Calling `search_companies` with `industry="FinTech"` returns only FinTech company records
  4. Running the MCP server concurrently with `uvicorn app.main:app` produces no `SQLITE_BUSY` errors — WAL journal mode allows concurrent reads
**Plans**: TBD
**Technical notes**:
  - **MCP-1 (stdout corruption):** Any `print()` statement (or logging to stdout) in `mcp_server/server.py` or its imports corrupts the JSON-RPC stdio stream — redirect ALL logging to `sys.stderr` before any imports: `logging.basicConfig(stream=sys.stderr, level=logging.WARNING)`; never use `print()` in the MCP process
  - **MCP-2 (WAL mode required):** SQLite default journal mode causes `SQLITE_BUSY` when MCP server and FastAPI share `companies.db` — enable WAL on the MCP engine: `engine.execute("PRAGMA journal_mode=WAL")` immediately after `create_engine()`; also enable in `app/database.py` for the FastAPI side
  - Use `fastmcp==3.2.0` (PrefectHQ/fastmcp standalone) — NOT `mcp==1.27.0`; add to `requirements.txt`
  - New files: `mcp_server/__init__.py`, `mcp_server/server.py`; modified: `app/database.py` (WAL PRAGMA), `requirements.txt`

---

### Phase 8: Static Frontend
**Goal**: Users can browse all company cards and filter by industry in a browser at `/ui` — served directly by the FastAPI process with no separate web server or build step
**Depends on**: Phase 6
**Requirements**: UI-01, UI-02, UI-03
**Success Criteria** (what must be TRUE):
  1. `GET /ui` (or `/ui/index.html`) returns an HTML page showing company cards with name, industry badge, business model, summary, and website link
  2. Selecting an industry from the filter dropdown narrows visible cards client-side without a page reload
  3. Clearing the filter restores all cards — the page fetches from `GET /companies` (and `GET /companies?industry=X` when filtering)
**Plans**: TBD
**UI hint**: yes
**Technical notes**:
  - **STATIC-1 (mount order matters):** Mount `StaticFiles` at `/ui` — NOT `/` (would shadow all API routes and return 404 on `GET /companies`); mount AFTER all `app.include_router()` calls in `app/main.py`
  - Use Tailwind CSS via CDN (`<script src="https://cdn.tailwindcss.com">`) — zero build step, no `npm`, no `node_modules`
  - Use vanilla JS (`fetch` + DOM manipulation) — no framework needed for 50 cards; 80-line `app.js` is sufficient
  - New files: `frontend/index.html`, `frontend/app.js`, `frontend/style.css`; modified: `app/main.py` (add `StaticFiles` mount at `/ui`)

---

### Phase 9: CI/CD Pipeline
**Goal**: Every pull request automatically receives an AI-generated code review comment — the GitHub Actions workflow fetches the PR diff, sends it to OpenAI, and posts analysis as a PR comment using repo secrets
**Depends on**: Phase 8
**Requirements**: CICD-01, CICD-02, CICD-03
**Success Criteria** (what must be TRUE):
  1. Opening a pull request on the repo triggers the `code-review` workflow — visible in the GitHub Actions tab within 60 seconds
  2. The workflow posts an OpenAI-generated code review as a comment on the PR (visible in the PR Conversation tab)
  3. Draft PRs do NOT trigger the workflow — the `if: github.event.pull_request.draft == false` guard is in place
**Plans**: TBD
**Technical notes**:
  - **CI-permissions:** Workflow YAML must declare `permissions: pull-requests: write` at the job level — without it, `GITHUB_TOKEN` cannot post PR comments (silent 403)
  - **CI-draft (skip drafts):** Add `if: github.event.pull_request.draft == false` job condition — draft PRs should not consume OpenAI API credits
  - **CI-fork (secrets unavailable):** `OPENAI_API_KEY` is unavailable for PRs from forks (GitHub security model) — add guard: `if: github.event.pull_request.head.repo.full_name == github.repository`; document this limitation in the workflow file
  - `scripts/ai_code_review.py` fetches diff via GitHub REST API (`GITHUB_TOKEN`), sends to OpenAI (`OPENAI_API_KEY`), posts comment via `POST /repos/{owner}/{repo}/issues/{pr_number}/comments`
  - New files: `.github/workflows/code-review.yml`, `scripts/ai_code_review.py`
