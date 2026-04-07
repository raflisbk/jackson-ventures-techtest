# Phase 4: REST API — Research

**Researched:** 2025-07-25
**Domain:** FastAPI + SQLModel REST API, Pydantic v2 response models
**Confidence:** HIGH — all patterns verified by live execution against project DB

---

## Summary

Phase 4 adds two GET endpoints (`/companies` and `/companies/{id}`) on top of the existing
SQLite database populated in Phases 2 and 3. The project already has `app/models.py`
(Company SQLModel table), `app/database.py` (engine + `get_db()` + `create_db_and_tables()`),
and `app/config.py` — but **no `app/main.py` and no `app/routers/` directory** exist yet.

All four requirements are straightforward with the installed library versions:
FastAPI 0.135.3 supports the `@asynccontextmanager` lifespan pattern natively;
Pydantic v2 patterns (`model_config = ConfigDict(from_attributes=True)`) are already used
throughout the project; and `Company` (SQLModel table class) can be used **directly** as
`response_model=` in route decorators — no separate response schema is needed.

Every pattern in this document was **verified by live execution** against `data/companies.db`
(50 companies, AI fields currently NULL).

**Primary recommendation:** Create `app/main.py` with the lifespan app + an `app/routers/companies.py`
router. Two files, four tests, done.

---

<phase_requirements>
## Phase Requirements

| ID     | Description                                                                                      | Research Support |
|--------|--------------------------------------------------------------------------------------------------|------------------|
| API-01 | `GET /companies` returns all companies with all AI-generated fields as a JSON array              | Verified: `session.exec(select(Company)).all()` returns list; `response_model=list[Company]` serialises NULL fields as `null` |
| API-02 | `GET /companies/{id}` returns full details; 404 if not found                                     | Verified: `session.get(Company, id)` returns `None` for missing IDs; `HTTPException(status_code=404)` works correctly |
| API-03 | FastAPI lifespan context manager (`@asynccontextmanager` + `lifespan=`) not deprecated `@app.on_event` | Verified: FastAPI 0.135.3 supports and encourages this pattern |
| API-04 | Response models use Pydantic v2 `model_config = ConfigDict(from_attributes=True)`, not `orm_mode = True` | Verified: Company already uses SQLModel which is Pydantic v2-based; no additional config needed |
</phase_requirements>

---

## Standard Stack

### Core (already installed — verified by live checks)

| Library        | Installed Version | Purpose                                  | Why Standard                              |
|----------------|-------------------|------------------------------------------|-------------------------------------------|
| fastapi        | **0.135.3**       | HTTP framework, routing, OpenAPI gen     | Project requirement; async-first          |
| sqlmodel       | **0.0.38**        | ORM + Pydantic model in one class        | Already used for Company table            |
| pydantic       | **2.12.5**        | Validation, serialisation, response models | SQLModel v2 backbone; already in project |
| uvicorn        | check below       | ASGI server to run the FastAPI app       | De-facto standard for FastAPI             |
| httpx          | **0.28.1**        | Async HTTP client — TestClient dependency | Already installed                         |
| starlette      | bundled with FA   | TestClient lives here                    | `from starlette.testclient import TestClient` — verified working |

```bash
# Verify uvicorn is present (needed to run the server)
.venv\Scripts\python -c "import uvicorn; print(uvicorn.__version__)"
# If missing: .venv\Scripts\pip install uvicorn
```

### Nothing new to install
All required libraries are already in the virtual environment. No `pip install` step is needed for this phase.

---

## Architecture Patterns

### Recommended Project Structure

```
app/
├── main.py              # FastAPI app instance + lifespan (CREATE THIS)
├── routers/
│   ├── __init__.py      # Empty (CREATE THIS)
│   └── companies.py     # GET /companies, GET /companies/{id} (CREATE THIS)
├── models.py            # Company SQLModel table ← already exists
├── database.py          # engine, get_db(), create_db_and_tables() ← already exists
└── config.py            # Settings ← already exists
tests/
└── test_api.py          # FastAPI TestClient tests (CREATE THIS)
```

