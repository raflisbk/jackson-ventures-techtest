---
phase: phase-1
plan: "01"
subsystem: database
tags: [sqlmodel, pydantic-settings, sqlite, fastapi, openai]

requires: []
provides:
  - Project directory scaffold with all placeholder packages (app/, scraper/, agent/, scripts/, data/)
  - requirements.txt with all dependencies pinned (openai==2.30.0, sqlmodel==0.0.38, fastapi[standard]==0.135.3)
  - app/config.py — pydantic-settings Settings with OPENAI_API_KEY fail-fast (no default)
  - app/models.py — Company(SQLModel, table=True) unified ORM + Pydantic class
  - app/database.py — SQLite engine with check_same_thread=False, absolute _DB_PATH, get_db(), create_db_and_tables()
  - .env.example, .gitignore, README.md
affects: [phase-2, phase-3, phase-4, phase-5, phase-6, phase-7, phase-8]

tech-stack:
  added:
    - openai==2.30.0
    - sqlmodel==0.0.38
    - fastapi[standard]==0.135.3
    - pydantic-settings==2.7.1
    - python-dotenv==1.2.2
    - tenacity==9.1.4
    - requests==2.32.3
    - pytest==9.0.2
    - httpx==0.28.1
  patterns:
    - SQLModel dual-role pattern (table=True makes class both SQLAlchemy ORM table and Pydantic schema)
    - Absolute DB path via Path(__file__).resolve().parent.parent
    - pydantic-settings fail-fast (required field with no default = ValidationError at import)
    - check_same_thread=False + per-request Session (two-part SQLite threading fix)

key-files:
  created:
    - app/config.py
    - app/models.py
    - app/database.py
    - requirements.txt
    - .env.example
    - .gitignore
    - README.md
    - app/__init__.py
    - scraper/__init__.py
    - agent/__init__.py
    - scripts/__init__.py
    - data/.gitkeep
  modified: []

key-decisions:
  - "Used Path(__file__).resolve() for DB path — never relative path strings that break based on CWD"
  - "OPENAI_API_KEY has no default in Settings — pydantic-settings raises ValidationError at import time if missing"
  - "Single Company class with table=True — serves as both SQLAlchemy ORM table and Pydantic API schema"
  - "check_same_thread=False on engine + new Session per get_db() call — both required for FastAPI threadpool safety"
  - "Excluded playwright, beautifulsoup4, lxml — YC JSON API (api.ycombinator.com/v0.1/companies) only needs requests"

patterns-established:
  - "SQLModel dual-role: Company(SQLModel, table=True) is the DB table AND Pydantic schema — no duplicate models"
  - "Absolute DB path: always Path(__file__).resolve().parent.parent / 'data' / 'companies.db' in database.py"
  - "Threading fix: always paired — check_same_thread=False on engine AND new Session per get_db() call"
  - "Fail-fast config: required settings have no default — crash at startup, not mid-request"

requirements-completed: [CFG-01, CFG-02, DB-01, DB-02, DB-03, DB-04]

duration: 35min
completed: 2026-04-07
---

# Phase 1: Foundation — Plan 01 Summary

**SQLModel Company table, pydantic-settings fail-fast config, and SQLite engine with absolute path + threading fix — full project scaffold ready for downstream phases**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-04-07
- **Tasks:** 2 (scaffold + core modules)
- **Files created:** 12

## Accomplishments

- Project directory structure created with all placeholder packages (`app/`, `scraper/`, `agent/`, `scripts/`, `data/`)
- `requirements.txt` with all dependencies pinned to exact versions (live-verified 2026-04-07)
- `app/config.py` — pydantic-settings `Settings` with `OPENAI_API_KEY` (no default = fail-fast at import)
- `app/models.py` — `Company(SQLModel, table=True)` unified ORM table + Pydantic schema
- `app/database.py` — SQLite engine with `check_same_thread=False`, `_DB_PATH` absolute via `Path(__file__).resolve()`, `create_db_and_tables()` idempotent, `get_db()` per-request Session generator

## Task Commits

1. **Task 1: Project Scaffold** — part of `f4c4c8a` (feat: Phase 1 — foundation)
2. **Task 2: Core App Modules** — part of `f4c4c8a` (feat: Phase 1 — foundation)

## Files Created

- `requirements.txt` — all deps pinned; no Playwright/BS4/lxml (YC JSON API only needs `requests`)
- `app/config.py` — `Settings(BaseSettings)` with fail-fast `OPENAI_API_KEY`; module-level `settings` singleton
- `app/models.py` — `Company(SQLModel, table=True)` with id (PK auto), company_name, description, website, industry, business_model, summary, use_case
- `app/database.py` — engine + `_DB_PATH` (absolute) + `create_db_and_tables()` + `get_db()` generator
- `app/__init__.py`, `scraper/__init__.py`, `agent/__init__.py`, `scripts/__init__.py` — package markers
- `data/.gitkeep` — tracks directory while keeping `.db` files gitignored
- `.env.example`, `.gitignore`, `README.md`

## Decisions Made

- **Absolute DB path**: `Path(__file__).resolve().parent.parent / "data" / "companies.db"` — ensures same DB file is opened regardless of which directory the process starts from
- **No Playwright**: Research corrected STACK.md — YC JSON API at `api.ycombinator.com/v0.1/companies` returns clean JSON; no HTML scraping needed
- **Single Company class**: `table=True` makes it serve double duty as ORM table and Pydantic response schema — no duplicate models
- **DATABASE_URL in config.py is a convenience default only** — `database.py` ignores it and always uses the `__file__`-based absolute path

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## Next Phase Readiness

All three shared modules (`app.config`, `app.models`, `app.database`) are importable and correct. Phase 2 (scraper), Phase 3 (agent), and Phase 4 (API) can all import from this foundation without modification.

The `DATABASE_URL` absolute path value: determined at runtime by `Path(__file__).resolve()` from `app/database.py` location.

---
*Phase: phase-1*
*Completed: 2026-04-07*
