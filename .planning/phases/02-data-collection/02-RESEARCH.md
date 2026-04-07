# Phase 2: Data Collection — Research

**Researched:** 2026-04-07  
**Domain:** YC JSON API scraping, SQLite upsert, standalone Python script  
**Confidence:** HIGH — YC API probed live; all field names and pagination behaviour verified against real responses

---

## Summary

Phase 2 delivers `scraper/yc_scraper.py`: a standalone script that fetches paginated company records from `api.ycombinator.com/v0.1/companies`, applies a description fallback chain, and upserts each company into the existing SQLite database — all without importing anything from `app/` or `agent/`.

**Critical finding:** The YC API has **no `shortDescription` field**. REQUIREMENTS.md COLL-03 lists it in the fallback chain, but it does not exist in the response. The actual available description fields are `longDescription` and `oneLiner`. The effective fallback chain is `longDescription → oneLiner → "{name} (no description available)"`.

**Primary recommendation:** Use `sqlite3` (stdlib, no SQLModel) for DB writes. Build the absolute `_DB_PATH` the same way `app/database.py` does — `Path(__file__).resolve().parent.parent / "data" / "companies.db"`. Use SELECT + INSERT/UPDATE pattern for upsert (no UNIQUE constraint on `company_name` exists). Collect 2 pages (50 companies) — enough for Phase 3 AI analysis without over-spending on OpenAI.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| COLL-01 | Fetch ≥10 company records from `api.ycombinator.com/v0.1/companies` | API confirmed live, 25 records/page, 234 total pages (~5,850 companies). 1 page = 25 records, well above minimum. |
| COLL-02 | Each record contains company name, website URL (if available), description | API fields confirmed: `name` → `company_name`, `website` → `website`, description via fallback chain → `description` |
| COLL-03 | Fallback chain for missing descriptions | `longDescription` and `oneLiner` exist. `shortDescription` does NOT exist. Chain: `longDescription → oneLiner → "{name} (no description available)"` |
| COLL-04 | Idempotent — re-run produces no duplicates | No UNIQUE constraint on `company_name`; use SELECT + conditional INSERT/UPDATE with `sqlite3` |
</phase_requirements>

---

## 1. API Response Shape

**Source:** Live probe of `https://api.ycombinator.com/v0.1/companies` (2026-04-07, HTTP 200 confirmed)

### Top-Level Response Keys

```json
{
  "companies": [ ... ],
  "nextPage": "https://api.ycombinator.com/v0.1/companies?page=2",
  "page": 1,
  "totalPages": 234
}
```

| Key | Type | Notes |
|-----|------|-------|
| `companies` | array | 25 records per page |
| `nextPage` | string \| null | Full URL for next page; `null` on last page |
| `page` | int | Current page number |
| `totalPages` | int | 234 total (≈5,850 companies as of 2026-04-07) |

### Per-Company Record Keys (all confirmed live)

```json
{
  "id": 31561,
  "name": "Maquoketa Research",
  "slug": "maquoketa-research",
  "website": "https://www.maquoketa.net",
  "smallLogoUrl": "https://...",
  "oneLiner": "Intelligent one-way attack drones",
  "longDescription": "",
  "teamSize": 5,
  "url": "https://www.ycombinator.com/companies/maquoketa-research",
  "batch": "P26",
  "tags": ["Artificial Intelligence", "Hardware"],
  "status": "Active",
  "industries": ["Industrials", "Defense"],
  "regions": ["United States of America"],
  "locations": ["Elk Grove Village, IL 60007, USA"],
  "badges": ["highlightLatinx"]
}
```

### Field Mapping to `Company` Schema

| YC API Field | Company Column | Notes |
|-------------|----------------|-------|
| `name` | `company_name` | Always present, non-empty |
| `website` | `website` | Present on most; may be `None` or `""` for some |
| `longDescription` | `description` (primary) | Often empty string `""` — treat as missing |
| `oneLiner` | `description` (fallback) | Present on all observed records; rarely empty |
| *(none)* | `description` (final fallback) | `"{name} (no description available)"` |

