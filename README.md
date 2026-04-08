# AI Company Research Agent

An agentic pipeline that collects YC startup data, analyzes each company with OpenAI Structured Outputs, stores enriched records in SQLite, and exposes the results via a FastAPI REST API — with a browser frontend, MCP server integration, and CI/CD pipeline.

## Architecture

```
YC JSON API → scraper/yc_scraper.py → data/companies.db
                                            ↓
                                  agent/analyzer.py (OpenAI)
                                            ↓
                          app/main.py (FastAPI REST + frontend)
                          mcp_server/server.py (MCP stdio tools)
```

Three separate entrypoints share one SQLite file. No entrypoint starts another; they communicate only through the DB.

## Quick Start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate  |  Unix: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env — set OPENAI_API_KEY
```

## Usage

```bash
# 1. Collect company data from YC JSON API (50 companies, no API key required)
python scraper/yc_scraper.py

# 2. Run AI analysis pipeline (requires OPENAI_API_KEY)
python -m scripts.run_pipeline

# 3. Start REST API + frontend
uvicorn app.main:app --reload
# Root:     http://localhost:8000        ← redirects to /ui automatically
# Frontend: http://localhost:8000/ui
# API docs: http://localhost:8000/docs

# 4. Start MCP server (stdio transport — for Claude Desktop / Cursor)
python mcp_server/server.py

# Apply DB schema migration (adds description_hash column to existing DBs)
python scripts/migrate_add_hash.py
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/companies/` | List all companies. Supports `?industry=FinTech` and `?q=payment` filters. |
| `GET` | `/companies/{id}` | Full details for a single company. |
| `GET` | `/ui/` | Browser frontend (search + filter UI). |

## MCP Tools

The MCP server exposes three tools for AI agents:

| Tool | Description |
|------|-------------|
| `list_industries` | Returns sorted distinct industry values in the DB. |
| `search_companies` | Filters by `industry` and/or keyword `q`, up to `limit` results. |
| `get_company` | Returns full company dict by integer ID, or `None`. |

## Features

- **Data collection** — YC public JSON API (`api.ycombinator.com/v0.1/companies`), 50 companies, idempotent upserts
- **AI analysis** — OpenAI `gpt-4o-mini` Structured Outputs with controlled `Industry` enum (13 verticals), `business_model`, `summary`, `use_case`
- **AI caching** — SHA-256 hash of description; skips reanalysis if hash + industry both present
- **Filtering & search** — `?industry=` exact match + `?q=` substring search across name and description
- **MCP server** — FastMCP stdio transport; 3 tools for agentic clients
- **Frontend** — Vanilla JS single-page app at `/ui`; debounced live search
- **CI/CD** — GitHub Actions: lint → test → AI code review on PRs (draft/fork guarded)
- **Resilience** — per-company `try/except` in analyze loop; one failure never aborts the batch
- **Tenacity retry** — exponential backoff on OpenAI `RateLimitError` / `APIConnectionError` (5 attempts max)

## Tests

```bash
# All tests (58 total: 44 unit + 14 E2E)
python -m pytest tests/ -v

# E2E tests only (file-based SQLite, mocked HTTP + OpenAI)
python -m pytest tests/test_e2e.py -v
```

E2E test coverage spans the full pipeline:

| Test | Scenario |
|------|----------|
| `test_scraper_to_db_to_api` | Mock YC HTTP → scraper → REST API (no AI) |
| `test_analyze_step_populates_ai_fields` | Raw DB rows → analyze → enriched API response |
| `test_full_pipeline_end_to_end` | Scrape + analyze + API, mock-to-mock |
| `test_caching_skips_reanalysis` | 0 OpenAI calls on second analyze run |
| `test_filter_by_industry` | `?industry=FinTech` returns correct subset |
| `test_search_by_keyword` | `?q=payment` matches name and description |
| `test_filter_and_search_combined` | Intersection of both filters |
| `test_frontend_served_at_ui` | `/ui/` returns HTML |
| `test_mcp_list_industries` | MCP tool returns sorted distinct values |
| `test_mcp_search_companies` | MCP tool filters by industry |
| `test_mcp_get_company` | MCP tool returns dict or None |
| `test_pipeline_resilience_one_failure` | Batch continues after one company fails |
| `test_all_fields_in_api_response` | All 9 fields present in JSON response |
| `test_data_integrity_scraper_to_api` | Exact values preserved scraper → DB → API |

## Stack

- `sqlmodel` — SQLite ORM + Pydantic schema (single `Company` class)
- `pydantic-settings` — typed config with fail-fast `OPENAI_API_KEY` validation
- `openai==2.30.0` — Structured Outputs via `client.beta.chat.completions.parse`
- `fastapi[standard]` — REST API with auto-generated docs
- `fastmcp` — MCP server (stdio transport)
- `requests` — YC JSON API scraper
- `tenacity` — exponential backoff retry for OpenAI rate limits
