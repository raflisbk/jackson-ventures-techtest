# Project Research Summary — v1.1

**Project:** AI Company Research Agent — Milestone v1.1: Agent-Accessible & Production-Ready
**Domain:** AI data pipeline + REST API + MCP server + Static frontend + CI/CD (Python / FastAPI / SQLite / FastMCP)
**Researched:** 2026-04-07 (v1.1; supersedes v1.0 SUMMARY)
**Confidence:** HIGH (all patterns live-verified against installed packages and running code)

---

## Executive Summary

v1.1 adds five production-readiness features to the existing v1.0 Python/FastAPI/SQLModel/SQLite pipeline: AI response caching (SHA-256 description hash), filtering/search on `GET /companies`, a standalone MCP server for AI agent clients, a static HTML/JS frontend, and a GitHub Actions CI/CD pipeline with agentic PR code review. The v1.0 foundation (scraper, OpenAI analyzer, REST API — Phases 1–4) is complete and unchanged; v1.1 builds exclusively on top of it with **zero breaking changes** to existing APIs or dependencies.

The research recommends a **standalone MCP server** (`mcp_server/server.py`) as a third OS process (alongside the existing FastAPI server and pipeline script), communicating over stdio transport via `fastmcp==3.2.0`. This is the authoritative decision: the FEATURES.md suggestion to mount MCP onto FastAPI via `mcp==1.27.0` is overruled by the ARCHITECTURE.md finding that separate processes are cleaner for lifecycle management and that `fastmcp==3.2.0` (PrefectHQ/fastmcp, the standalone descendant of the original FastMCP) is the correct library. For CI/CD code review, the architecture agent recommends `scripts/ai_code_review.py` (custom Python script using the existing `OPENAI_API_KEY`) via GitHub Actions — this avoids adding `anthropics/claude-code-action@v1` (which requires a new `ANTHROPIC_API_KEY` secret) without sacrificing any capability.

The key risks are all concrete and have verified fixes: `print()` in MCP stdio corrupts the JSON-RPC stream; SQLite's default journal mode causes `SQLITE_BUSY` when the MCP server and FastAPI server share the DB file; `SQLModel.metadata.create_all()` silently skips the new `description_hash` column on existing tables; mounting `StaticFiles` at `/` before API routes makes all API routes return 404; and empty-string query params like `?industry=` are not `None` in FastAPI, triggering unintended zero-result filters. All five have been live-verified with exact error messages and have 5–15 line prevention patterns documented below.

---

## Key Findings

### Recommended Stack — v1.1 Delta

The entire v1.1 milestone requires **one new Python package** (`fastmcp==3.2.0`). Everything else uses stdlib (`hashlib`, `pathlib`, `sqlite3`) or already-installed packages (`FastAPI StaticFiles`, `SQLModel`, `openai`).

| Technology | Version | Purpose | Source |
|------------|---------|---------|--------|
| `fastmcp` | `3.2.0` (new) | MCP server framework — `@mcp.tool` decorator, auto-generates JSON schemas from Python signatures, stdio + http transport | STACK.md (live PyPI verified) |
| `hashlib` | stdlib | SHA-256 description hashing for AI response cache | STACK.md |
| `fastapi.staticfiles.StaticFiles` | (already installed) | Serve `frontend/` directory at `/ui` — no separate server | STACK.md / ARCHITECTURE.md |
| `anthropics/claude-code-action@v1` | v1.0 | OR: use `scripts/ai_code_review.py` via custom GitHub Actions workflow | STACK.md vs ARCHITECTURE.md — see CI/CD decision below |

**Conflict resolved — CI/CD action:** STACK.md recommends `anthropics/claude-code-action@v1` (requires new `ANTHROPIC_API_KEY`). ARCHITECTURE.md recommends `scripts/ai_code_review.py` (uses existing `OPENAI_API_KEY`, full control). **Winner: `scripts/ai_code_review.py`** — reuses existing secret, avoids third-party action dependency, keeps logic inside the repo. Implement as a Python script (`openai` + `httpx`) invoked from `.github/workflows/code-review.yml`.

**Conflict resolved — MCP library:** FEATURES.md recommends `mcp==1.27.0` mounted onto FastAPI. STACK.md and ARCHITECTURE.md both recommend `fastmcp==3.2.0` standalone. **Winner: `fastmcp==3.2.0` standalone** — verified by ARCHITECTURE.md live code inspection; separate process is architecturally cleaner.