### ⚠️ Critical: `shortDescription` Does NOT Exist

Confirmed by live API probe — the per-company object has **no `shortDescription` key**. REQUIREMENTS.md mentions it in COLL-03, but it is absent from the API. The copilot-instructions.md fallback chain also lists it, but since it doesn't exist, it is a no-op.

**Effective fallback chain:**
```python
description = (
    company.get("longDescription")          # "" → falsy
    or company.get("oneLiner")              # always present
    or f"{company['name']} (no description available)"
)
```

### Description Field Coverage (page 1 sample, 25 companies)

| Field | Empty/Missing | Non-empty |
|-------|---------------|-----------|
| `longDescription` | 2/25 (8%) | 23/25 |
| `oneLiner` | 0/25 | 25/25 |

`oneLiner` is effectively always present — the final name-only placeholder will rarely trigger in practice.

---

## 2. Upsert Strategy

**Constraint:** `app/models.py` defines `company_name: str` with no `unique=True`. No UNIQUE constraint exists on the `company_name` column in SQLite, so `INSERT OR REPLACE` and `ON CONFLICT` clauses cannot be used cleanly.

**Chosen pattern:** SELECT → conditional INSERT or UPDATE using `sqlite3` stdlib.

```python
import sqlite3
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "companies.db"

def _upsert_company(conn: sqlite3.Connection, name: str, description: str, website: str | None) -> None:
    cursor = conn.execute(
        "SELECT id FROM company WHERE company_name = ?", (name,)
    )
    row = cursor.fetchone()
    if row:
        # Update scraped fields only — preserve AI fields (industry, business_model, etc.)
        conn.execute(
            "UPDATE company SET description = ?, website = ? WHERE company_name = ?",
            (description, website, name),
        )
    else:
        conn.execute(
            "INSERT INTO company (company_name, description, website) VALUES (?, ?, ?)",
            (name, description, website),
        )
    conn.commit()
```

**Why not SQLModel's `Session.merge()`?**  
`Session.merge()` requires importing `Company` from `app/models.py`, which violates the import boundary rule.

**Why not `INSERT OR REPLACE`?**  
`INSERT OR REPLACE` deletes the old row and inserts a new one, assigning a new `id` and wiping AI-generated fields (`industry`, `business_model`, etc.). Running the scraper after Phase 3 would destroy all AI analysis data.

**Why not `ON CONFLICT(company_name) DO UPDATE SET`?**  
Requires a UNIQUE constraint on `company_name`. The existing schema has none, and altering the schema is out of scope for Phase 2.

**The SELECT + conditional approach:**
- Zero raw schema changes needed
- Preserves AI fields on re-run
- Idempotent (satisfies COLL-04)
- No SQLModel import required

---

## 3. Import Architecture — Scraper is Fully Standalone

**Rule (copilot-instructions.md, enforced):** `scraper/` imports nothing from `app/` or `agent/`.

### What the scraper builds itself:

```python
# scraper/yc_scraper.py — top of file, no app/ imports

import sqlite3
import time
import logging
from pathlib import Path

import requests

# Mirror app/database.py's path resolution — same absolute DB path
_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "companies.db"
_API_BASE = "https://api.ycombinator.com/v0.1/companies"
_DELAY_SECONDS = 0.5
```

The scraper does NOT import:
- `app.database` (engine, get_db)  
- `app.models` (Company)  
- `app.config` (Settings)  
- `agent.*`

The scraper DOES use:
- `requests` — HTTP (already in requirements.txt)
- `sqlite3` — stdlib, zero install
- `pathlib.Path` — stdlib, absolute path resolution
- `time.sleep` — stdlib, polite delay
- `logging` — stdlib, per-company error isolation

### DB table guaranteed to exist

Phase 1 creates `data/companies.db` and the `company` table on first import of `app.database`. The scraper relies on this existing. For defensive safety, the scraper can call `CREATE TABLE IF NOT EXISTS` at startup — this is idempotent and works even if the table was already created by Phase 1.

