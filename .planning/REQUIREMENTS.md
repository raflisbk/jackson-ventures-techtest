# Requirements: AI Company Research Agent

**Defined:** 2026-04-07
**Core Value:** Any company in the database can be instantly retrieved with AI-generated insights — no manual research needed.

## v1 Requirements

### Data Collection

- [ ] **COLL-01**: System fetches at least 10 company records from the YC public JSON API (`api.ycombinator.com/v0.1/companies`)
- [ ] **COLL-02**: Each collected company record contains: company name, website URL (if available), and description
- [ ] **COLL-03**: Scraper handles companies with missing or empty descriptions via a fallback chain (shortDescription → longDescription → name-only placeholder)
- [ ] **COLL-04**: Scraper is idempotent — re-running does not create duplicate records (upsert by company name)

### AI Analysis

- [ ] **AI-01**: AI agent analyzes each company and produces: industry, business model, 1-sentence summary, potential use case
- [ ] **AI-02**: Analysis uses OpenAI Structured Outputs (`client.beta.chat.completions.parse`) with a Pydantic model to guarantee consistent field types and values
- [ ] **AI-03**: Industry field uses a fixed enum of valid values (e.g., FinTech, HealthTech, Developer Tools, SaaS, etc.) to prevent free-form drift
- [ ] **AI-04**: Per-company error isolation: one failed OpenAI call does not halt the rest of the batch
- [ ] **AI-05**: Retry logic (tenacity) handles OpenAI rate limit errors (429) with exponential backoff

### Data Storage

- [ ] **DB-01**: SQLite database stores all company fields: id, company_name, description, website, industry, business_model, summary, use_case
- [ ] **DB-02**: Database engine configured with `check_same_thread=False` and per-request session via `Depends(get_db)` to prevent FastAPI threading errors
- [ ] **DB-03**: Schema is defined as a SQLModel table class (unified Pydantic + SQLAlchemy model)
- [ ] **DB-04**: Database and tables are created automatically on first run (no manual migration step required for v1)

### REST API

- [ ] **API-01**: `GET /companies` returns all companies with all AI-generated fields as a JSON array
- [ ] **API-02**: `GET /companies/{id}` returns full details for a single company; returns 404 if not found
- [ ] **API-03**: API uses FastAPI lifespan context manager (not deprecated `@app.on_event`) for startup initialization
- [ ] **API-04**: Response models use Pydantic v2-native patterns (no deprecated `orm_mode`, use `model_config = ConfigDict(from_attributes=True)`)

### Configuration

- [ ] **CFG-01**: `OPENAI_API_KEY` is loaded from environment variable via `pydantic-settings`; app fails fast at startup with a clear error if missing
- [ ] **CFG-02**: Database file path is configurable via environment variable with a sensible default (`./data/companies.db`)

## v2 Requirements

### Enhanced API

- **API-V2-01**: `GET /companies?industry=FinTech` — filter by industry
- **API-V2-02**: `GET /companies?q=search+term` — full-text search across name and description
- **API-V2-03**: Pagination (`?page=1&limit=20`) for large datasets

### Data Quality

- **DQ-V2-01**: `analyzed_at` timestamp on each record to track freshness
- **DQ-V2-02**: `raw_yc_data` JSON blob stored as insurance against YC API schema changes
- **DQ-V2-03**: Re-analysis endpoint: `POST /companies/{id}/reanalyze` triggers fresh OpenAI call

### Pipeline

- **PIPE-V2-01**: Scheduled refresh (cron or APScheduler) to collect new YC companies periodically
- **PIPE-V2-02**: Structured logging with per-run summary (X collected, Y analyzed, Z failed)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Authentication on the REST API | Internal tool only; adds complexity without v1 value |
| Frontend / UI | FastAPI `/docs` serves as internal interface |
| Playwright browser automation | YC public JSON API (`api.ycombinator.com`) eliminates the need |
| LangChain / LlamaIndex | Single-prompt-per-record pattern; raw openai client is sufficient |
| Alembic migrations | Schema is stable for v1; `SQLModel.metadata.create_all()` is sufficient |
| Async OpenAI calls | API is read-only; sync routes with FastAPI threadpool are correct for this scope |
| PostgreSQL | SQLite is sufficient for batch size of 10–50 companies |
| Real-time scraping on API request | Scraping runs as a one-time batch pipeline script |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CFG-01 | Phase 1 | Pending |
| CFG-02 | Phase 1 | Pending |
| DB-01 | Phase 1 | Pending |
| DB-02 | Phase 1 | Pending |
| DB-03 | Phase 1 | Pending |
| DB-04 | Phase 1 | Pending |
| COLL-01 | Phase 2 | Pending |
| COLL-02 | Phase 2 | Pending |
| COLL-03 | Phase 2 | Pending |
| COLL-04 | Phase 2 | Pending |
| AI-01 | Phase 3 | Pending |
| AI-02 | Phase 3 | Pending |
| AI-03 | Phase 3 | Pending |
| AI-04 | Phase 3 | Pending |
| AI-05 | Phase 3 | Pending |
| API-01 | Phase 4 | Pending |
| API-02 | Phase 4 | Pending |
| API-03 | Phase 4 | Pending |
| API-04 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-07*
*Last updated: 2026-04-07 after initial definition*