**Why a separate `routers/companies.py` instead of putting routes in `main.py`?**
The project's `models.py` comment already references `app/routers/companies.py`
(`"Imported by database.py, scripts/run_pipeline.py, and app/routers/companies.py"`).
Keeping routes in a router module also matches the pattern used in previous phases
and is the FastAPI community standard for any non-trivial app.

---

### Pattern 1: FastAPI Lifespan Context Manager (API-03)

**What:** Replace deprecated `@app.on_event("startup")` with `@asynccontextmanager` lifespan.
**When to use:** Always for startup/shutdown logic in FastAPI 0.93+.

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import create_db_and_tables
from app.routers import companies

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables on startup (no-op if they already exist)."""
    create_db_and_tables()
    yield
    # (optional teardown here)

app = FastAPI(
    title="Jackson Ventures Company API",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(companies.router)
```

**Verified:** FastAPI 0.135.3 accepts this pattern without warnings.

---

### Pattern 2: Router Definition with `Depends(get_db)` (API-01, API-02)

```python
# app/routers/companies.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.database import get_db
from app.models import Company

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("/", response_model=list[Company])
def get_companies(db: Session = Depends(get_db)):
    """Return all companies. Empty list if DB has no rows."""
    return db.exec(select(Company)).all()


@router.get("/{company_id}", response_model=Company)
def get_company(company_id: int, db: Session = Depends(get_db)):
    """Return a single company by integer ID, or 404."""
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company
```

**Key verified facts:**
- Routes are **`def`** (not `async def`) — `get_db()` is a sync generator using `with Session(engine) as session: yield session`; FastAPI handles sync dependencies correctly in its threadpool.
- `db: Session = Depends(get_db)` — exact annotation form that FastAPI resolves.
- `session.get(Company, company_id)` returns **`None`** (not raise) when ID doesn't exist → safe to check with `if not company`.
- `session.exec(select(Company)).all()` returns a Python list, which serialises to a JSON array.

---

### Pattern 3: Pydantic v2 Response Model (API-04)

```python
# Company is ALREADY a valid response_model — no separate schema class needed.
# SQLModel table classes inherit from SQLModel which uses Pydantic v2 internally.
# FastAPI 0.135.3 + SQLModel 0.0.38 accept `response_model=Company` directly.
```

**Verified live:**
```
Keys in response: ['company_name', 'description', 'industry', 'summary',
                   'id', 'website', 'business_model', 'use_case']
```

All 8 fields are included. NULL AI fields come back as JSON `null` — not omitted, not errored.

**When you DO need a separate schema:**  Only if you want to hide fields (e.g., exclude internal
fields). Not needed here — all Company fields should be visible in the API response.

**Pydantic v2 note (API-04):** `orm_mode = True` is the Pydantic v1 pattern.
SQLModel 0.0.38 uses Pydantic v2 internally; its `SQLModel` base already configures
`model_config = ConfigDict(from_attributes=True)` equivalent. If you create a
*separate* Pydantic response schema (not a SQLModel table), use:
```python
from pydantic import BaseModel, ConfigDict

class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: Optional[int]
    company_name: str
    # ... etc
```
But again, using `Company` directly as `response_model=Company` is simpler and verified to work.

---

### Pattern 4: HTTP 404 (API-02)

```python
from fastapi import HTTPException

raise HTTPException(status_code=404, detail="Company not found")
```

**Verified:** Returns `{"detail": "Company not found"}` with HTTP 404.

---

### Pattern 5: Automatic 422 for Invalid Path Parameters

FastAPI automatically validates path parameters declared as `int`. If a client sends
`GET /companies/abc`, FastAPI returns HTTP 422 Unprocessable Entity **before the route
function is called** — no custom code needed.

**Verified:** `GET /companies/abc` → 422 automatically.

---

### Anti-Patterns to Avoid

- **`@app.on_event("startup")`:** Deprecated since FastAPI 0.93. Raises deprecation warning in 0.135.3. Use lifespan instead (API-03).
- **`orm_mode = True`:** Pydantic v1 syntax. Will raise a warning/error with Pydantic v2. Use `model_config = ConfigDict(from_attributes=True)` if building a separate schema.
- **`session.exec(select(Company).where(Company.id == id)).first()`** for single-record lookup: Works but is more verbose than `session.get(Company, id)`. Both return `None` for missing records. Prefer `session.get()` for primary key lookups.
- **Shared session state:** `get_db()` creates a new `Session` per request. Never store session at module level or share across requests — the existing `database.py` is correctly written.
- **Relative DB path in `DATABASE_URL`:** Already fixed in `database.py` with absolute path resolution. Do not reintroduce a relative path.

---

## Don't Hand-Roll

| Problem                        | Don't Build                      | Use Instead                                  | Why                                                                |
|-------------------------------|----------------------------------|----------------------------------------------|--------------------------------------------------------------------|
| Request validation             | Manual type-checking in routes   | FastAPI path param type annotation (`int`)   | Auto 422 with clear error message; zero code                      |
| OpenAPI / Swagger docs         | Custom documentation             | FastAPI's built-in (`/docs`, `/redoc`)       | Auto-generated from route + response_model + docstrings           |
| JSON serialisation of ORM obj  | `dict()` + `jsonify()`           | `response_model=Company`                     | FastAPI serialises SQLModel objects natively; handles None fields  |
| Session lifecycle              | Manual `session.close()` calls   | `with Session(engine) as session: yield`     | Context manager guarantees close on error; already in `get_db()`  |
| 404 response body format       | Custom JSON error structure      | `HTTPException(status_code=404, detail=…)`  | FastAPI formats `{"detail": "…"}` consistently with all other errors |

---

## Common Pitfalls

### Pitfall 1: `app/main.py` imports `app/config.py` → `Settings()` requires `OPENAI_API_KEY`

**What goes wrong:** Importing `app.main` in tests triggers `from app.config import settings`
which instantiates `Settings()`, which requires `OPENAI_API_KEY` in the environment.
Tests will fail with `ValidationError` if the key is not set.

**Why it happens:** `app/config.py` creates a module-level singleton: `settings = Settings()`.
Any import of a module that imports `app.config` triggers this at import time.

**How to avoid:** In `tests/test_api.py`, set a fake key before importing the app:
```python
import os
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-used")

from starlette.testclient import TestClient
from app.main import app

client = TestClient(app)
```
Or use a `conftest.py` fixture that patches the env var before any test module is imported.

**Warning signs:** `pydantic.ValidationError: 1 validation error for Settings OPENAI_API_KEY field required` in test output.

---

### Pitfall 2: Router prefix duplication

**What goes wrong:** Defining `prefix="/companies"` on the `APIRouter` AND including it as
`app.include_router(companies.router, prefix="/companies")` results in routes at
`/companies/companies` and `/companies/companies/{id}`.

**How to avoid:** Set prefix in **one place only** — either on `APIRouter(prefix="/companies")`
or on `app.include_router(..., prefix="/companies")`, not both.

**Recommended:** Set `prefix="/companies"` in `companies.router` definition; use
`app.include_router(companies.router)` with no prefix argument in `main.py`.

---

### Pitfall 3: `select(Company)` returns `ScalarResult`, not a list

**What goes wrong:** `db.exec(select(Company))` returns a `ScalarResult` object, not a list.
Assigning it directly to a variable and passing it as the response without `.all()` may
cause serialisation issues.

**How to avoid:** Always call `.all()`:
```python
return db.exec(select(Company)).all()  # returns list[Company]
```

**Verified:** `db.exec(select(Company)).all()` returns a Python `list` of `Company` objects.

---

### Pitfall 4: `Company` table class has `id: Optional[int]` (primary key can be None before insert)

**What goes wrong:** If you try to return a Company object that hasn't been committed to DB yet
(e.g., in a test), `id` will be `None`. The response schema allows this (`Optional[int]`).

**Relevance to this phase:** Not a problem for GET endpoints — any record in the DB
already has an integer `id` assigned by SQLite. Only relevant if Phase 4 is extended
to include POST/PUT.

---

### Pitfall 5: NULL AI fields in the response

**What is observed (verified):** Companies scraped in Phase 2 but not yet processed by
Phase 3 have `industry=None`, `business_model=None`, `summary=None`, `use_case=None`.
These are **correctly serialised as JSON `null`**, not omitted. API-01 says "all AI-generated
fields" — this behaviour is correct.

**No code change needed.** The `response_model=list[Company]` pattern handles this automatically.

---

## Code Examples

### Minimal working app (verified end-to-end)

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import create_db_and_tables
from app.routers import companies

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield

app = FastAPI(
    title="Jackson Ventures Company API",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(companies.router)
```

```python
# app/routers/__init__.py
# (empty)
```

```python
# app/routers/companies.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from app.database import get_db
from app.models import Company

router = APIRouter(prefix="/companies", tags=["companies"])

@router.get("/", response_model=list[Company])
def get_companies(db: Session = Depends(get_db)):
    return db.exec(select(Company)).all()

@router.get("/{company_id}", response_model=Company)
def get_company(company_id: int, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company
```

### Test file (verified working)

```python
# tests/test_api.py
import os
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-used")  # must be before app import

import pytest
from starlette.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_get_companies_returns_list():
    """API-01: GET /companies returns a JSON array."""
    r = client.get("/companies")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)


def test_get_companies_has_all_fields():
    """API-01: Each company object contains all AI-generated fields (may be null)."""
    r = client.get("/companies")
    assert r.status_code == 200
    companies = r.json()
    if companies:
        expected_fields = {
            "id", "company_name", "description", "website",
            "industry", "business_model", "summary", "use_case",
        }
        assert expected_fields.issubset(set(companies[0].keys()))


def test_get_company_by_id():
    """API-02: GET /companies/{id} returns 200 for a valid ID."""
    # Get first company's ID dynamically
    all_companies = client.get("/companies").json()
    if all_companies:
        first_id = all_companies[0]["id"]
        r = client.get(f"/companies/{first_id}")
        assert r.status_code == 200
        assert r.json()["id"] == first_id


def test_get_company_404():
    """API-02: GET /companies/{id} returns 404 for non-existent ID."""
    r = client.get("/companies/999999")
    assert r.status_code == 404
    assert r.json()["detail"] == "Company not found"


def test_get_company_invalid_id_type():
    """FastAPI auto-validates path param type; non-integer returns 422."""
    r = client.get("/companies/not-an-integer")
    assert r.status_code == 422
```

### Running the server locally

```bash
# From project root
.venv\Scripts\python -m uvicorn app.main:app --reload
# Docs available at: http://localhost:8000/docs
# Redoc available at: http://localhost:8000/redoc
```

---

## File Structure: Exact Files to Create / Modify

| File                          | Action  | What it contains                                             |
|-------------------------------|---------|--------------------------------------------------------------|
| `app/main.py`                 | CREATE  | FastAPI app + lifespan + `include_router(companies.router)` |
| `app/routers/__init__.py`     | CREATE  | Empty file (makes `routers` a Python package)                |
| `app/routers/companies.py`    | CREATE  | `GET /companies` and `GET /companies/{id}` routes            |
| `tests/test_api.py`           | CREATE  | 5 test cases covering API-01, API-02, type validation        |
| `app/models.py`               | NO CHANGE | Already correct; `Company` works as response_model directly |
| `app/database.py`             | NO CHANGE | Already has `get_db()`, `create_db_and_tables()`, `engine` |
| `app/config.py`               | NO CHANGE | Settings singleton already using Pydantic v2 patterns       |

---

## Edge Cases

| Edge Case                            | Behaviour (verified)                                                       | Handling                          |
|--------------------------------------|----------------------------------------------------------------------------|-----------------------------------|
| Empty DB (no rows)                   | `GET /companies` returns `[]` — empty JSON array, HTTP 200                | No special code needed            |
| NULL AI fields                       | Appear as `null` in JSON response — not omitted, not errored               | No special code needed            |
| ID that doesn't exist                | `session.get(Company, 9999)` returns `None` → raise 404                   | `if not company: raise HTTPException(404)` |
| Non-integer path param (`/abc`)      | FastAPI auto-validates → HTTP 422 Unprocessable Entity                     | No custom code needed             |
| Negative integer ID (`/-1`)          | `session.get(Company, -1)` returns `None` → 404                           | Same 404 path                     |
| Float-like integer (`/1.0`)          | FastAPI rejects at validation layer → 422                                  | No custom code needed             |
| OPENAI_API_KEY missing in test env   | `Settings()` raises `ValidationError` at import time                      | `os.environ.setdefault(...)` before import |

---

## Environment Availability

| Dependency     | Required By           | Available | Version  | Fallback   |
|----------------|-----------------------|-----------|----------|------------|
| fastapi        | All routes            | ✓         | 0.135.3  | —          |
| sqlmodel       | DB queries            | ✓         | 0.0.38   | —          |
| pydantic       | Response models       | ✓         | 2.12.5   | —          |
| httpx          | TestClient            | ✓         | 0.28.1   | —          |
| starlette      | TestClient            | ✓         | bundled  | —          |
| uvicorn        | Running the server    | verify    | —        | hypercorn  |
| data/companies.db | GET /companies data | ✓        | 50 rows  | Empty list |

**Note:** `uvicorn` is needed to run the server manually (not for tests). Run
`.venv\Scripts\python -c "import uvicorn; print(uvicorn.__version__)"` to verify.
If missing: `.venv\Scripts\pip install uvicorn[standard]`.

---

## State of the Art

| Old Approach                          | Current Approach                        | When Changed    | Impact                                      |
|--------------------------------------|-----------------------------------------|-----------------|---------------------------------------------|
| `@app.on_event("startup")`           | `@asynccontextmanager` lifespan         | FastAPI 0.93    | Old form still works but shows deprecation warning; API-03 requires new form |
| `class Config: orm_mode = True`      | `model_config = ConfigDict(from_attributes=True)` | Pydantic v2  | Old form raises `PydanticUserError` in v2; API-04 requires new form |
| `from fastapi.testclient import TestClient` | `from starlette.testclient import TestClient` | Starlette refactor | Both work in current version; starlette import is the canonical source |

---

## Open Questions

1. **Is uvicorn installed?**
   - What we know: httpx and starlette are present; no test for uvicorn was run.
   - What's unclear: Whether `uvicorn` is in the venv (tests don't need it, only manual `uvicorn app.main:app --reload` does).
   - Recommendation: Planner should add a Wave 0 check: `.venv\Scripts\python -c "import uvicorn"`.

2. **Should `/companies` redirect to `/companies/` or are they the same?**
   - What we know: FastAPI's `APIRouter(prefix="/companies")` + `@router.get("/")` creates the route at `/companies/`. FastAPI by default redirects `/companies` → `/companies/` (307).
   - Recommendation: This is acceptable for an API. Alternatively, add `@router.get("")` (no trailing slash) if exact path control is needed. Not a blocker.

3. **Should AI-null records be filtered out of `GET /companies`?**
   - What we know: API-01 says "returns all companies with all AI-generated fields" — the word "all" refers to fields, not a filter condition.
   - Recommendation: Return all 50 rows regardless of NULL fields. This is consistent with API-01 and the verified behaviour.

---

## Sources

### Primary (HIGH confidence — verified by live execution)
- Live REPL tests against `data/companies.db` (50 companies) — all patterns run and output inspected
- `app/models.py`, `app/database.py`, `app/config.py` — read directly from project
- FastAPI 0.135.3 installed in `.venv` — `import fastapi; print(fastapi.__version__)`
- SQLModel 0.0.38 installed in `.venv` — `import sqlmodel; print(sqlmodel.__version__)`
- Pydantic 2.12.5 installed in `.venv`
- httpx 0.28.1 installed in `.venv`

### Secondary (MEDIUM confidence)
- FastAPI docs on lifespan: https://fastapi.tiangolo.com/advanced/events/#lifespan
- SQLModel docs on session: https://sqlmodel.tiangolo.com/tutorial/fastapi/session-with-dependency/

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified by live import
- Architecture patterns: HIGH — full end-to-end test executed (50 companies, 404, 422, NULL fields)
- Pitfalls: HIGH — OPENAI_API_KEY pitfall reproduced and workaround confirmed; others deduced from verified code paths

**Research date:** 2025-07-25
**Valid until:** 2025-08-25 (FastAPI/SQLModel are stable; Pydantic v2 patterns are locked in)