---

## 4. Description Fallback Chain

**Python implementation:**

```python
def _get_description(company: dict) -> str:
    """
    Return the best available description for a company.
    
    Fallback chain (per COLL-03 + live API verification):
      1. longDescription  — richest; often empty string
      2. oneLiner         — always present in practice
      3. name-only placeholder — last resort
    
    NOTE: 'shortDescription' does NOT exist in the YC API response.
    """
    return (
        company.get("longDescription", "").strip()
        or company.get("oneLiner", "").strip()
        or f"{company['name']} (no description available)"
    )
```

**Key details:**
- Use `.strip()` before falsy check — whitespace-only strings are treated as missing
- `or` short-circuits correctly: first truthy value wins
- The final fallback uses an f-string so the company name is always visible in the DB
- This is a pure function — easy to unit-test without any DB or HTTP

---

## 5. Test Strategy — Offline with Mock Fixtures

**Approach:** `unittest.mock.patch` on `requests.get` with a hand-crafted fixture. No live API calls in tests.

### Fixture Design

```python
# tests/fixtures/yc_api_page1.json  (or inline dict in test file)
FIXTURE_PAGE_1 = {
    "companies": [
        {
            "id": 1, "name": "Acme Corp", "website": "https://acme.com",
            "longDescription": "We build rockets.", "oneLiner": "Rockets for everyone",
            "batch": "S23", "tags": [], "status": "Active",
            "industries": [], "regions": [], "locations": [], "badges": [],
            "slug": "acme-corp", "smallLogoUrl": "", "teamSize": 10,
            "url": "https://ycombinator.com/companies/acme-corp"
        },
        {
            "id": 2, "name": "EmptyDesc Co", "website": None,
            "longDescription": "", "oneLiner": "A startup",
            "batch": "W24", "tags": [], "status": "Active",
            "industries": [], "regions": [], "locations": [], "badges": [],
            "slug": "emptydesc-co", "smallLogoUrl": "", "teamSize": 3,
            "url": "https://ycombinator.com/companies/emptydesc-co"
        },
        {
            "id": 3, "name": "NoDesc Inc", "website": "https://nodesc.io",
            "longDescription": "", "oneLiner": "",
            "batch": "S24", "tags": [], "status": "Active",
            "industries": [], "regions": [], "locations": [], "badges": [],
            "slug": "nodesc-inc", "smallLogoUrl": "", "teamSize": 2,
            "url": "https://ycombinator.com/companies/nodesc-inc"
        },
    ],
    "nextPage": None,
    "page": 1,
    "totalPages": 1
}
```

### Test Cases

| Test | What it verifies | Req |
|------|-----------------|-----|
| `test_fallback_long_description` | `longDescription` used when non-empty | COLL-03 |
| `test_fallback_one_liner` | `oneLiner` used when `longDescription` is empty | COLL-03 |
| `test_fallback_name_placeholder` | placeholder used when both are empty | COLL-03 |
| `test_scraper_inserts_records` | mock API → DB contains ≥1 record with name+desc+website | COLL-01, COLL-02 |
| `test_scraper_idempotent` | running scraper twice → same row count, no duplicates | COLL-04 |
| `test_upsert_preserves_ai_fields` | re-run after fake AI data → `industry` not wiped | COLL-04 edge case |

### Patching Pattern

```python
from unittest.mock import patch, MagicMock
import pytest

def test_scraper_inserts_records(tmp_path):
    """Scraper writes records to an in-memory or tmp SQLite DB via mock API."""
    mock_response = MagicMock()
    mock_response.json.return_value = FIXTURE_PAGE_1
    mock_response.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_response) as mock_get:
        # Call scraper's main function (or fetch_and_store helper)
        from scraper.yc_scraper import fetch_companies
        records = fetch_companies(db_path=tmp_path / "test.db")

    assert len(records) >= 1
    assert mock_get.called
```

