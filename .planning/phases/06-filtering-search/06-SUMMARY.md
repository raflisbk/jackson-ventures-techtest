# Phase 6 — Summary: Filtering & Search

**Completed**: 2026-04-08
**Status**: ✅ DONE

## What Was Built

### `app/routers/companies.py` — updated `get_companies()`
Added `industry: Optional[str]` and `q: Optional[str]` query params:

| Logic | Implementation |
|-------|---------------|
| Industry filter | `func.lower(Company.industry) == industry.lower()` |
| Empty guard | `if industry:` truthy check (rejects `""`) |
| Text search | `Company.company_name.ilike(pattern) OR Company.description.ilike(pattern)` |
| Wildcard escape | `%` → `\%`, `_` → `\_` before building LIKE pattern |

### `tests/test_filtering.py` — 11 tests

| # | Test | Validates |
|---|------|-----------|
| 1 | `test_filter_by_industry_exact` | Exact match returns 1 result |
| 2 | `test_filter_by_industry_case_insensitive` | fintech/FinTech/FINTECH all match |
| 3 | `test_filter_empty_industry_returns_all` | `?industry=` → all rows (FILTER-1) |
| 4 | `test_filter_nonexistent_industry_returns_empty` | SpaceTech → [] |
| 5 | `test_search_matches_description` | Substring in description → match |
| 6 | `test_search_matches_company_name` | Substring in name → match |
| 7 | `test_search_case_insensitive` | PAYMENTS matches "payments" |
| 8 | `test_search_no_match_returns_empty` | No match → [] |
| 9 | `test_filter_and_search_combined` | `?industry=&q=` combined narrowing |
| 10 | `test_search_with_percent_wildcard_no_error` | `%25` → no SQL error (FILTER-2) |
| 11 | `test_search_with_underscore_no_error` | `a_b` escaped → no false matches |

## Verification

```
44/44 tests passed (zero regressions)
```

## Requirements Satisfied

| Req | How |
|-----|-----|
| FILTER-01 | `func.lower()` case-insensitive industry match |
| FILTER-02 | `.ilike()` OR on name + description |
| FILTER-03 | Truthy `if industry:` rejects empty string |
| FILTER-04 | `%` and `_` escaped with backslash before LIKE |
