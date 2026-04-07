# Phase 4 — Wave 2 Summary: API Tests

**Completed**: 2026-04-07
**Plans executed**: 04-02-PLAN.md
**Status**: ✅ DONE

## What Was Built

### Task 2.1 — `tests/test_api.py`
6 hermetic TestClient tests — in-memory SQLite, `dependency_overrides`, no production DB access.

| # | Test | Validates |
|---|------|-----------|
| 1 | `test_get_companies_empty` | Empty DB → `[]` 200 response (API-01) |
| 2 | `test_get_companies_returns_list` | 2 inserts → both returned with correct fields (API-01) |
| 3 | `test_get_company_by_id` | Correct record returned by PK (API-02) |
| 4 | `test_get_company_not_found` | 404 + `{"detail": "Company not found"}` (API-02) |
| 5 | `test_get_company_invalid_id` | `/companies/abc` → 422 (API-02) |
| 6 | `test_get_companies_includes_ai_fields` | All 4 AI fields present as `null` (API-01, API-04) |

Key safeguards:
- `os.environ.setdefault("OPENAI_API_KEY", "test-key-not-used")` before any `from app.*` import
- `StaticPool` keeps in-memory DB alive across connections within a test
- `app.dependency_overrides.clear()` in `client` fixture teardown

## Verification Results

```
tests/test_api.py      6 passed
tests/test_analyzer.py 7 passed   ← no regressions
tests/test_foundation.py 4 passed ← no regressions
tests/test_scraper.py  7 passed   ← no regressions
─────────────────────────────────
TOTAL: 24 passed in 3.18s
```

## Requirements Satisfied

| Req    | Test(s) |
|--------|---------|
| API-01 | tests 1, 2, 6 |
| API-02 | tests 3, 4, 5 |
| API-03 | lifespan pattern (verified via no DeprecationWarning in test output) |
| API-04 | test 6 (AI fields as null, not omitted) |