**Key testing decisions:**
- Use `tmp_path` pytest fixture for a throwaway DB — never touch real `data/companies.db` in tests
- Test `_get_description()` as a pure function — no mocking needed for fallback chain tests
- Test upsert logic with an in-memory or `tmp_path` SQLite to avoid test interference

---

## 6. Data Volume Decision

**Requirement:** COLL-01 requires ≥10 records.  
**Reality:** 1 page = 25 records. 2 pages = 50 records. Total available: ~5,850.

**Recommendation: Collect 2 pages (50 companies) by default.**

| Option | Pages | Companies | Phase 3 Cost Estimate | Verdict |
|--------|-------|-----------|----------------------|---------|
| Minimum | 1 | 25 | ~$0.002 (gpt-4o-mini) | ✓ passes COLL-01, reasonable |
| **Recommended** | **2** | **50** | **~$0.004** | **✓ good diversity for AI analysis** |
| Generous | 4 | 100 | ~$0.008 | ✓ but slower scraper run |
| Excessive | 234 | 5,850 | ~$0.47 | ✗ overkill for Phase 3 demo |

**Implementation:** Hard-code `MAX_PAGES = 2` as a module-level constant with a comment explaining the choice. Easy to increase for production.

```python
# Collect 2 pages (50 companies) — sufficient for Phase 3 AI analysis demo.
# Each page = 25 records. Increase MAX_PAGES to collect more.
MAX_PAGES = 2
```

---

## 7. Rate Limiting — Polite Crawling

**Spec (ROADMAP.md):** 0.5s delay between paginated requests.

**Implementation:**

```python
import time

def _fetch_page(url: str, session: requests.Session) -> dict:
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()

def fetch_all_pages(max_pages: int = MAX_PAGES) -> list[dict]:
    companies = []
    url = _API_BASE
    session = requests.Session()
    
    for page_num in range(1, max_pages + 1):
        data = _fetch_page(url, session)
        companies.extend(data["companies"])
        logging.info("Fetched page %d/%d (%d companies so far)", page_num, max_pages, len(companies))
        
        next_url = data.get("nextPage")
        if not next_url:
            break
        
        if page_num < max_pages:
            time.sleep(0.5)   # polite delay — don't hammer YC API
        
        url = next_url
    
    return companies
```

**Notes:**
- `requests.Session()` enables connection reuse (TCP keep-alive) — faster than re-connecting per page
- `timeout=15` prevents hanging indefinitely on slow responses
- Delay only inserted between pages (not after the last page)
- `raise_for_status()` converts 4xx/5xx HTTP responses into exceptions — triggers per-company error handling

---

## Architecture Patterns

### Recommended File Structure

```
scraper/
├── __init__.py          # already exists (Phase 1)
└── yc_scraper.py        # new — entire scraper in one file
```

Single-file scraper is correct at this scope. No sub-modules needed.

### Script Entry Point Pattern

```python
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
```

`main()` is a callable function (not just module-level code) so tests can call `scraper.yc_scraper.main()` or individual helpers without running the full pipeline.

### Per-Company Error Isolation

```python
for company in companies:
    try:
        name = company["name"]
        website = company.get("website") or None
        description = _get_description(company)
        _upsert_company(conn, name, description, website)
    except Exception as exc:
        logging.error("Failed to store company %r: %s", company.get("name", "?"), exc)
        # continue — one failure must NOT abort the batch
```

`or None` normalizes empty strings for `website` (API returns `""` for some companies, DB column is `Optional[str]`).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP client | Custom urllib wrapper | `requests.Session` | Already in requirements.txt; connection pooling built-in |
| JSON parsing | Manual string parsing | `resp.json()` | `requests` handles encoding, Content-Type automatically |
| DB path resolution | String concatenation | `Path(__file__).resolve()` | Established pattern from Phase 1; CWD-independent |
| Rate limiting | asyncio sleep | `time.sleep(0.5)` | Sync script; asyncio adds complexity without benefit |

---

## Common Pitfalls