**Do NOT add:**
- `alembic` — a 30-line `ALTER TABLE` migration script beats 5+ config files at this scale
- `jinja2` / `aiofiles` — `StaticFiles` serves pre-built HTML/JS with no server-side rendering
- `redis` / `celery` — SQLite column cache is sufficient; no distributed infrastructure needed
- `Alpine.js` / `Vue` / `React` — 80 lines of vanilla JS solves the problem without a build pipeline

---

### Expected Features (v1.1 Table Stakes)

**Feature 5.1 — AI Response Caching:**
- `description_hash: Optional[str]` column on `Company` model (64-char SHA-256 hex, `index=True`)
- `compute_description_hash(description)` helper: `.strip()` before hashing (prevents whitespace drift), returns `None` for empty/None descriptions
- Two-condition cache check: `hash matches AND industry is not None` (guards against partial-write records)
- Cache hit logging: `"[CACHE HIT] {name} — skipping"` to stdout; summary count at end of run

**Feature 5.2 — Filtering / Search:**
- `?industry=` query param: case-insensitive exact match via `col(Company.industry) == industry`
- `?q=` query param: name + description substring search via `.contains(q)` (`LIKE %q%`)
- Both params optional, composable, additive (AND between params, OR within `?q=` fields)
- Return `[]` (not 404) when no results match

**Feature 5.3 — MCP Server:**
- Three tools: `get_all_companies()`, `get_company_by_id(company_id)`, `search_companies(industry, search)`
- Standalone process (`python mcp_server/server.py`), stdio transport for Claude Desktop
- Reads same `data/companies.db` via its own SQLAlchemy engine with WAL mode enabled
- Tool docstrings are required — AI agents read them to understand what to call

**Feature 5.4 — Static Frontend:**
- `frontend/index.html` + `frontend/app.js` + `frontend/style.css`
- Company cards: name, industry badge, summary, website link
- Industry filter dropdown + text search box wired to `GET /companies?industry=&q=`
- Served by FastAPI `StaticFiles` at `/ui` — same origin, no CORS issues, no separate server
- Tailwind CSS via CDN — zero build step

**Feature 5.5 — CI/CD Pipeline:**
- `.github/workflows/ci.yml`: `pytest` on push to main + all PRs; Python 3.13; `actions/setup-python@v6`
- `.github/workflows/code-review.yml`: agentic PR review via `scripts/ai_code_review.py`; fires on `pull_request: [opened, synchronize]`; skips drafts (`pull_request.draft == false`); skips forks (`head.repo.full_name == github.repository`)
- Required secret: `OPENAI_API_KEY` (already used by pipeline; same key reused)

**Defer to v1.2+:**
- FTS5 full-text search (LIKE is correct at 50 records)
- Pagination (< 100 records expected)
- MCP HTTP transport (stdio covers local Claude Desktop use case)
- MCP authentication (internal tool)
- `pytest-cov` coverage reports

---

### Architecture Approach

v1.1 extends the existing two-entrypoint design to **three entrypoints**, all sharing `data/companies.db`:

```
┌─────────────────────────────────────────────────────────────────┐
│  1. PIPELINE   scripts/run_pipeline.py                          │
│     YC API → scraper → analyzer (+ hash check) → companies.db  │
└────────────────────────────────────┬────────────────────────────┘
                                     │ data/companies.db (shared)
          ┌──────────────────────────┼──────────────────────────┐
          ▼                          ▼                          ▼
┌──────────────────┐    ┌─────────────────────┐    ┌───────────────────┐
│  2. API SERVER   │    │  3. MCP SERVER      │    │  4. CI/CD         │
│  uvicorn         │    │  python mcp_server/ │    │  GitHub Actions   │
│  app.main:app    │    │  server.py          │    │  pytest + review  │
│                  │    │                     │    │  (no DB access)   │
│  GET /companies  │    │  @mcp.tool          │    └───────────────────┘
│  ?industry=&q=   │    │  get_all_companies  │
│  GET /companies/ │    │  get_company_by_id  │
│  {id}            │    │  search_companies   │
│                  │    │                     │
│  GET /ui/ ←      │    │  stdio transport    │
│  frontend/       │    │  (Claude Desktop)   │
└──────────────────┘    └─────────────────────┘
```

**New files (v1.1 additions):**
- `mcp_server/__init__.py` + `mcp_server/server.py` — standalone MCP entrypoint
- `frontend/index.html` + `frontend/app.js` + `frontend/style.css` — static UI
- `scripts/migrate_add_hash.py` — one-time idempotent `ALTER TABLE` migration
- `scripts/ai_code_review.py` — agentic PR reviewer (runs inside GitHub Actions)
- `.github/workflows/ci.yml` — tests on push/PR
- `.github/workflows/code-review.yml` — agentic review on PR

