---
phase: phase-2
plan: "01"
subsystem: database
tags: [sqlite3, requests, yc-api, scraper, upsert]

requires:
  - phase: phase-1-01
    provides: Company SQLModel schema (column names/types), _DB_PATH path pattern

provides:
  - scraper/yc_scraper.py — fully standalone YC API scraper (zero app/ imports)
  - data/companies.db populated with 50 real YC company records
affects: [phase-3, phase-4, phase-5]

tech-stack:
  added: []
  patterns:
    - Standalone scraper pattern — sqlite3 stdlib only, no SQLModel imports
    - SELECT + conditional INSERT/UPDATE upsert (preserves AI fields, no UNIQUE constraint needed)
    - requests.Session for TCP connection reuse across paginated API calls
    - db_path parameter for test isolation (default _DB_PATH, override in tests)
    - Per-company try/except isolation — one failure never aborts the batch

key-files:
  created:
    - scraper/yc_scraper.py
  modified:
    - data/companies.db (populated — not committed)

key-decisions:
  - "Used sqlite3 stdlib (not SQLModel) — scraper cannot import from app/ per import boundary rule"
  - "SELECT + conditional INSERT/UPDATE (not INSERT OR REPLACE) — INSERT OR REPLACE deletes old row, wiping Phase 3 AI fields"
  - "fetch_companies accepts db_path=None parameter — enables tmp_path test isolation without touching real DB"
  - "MAX_PAGES=2 (50 companies) — sufficient for Phase 3 AI demo, avoids over-scraping"
  - "_ensure_table called at scraper startup — defensive CREATE TABLE IF NOT EXISTS for fresh environments"

patterns-established:
  - "Scraper import boundary: scraper/ imports NOTHING from app/ or agent/ — verified with AST scan"
  - "Upsert safety: SELECT id + conditional UPDATE/INSERT — never INSERT OR REPLACE (wipes AI fields)"
  - "Session patching in tests: patch('scraper.yc_scraper.requests.Session') not requests.get (scraper uses Session.get)"
  - "website normalization: company.get('website') or None — converts '' to NULL"

requirements-completed: [COLL-01, COLL-02, COLL-03, COLL-04]

duration: 25min
completed: 2026-04-08
---

# Phase 2: Data Collection — Plan 01 Summary

**Standalone YC JSON API scraper using sqlite3 stdlib — fetches 50 companies across 2 paginated pages with safe SELECT+UPDATE upsert that preserves Phase 3 AI fields**

## Performance

- **Duration:** ~25 min (including live API verification)
- **Completed:** 2026-04-08
- **Tasks:** 2 (implement scraper + live verification)
- **Files created:** 1

## Accomplishments

- `scraper/yc_scraper.py` — fully standalone YC API scraper with all required functions
- Live verification: 50 companies stored, 0 empty descriptions, 0 empty-string websites, idempotent
- `_get_description` fallback chain: `longDescription → oneLiner → "{name} (no description available)"` (shortDescription absent from YC API — confirmed by researcher)
- `_upsert_company`: SELECT + conditional INSERT/UPDATE — AI fields (`industry`, `business_model`, etc.) preserved on re-run
- Per-company error isolation via try/except — one bad record never aborts the batch

## Task Commits

1. **Task 1: scraper/yc_scraper.py** — `793c48e` (feat(phase-2): implement YC API scraper)
2. **Task 2: Live verification** — included in same commit (no code changes, data only)

## Files Created

- `scraper/yc_scraper.py` — 109 lines:
  - `_DB_PATH` — `Path(__file__).resolve().parent.parent / "data" / "companies.db"` (absolute)
  - `_ensure_table(conn)` — defensive `CREATE TABLE IF NOT EXISTS` on startup
  - `_get_description(company)` — pure fallback function (no shortDescription)
  - `_upsert_company(conn, name, desc, website)` — safe upsert preserving AI fields
  - `fetch_companies(db_path=None)` — pagination loop, Session reuse, per-company isolation
  - `main()` — entry point with logging

## Decisions Made

- **sqlite3 over SQLModel**: Import boundary rule requires scraper/ to import nothing from app/. sqlite3 is stdlib and self-sufficient.
- **SELECT+UPDATE over INSERT OR REPLACE**: INSERT OR REPLACE deletes and re-inserts, wiping any AI fields Phase 3 has already populated. SELECT+UPDATE only touches description and website.
- **db_path parameter**: Added to `fetch_companies` signature to enable tmp_path test isolation — critical design decision caught pre-implementation from research.
- **MAX_PAGES=2**: 50 companies provides enough diversity for Phase 3 AI demo without over-scraping.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule — Blocking] patch("requests.get") doesn't intercept Session.get()**
- **Found during:** Wave 2 test execution
- **Issue:** Plan 02 specified `patch("requests.get")` but scraper uses `requests.Session().get()` — integration tests hit live API and timed out
- **Fix:** Added `_patch_session()` helper in tests using `patch("scraper.yc_scraper.requests.Session", return_value=mock_session)` — correctly intercepts the Session constructor
- **Files modified:** tests/test_scraper.py
- **Verification:** All 7 tests pass offline in 1.17s, no network calls
- **Committed in:** Wave 2 commit

---

**Total deviations:** 1 auto-fixed (1 blocking — test mock target mismatch)
**Impact:** Fix was necessary for test isolation. No scope creep.

## Issues Encountered

- `patch("requests.get")` in integration tests didn't intercept `requests.Session().get()` — fixed by patching `requests.Session` constructor instead.

## Next Phase Readiness

50 real YC company records in `data/companies.db` with `company_name`, `description`, and `website` populated. `industry`, `business_model`, `summary`, `use_case` are NULL — ready for Phase 3 AI analysis pipeline to populate.

---
*Phase: phase-2*
*Completed: 2026-04-08*