### Pitfall 1: Using `longDescription` as a string check without `.strip()`
**What goes wrong:** `" "` (whitespace-only) is truthy in Python — stored as the description instead of falling through to `oneLiner`.  
**Prevention:** Always `.strip()` before the falsy check: `company.get("longDescription", "").strip() or ...`

### Pitfall 2: Relative DB path breaks when run from non-root directory
**What goes wrong:** `sqlite:///./data/companies.db` resolves differently from `scraper/` vs project root.  
**Prevention:** Always use `Path(__file__).resolve().parent.parent / "data" / "companies.db"` — mirrors `app/database.py`.

### Pitfall 3: `INSERT OR REPLACE` wipes AI fields on re-run
**What goes wrong:** After Phase 3 populates `industry`/`business_model`/etc., re-running the scraper with `INSERT OR REPLACE` deletes the old row and inserts a fresh one — AI fields are NULL again.  
**Prevention:** SELECT + conditional UPDATE that only touches `description` and `website`. Never replace the row.

### Pitfall 4: `shortDescription` KeyError
**What goes wrong:** Code calls `company["shortDescription"]` — raises `KeyError` on every record (field doesn't exist).  
**Prevention:** Use `company.get("shortDescription", "")` — or better yet, don't reference it at all (it doesn't exist in the API).

### Pitfall 5: `website` stored as empty string instead of `None`
**What goes wrong:** `""` stored in `website` column when API returns empty; downstream code checks `if company.website:` and gets `False` for empty string but `None` is more semantically correct.  
**Prevention:** `website = company.get("website") or None` — converts empty string to `None`.

### Pitfall 6: No `raise_for_status()` call
**What goes wrong:** API returns HTTP 429/500; `requests` doesn't auto-raise — code happily tries to parse an error response as JSON, getting a `JSONDecodeError` with no useful message.  
**Prevention:** Always call `resp.raise_for_status()` immediately after `requests.get(...)`.

---

## Environment Availability

> Step 2.6 audit (probed 2026-04-07)

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.13 | Scraper runtime | ✓ | 3.13.9 | — |
| requests | HTTP fetching | ✓ | 2.32.3 (pinned) | — |
| sqlite3 | DB writes | ✓ | stdlib (bundled) | — |
| pytest | Test suite | ✓ | 9.0.2 (pinned) | — |
| `api.ycombinator.com` | Data source | ✓ | Live, HTTP 200 confirmed | — |

**Missing dependencies with no fallback:** None  
**Missing dependencies with fallback:** None  
**Network access required:** Yes — for the scraper itself (`python scraper/yc_scraper.py`). Tests use mocks and require no network.

---

## Code Examples

### Verified API Pagination Loop
```python
# Source: live API probe 2026-04-07
# nextPage is a full URL string like "https://api.ycombinator.com/v0.1/companies?page=2"
# or None on the final page

url = "https://api.ycombinator.com/v0.1/companies"
while url:
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    for company in data["companies"]:
        process(company)
    url = data.get("nextPage")   # None stops the loop
    if url:
        time.sleep(0.5)
```

### Verified Description Fallback
```python
# Handles empty string, whitespace, missing key — all confirmed needed from live data
description = (
    company.get("longDescription", "").strip()
    or company.get("oneLiner", "").strip()
    or f"{company['name']} (no description available)"
)
```

### Verified Upsert (sqlite3)
```python
# No UNIQUE constraint on company_name — SELECT + conditional branch required
cursor = conn.execute("SELECT id FROM company WHERE company_name = ?", (name,))
if cursor.fetchone():
    conn.execute(
        "UPDATE company SET description = ?, website = ? WHERE company_name = ?",
        (description, website, name),
    )
else:
    conn.execute(
        "INSERT INTO company (company_name, description, website) VALUES (?, ?, ?)",
        (name, description, website),
    )
conn.commit()
```

---

## Project Constraints (from copilot-instructions.md)

All directives from `.github/copilot-instructions.md` that apply to Phase 2:

| Directive | Impact on Phase 2 |
|-----------|-------------------|
| `scraper/` imports nothing from `app/` or `agent/` | Use `sqlite3` stdlib, not SQLModel Session. Build `_DB_PATH` via `Path(__file__).resolve()`. |
| Use `requests`, not Playwright | `requests.Session` for all HTTP. No browser automation. |
| Do NOT scrape `ycombinator.com/companies` HTML | Use `api.ycombinator.com/v0.1/companies` exclusively. |
| Pipeline is idempotent — upsert by company_name | SELECT + conditional INSERT/UPDATE; never blind INSERT. |
| Per-company error isolation | Wrap each company in `try/except`; log and continue on failure. |
| Description fallback chain | `longDescription → oneLiner → "{name} (no description available)"` (shortDescription absent from API). |
| 0.5s polite delay between pages | `time.sleep(0.5)` between paginated requests. |
| Tests run with `.venv\Scripts\python -m pytest` | Windows path; no Unix-only test patterns. |

---

## Open Questions

1. **`company_name` uniqueness**  
   - What we know: No UNIQUE constraint on `company_name` in `app/models.py`  
   - What's unclear: Could two YC companies have identical names? Unlikely but possible (e.g., renamed companies).  
   - Recommendation: Use `name` field from API (which is the display name). The SELECT + UPDATE approach handles this correctly regardless — worst case, the second company with the same name updates the first's description.

2. **`website` field normalization**  
   - What we know: Some companies return `""` for website; `Company.website` is `Optional[str]`  
   - What's unclear: Whether `""` or `None` is preferred by Phase 4 API consumers  
   - Recommendation: Store `None` for empty/missing websites (`company.get("website") or None`). This is consistent with `Optional[str]` semantics.

3. **Table existence guarantee**  
   - What we know: Phase 1 creates the table; scraper relies on it existing  
   - What's unclear: What if someone runs `scraper/yc_scraper.py` on a fresh checkout without Phase 1's DB?  
   - Recommendation: Add defensive `CREATE TABLE IF NOT EXISTS` at scraper startup — fully idempotent, zero downside.

---

## Sources

### Primary (HIGH confidence)
- Live API probe: `api.ycombinator.com/v0.1/companies` — all field names, pagination structure, data types verified 2026-04-07
- `app/models.py` — Company schema (column names, types, constraints)
- `app/database.py` — DB path resolution pattern
- `.github/copilot-instructions.md` — import boundary rules, API URL, fallback chain spec

### Secondary (MEDIUM confidence)
- `requirements.txt` — confirmed `requests==2.32.3` already installed
- Phase 1 summaries — confirmed DB and table exist after Phase 1

### Tertiary (LOW confidence)
- None — all findings backed by live verification or official project files

---

## Metadata

**Confidence breakdown:**
- API response shape: HIGH — live probe confirmed all field names, pagination, and data types
- Upsert strategy: HIGH — sqlite3 stdlib is definitive; SQLModel constraint absence verified in models.py
- Import architecture: HIGH — copilot-instructions.md is explicit and enforced
- Fallback chain: HIGH — `shortDescription` absence confirmed by live probe of 25 records
- Test strategy: HIGH — unittest.mock.patch is standard Python stdlib
- Data volume: MEDIUM — "50 companies" is a recommendation; actual best value depends on Phase 3 cost tolerance
- Rate limiting: HIGH — 0.5s specified in ROADMAP.md; `time.sleep` is correct for sync script

**Research date:** 2026-04-07  
**Valid until:** 2026-06-07 (API shape may evolve; re-probe if > 60 days)

---

## RESEARCH COMPLETE

**Summary:** YC API live-verified (no `shortDescription` — fallback chain is `longDescription → oneLiner → placeholder`); scraper uses `sqlite3` stdlib for DB writes (import boundary prohibits SQLModel); upsert pattern is SELECT + conditional INSERT/UPDATE (no UNIQUE constraint); collect 2 pages (50 companies); test with `unittest.mock.patch` on `requests.get` using in-memory fixtures.