**Modified files:**
- `app/models.py` — add `description_hash: Optional[str] = Field(default=None, index=True)`
- `app/routers/companies.py` — add `?industry=` and `?q=` query params
- `app/main.py` — mount `StaticFiles` at `/ui` AFTER `include_router()` calls
- `agent/analyzer.py` — hash check before OpenAI call
- `requirements.txt` — add `fastmcp==3.2.0`

**Key architectural rule:** `mcp_server/` imports FROM `app/` — never the reverse. No circular dependency. The MCP server must NOT import `app.config` (it requires `OPENAI_API_KEY` at module scope; the MCP server doesn't need it and will crash if the env var is absent).

**Build order within v1.1 (Phase 5.1 → 5.5 is mandatory — hash column must exist before filtering queries reference it):**

| Phase | Feature | Dependency |
|-------|---------|------------|
| 5.1 | AI Caching (hash migration) | Schema change first — all subsequent phases read `description_hash` |
| 5.2 | Filtering / Search | Requires v1.0 `GET /companies` route (already exists) |
| 5.3 | MCP Server | Should reuse `search_companies` filter logic from 5.2 |
| 5.4 | Static Frontend | Requires `?industry=` + `?q=` from 5.2 to be working |
| 5.5 | CI/CD | Independent — no application code changes; can be done any time |

---

### Critical Pitfalls (v1.1 — All Live-Verified)

**MCP-1: `print()` corrupts the MCP stdio JSON-RPC stream**

Any `print()` in `mcp_server/server.py` or any module it imports writes to stdout, which is the MCP protocol channel. The client silently disconnects with a JSON parse error. **Prevention:** Redirect ALL logging to stderr BEFORE any imports:

```python
# mcp_server/server.py — FIRST TWO LINES, before any other imports
import sys, logging
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
# Now safe to import from app/ — module-scope print()s are NOT a risk
# But never use print() in this file. Use logging.info() instead.
```

**MCP-2: Two processes sharing SQLite with default `journal_mode=delete` → `SQLITE_BUSY`**

SQLite's default journal mode acquires an exclusive lock on writes. When FastAPI and the MCP server both have engines pointing at `data/companies.db`, concurrent access raises `OperationalError: database is locked`. **Prevention:** Enable WAL mode on **both** engines (it persists in the DB file):

```python
# Add to BOTH app/database.py AND mcp_server/server.py engine setup
from sqlalchemy import event

@event.listens_for(engine, "connect")
def set_wal_mode(dbapi_connection, _):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()
```

**HASH-1: `SQLModel.metadata.create_all()` silently skips new columns on existing tables**

Adding `description_hash` to `Company` and calling `create_all()` raises no error but does not add the column. Queries fail later with `OperationalError: no such column: company.description_hash`. **Prevention:** Run an idempotent migration at startup:

```python
# scripts/migrate_add_hash.py (also inline in database.py create_db_and_tables)
def _run_migrations(engine):
    with engine.connect() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(company)"))]
        if "description_hash" not in cols:
            conn.execute(text("ALTER TABLE company ADD COLUMN description_hash TEXT"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_company_description_hash ON company (description_hash)"))
            conn.commit()
```

**STATIC-1: Mounting `StaticFiles` at `/ui` BEFORE `include_router()` shadows API routes**

FastAPI matches routes in registration order. A static mount acts as a catch-all for its prefix. **Prevention:** Always mount static files LAST:

```python
# app/main.py — correct order
app.include_router(companies_router)            # 1. API routes first
app.mount("/ui", StaticFiles(directory="frontend", html=True), name="frontend")  # 2. Static LAST
```

**FILTER-1 + FILTER-2: Empty string params and LIKE wildcards**

`?industry=` (empty) is `""` in Python — not `None` — so `if industry is not None:` wrongly triggers `WHERE industry = ""` → 0 results. `?q=%` treats `%` as a SQL LIKE wildcard and matches all records. **Prevention:**

```python
# Use falsy check (rejects None, "", "   ")
if industry:
    stmt = stmt.where(col(Company.industry) == industry.strip())

# Escape LIKE wildcards before .contains()
def escape_like(v: str) -> str:
    return v.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

if q:
    safe_q = escape_like(q.strip())
    stmt = stmt.where(col(Company.company_name).contains(safe_q) | col(Company.description).contains(safe_q))
```

---

## Implications for Roadmap

v1.1 features continue the phase numbering from v1.0's Phases 1–4. Phases 5–9 are the v1.1 sub-phases.

### Phase 5 — AI Response Caching (Schema Migration)
**Rationale:** Schema change must come first. Phases 6–8 all depend on `description_hash` existing in the DB. Running the migration before anything else prevents the "silent column skip" failure mode.
**Delivers:** `description_hash` column on `company` table (via `ALTER TABLE`), indexes on `description_hash` + `industry` + `business_model`, `compute_description_hash()` helper, cache check in `agent/analyzer.py`, `--force-refresh` CLI flag
**Pitfalls to prevent:** HASH-1 (migration not `create_all`), HASH-2 (run migration at startup), HASH-3 (`None` description guard)
**Research flag:** Standard pattern — no phase research needed

### Phase 6 — Filtering / Search on GET /companies
**Rationale:** Filtering is foundational — the MCP server's `search_companies` tool and the frontend's filter UI both call this endpoint. Build it once, reuse everywhere.
**Delivers:** `?industry=` (exact match) and `?q=` (name + description substring) query params on `GET /companies`; backward-compatible (no params = return all); input validation; updated tests
**Pitfalls to prevent:** FILTER-1 (falsy check not `is not None`), FILTER-2 (escape LIKE wildcards)
**Research flag:** Standard FastAPI/SQLModel pattern — no phase research needed

### Phase 7 — MCP Server
**Rationale:** Depends on Phase 6 (reuses filter logic in `search_companies` tool). Standalone process — no changes to FastAPI app required.
**Delivers:** `mcp_server/server.py` with `get_all_companies`, `get_company_by_id`, `search_companies` tools; stdio transport; WAL mode on shared DB; Claude Desktop config documented in README
**Pitfalls to prevent:** MCP-1 (stderr redirect before imports), MCP-2 (WAL mode on both engines), MCP-3 (FastMCP v3 constructor — no transport args), MCP-4 (don't import `app.config`)
**Research flag:** FastMCP patterns are well-documented at gofastmcp.com — no phase research needed. The WAL mode setup is the only non-obvious piece.

### Phase 8 — Static Frontend
**Rationale:** Depends on Phase 6 (`?industry=` and `?q=` must work before the frontend uses them). Simplest phase — vanilla HTML/JS, no build step.
**Delivers:** `frontend/index.html` + `frontend/app.js` + `frontend/style.css`; company cards with name, industry badge, summary, website link; filter dropdown; text search; served via FastAPI `StaticFiles` at `/ui`
**Pitfalls to prevent:** STATIC-1 (mount after `include_router`), STATIC-2 (conditional mount if dir missing — CI safety), XSS (always `escapeHtml()` when setting innerHTML)
**Research flag:** No research needed — vanilla JS + FastAPI StaticFiles is a well-known pattern

### Phase 9 — CI/CD Pipeline
**Rationale:** Independent of all application code. Can technically run any time, but building it last means the test suite is complete and the workflow validates real code.
**Delivers:** `.github/workflows/ci.yml` (pytest on push + PR; Python 3.13; `actions/setup-python@v6`); `.github/workflows/code-review.yml` (agentic review via `scripts/ai_code_review.py`); draft PR skip; fork PR skip; explicit `pull-requests: write` permission
**Pitfalls to prevent:** CI-1 (fork read-only token), CI-2 (draft PR guard), CI-3 (secret validation step), CI-4 (use `GITHUB_TOKEN` not PAT to prevent review loops), CI-5 (explicit permissions block)
**Research flag:** No research needed — GitHub Actions patterns are standard. The custom `ai_code_review.py` script uses `openai` + `httpx` which are already in requirements.

### Research Flags Summary
- **Phases 5–9: No `/gsd-research-phase` needed** — all patterns live-verified, HIGH confidence
- Phase 7 (MCP) is the only phase with non-obvious pitfalls; the prevention patterns are documented and concrete
- Phase 9 (CI/CD) has the most edge cases (fork tokens, draft filtering, bot loops) but all have simple YAML guards

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | `fastmcp==3.2.0` live-verified on PyPI 2026-04-07; transitive deps checked against installed venv; zero conflicts |
| Features | HIGH | All 5 features have verified implementation patterns; table-stakes list derived from live code testing |
| Architecture | HIGH | Component boundaries verified via live import tests; WAL mode verified with two-process SQLite test; StaticFiles mount order verified with FastAPI TestClient |
| Pitfalls | HIGH | All 5 critical pitfalls reproduced live with exact error messages (SQLITE_BUSY, OperationalError: no such column, 404 on API routes, Count: 0 on empty param) |

**Overall confidence: HIGH**

### Conflicts Resolved

| Conflict | Resolution | Rationale |
|----------|-----------|-----------|
| `fastmcp==3.2.0` standalone vs `mcp==1.27.0` mounted on FastAPI | **`fastmcp==3.2.0` standalone wins** | Architecture agent live-verified; separate process is cleaner; FastMCP is the standard layer |
| `anthropics/claude-code-action@v1` vs `scripts/ai_code_review.py` | **`scripts/ai_code_review.py` wins** | Reuses existing `OPENAI_API_KEY`; no new third-party action; logic lives in repo |
| Frontend: Jinja2 templates vs static HTML/JS | **Static HTML/JS wins** | No new dependencies; no build step; `StaticFiles` at `/ui` solves it cleanly |

### Gaps to Address

- **WAL mode persistence:** WAL mode is set per-connection via `PRAGMA journal_mode=WAL` and persists in the DB file. If the DB file is deleted and recreated (e.g., fresh dev setup), both engines must set WAL before the other process opens the file. The `@event.listens_for(engine, "connect")` pattern handles this correctly.
- **MCP server `sys.path` injection:** `mcp_server/server.py` must add the project root to `sys.path` to import from `app/`. The `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` line must precede app imports. Include this in the template.
- **Frontend `escapeHtml` XSS:** The frontend renders API data via `innerHTML`. A missing `escapeHtml()` call is a low-severity XSS risk (internal tool). Document the pattern in the phase plan.

---

## Sources

### STACK.md (HIGH confidence — all live-verified 2026-04-07)
- PyPI `fastmcp` API: v3.2.0 latest; Python 3.13 compat; `pydantic>=2.11.7`; `uvicorn>=0.35`
- PrefectHQ/fastmcp docs: `@mcp.tool` + `mcp.run()` API; stdio default; HTTP available
- `anthropics/claude-code-action` action.yml: inputs verified; v1 tag confirmed
- GitHub API: `actions/checkout@v6` (v6.0.2, 2026-01-09); `actions/setup-python@v6` (v6.2.0, 2026-01-22)
- Project venv pip list: pydantic 2.12.5, uvicorn 0.44.0, openapi-pydantic 0.5.1 — all FastMCP constraints satisfied

### FEATURES.md (HIGH confidence)
- MCP SDK (`mcp==1.27.0`) PyPI + official README verified
- SQLite LIKE case-insensitivity confirmed via live Python test
- `qodo-ai/pr-agent` PyPI + official docs verified (not chosen but confirmed viable)
- Jinja2 v3.1.6 confirmed installed as transitive FastAPI dep

### ARCHITECTURE.md (HIGH confidence — live code + import tests)
- `mcp_server/server.py` standalone pattern: live import verification confirmed `app.database.engine` resolves correctly from MCP process
- `FastMCP("YC Research Agent")` constructor + `mcp.run()`: verified against FastMCP 3.2.0 source
- StaticFiles mount order: verified with FastAPI TestClient — routes registered before mount return 200; after mount → 404
- SQLModel `col()` + chained `.where()`: verified with SQLModel 0.0.38 + SQLAlchemy 2.0.49
- WAL mode: `PRAGMA journal_mode=WAL` enables concurrent reads + writes — live two-process test confirmed

### PITFALLS.md (HIGH confidence — all pitfalls live-verified)
- MCP-1 (print corruption): FastMCP docs + MCP spec confirmed; reproduction confirmed
- MCP-2 (SQLITE_BUSY): `PRAGMA journal_mode` returned `delete`; two-process test → `OperationalError` confirmed
- HASH-1 (`create_all` silent skip): `OperationalError: no such column` after class update + `create_all()` — confirmed
- FILTER-1 (empty string): `GET /companies?industry=` → Count: 0 — confirmed
- FILTER-2 (LIKE wildcard): `GET /companies?q=%` → all records returned — confirmed
- STATIC-1 (mount order): `GET /api/companies` → 404 when static mounted before routes — confirmed

---

*Research completed: 2026-04-07 (v1.1 — 4 research agents + synthesizer)*
*Supersedes: v1.0 SUMMARY.md (Phases 1–4)*
*Ready for roadmap: yes — Phases 5–9*
