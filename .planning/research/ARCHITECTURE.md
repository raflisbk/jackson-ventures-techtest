# Architecture Patterns

**Project:** AI Company Research Agent — v1.1 Integration Architecture
**Domain:** AI-powered data pipeline + REST API + MCP server (Python)
**Researched:** 2026-04-07
**Version:** v1.1 (adding 5 features to existing v1.0 architecture)
**Confidence:** HIGH — all patterns verified against live code and installed packages

---

## v1.1 Overview: What Changes, What Stays

v1.1 adds **5 features** to a working v1.0 foundation. The core two-entrypoint design is
**preserved and extended** — v1.1 adds a third entrypoint (MCP server) without coupling it
to the existing two.

**Existing entrypoints (unchanged in structure):**
1. `scripts/run_pipeline.py` — CLI batch pipeline (scrape → analyze → store)
2. `uvicorn app.main:app` — REST API server (read-only, serves populated DB)

**New v1.1 entrypoint:**
3. `python mcp_server/server.py` — MCP server (AI agent interface, reads same DB)

**Modified files (v1.1 touch list):**
- `app/models.py` — add `description_hash` column
- `app/routers/companies.py` — add filter/search query params to GET /companies
- `app/main.py` — mount `frontend/` as static files
- `agent/analyzer.py` — use `description_hash` to skip re-analysis
- `requirements.txt` — add `fastmcp`

**New files (v1.1 additions):**
- `mcp_server/server.py` — standalone MCP server process
- `mcp_server/__init__.py` — package marker
- `frontend/index.html` — simple static UI
- `frontend/app.js` — fetch /companies and render
- `frontend/style.css` — minimal CSS
- `scripts/migrate_add_hash.py` — one-time migration script (ALTER TABLE)
- `.github/workflows/code-review.yml` — GitHub Actions agentic review trigger
- `scripts/ai_code_review.py` — the Python agent that runs in CI

---

## Full v1.1 Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│  PIPELINE MODE  (scripts/run_pipeline.py)                            │
│                                                                      │
│  YC JSON API ──► scraper/yc_scraper.py ──► agent/analyzer.py ──►   │
│  (HTTP/JSON)      upsert by name          OpenAI + hash check        │
│                                                 │                    │
│                                        skip if hash unchanged        │
└────────────────────────────────────────────────┬─────────────────────┘
                                                  │
                                    data/companies.db  (shared SQLite file)
                                                  │
         ┌────────────────────────────────────────┼──────────────────────────┐
         │                                         │                          │
         ▼                                         ▼                          ▼
┌─────────────────────┐               ┌────────────────────────┐  ┌──────────────────────┐
│  SERVER MODE        │               │  MCP SERVER MODE       │  │  GITHUB ACTIONS      │
│  uvicorn app.main   │               │  python mcp_server/    │  │  .github/workflows/  │
│                     │               │  server.py             │  │  code-review.yml     │
│  GET /companies     │               │                        │  │                      │
│  ?industry=         │               │  @mcp.tool             │  │  on: pull_request    │
│  ?business_model=   │               │  get_companies()       │  │  → scripts/          │
│  ?search=           │               │  get_company_by_id()   │  │    ai_code_review.py │
│                     │               │  search_companies()    │  │  → post PR comment   │
│  GET /companies/id  │               │                        │  └──────────────────────┘
│                     │               │  Transport: stdio      │
│  GET /ui (static)   │               │  (Claude Desktop)      │
│  ← frontend/        │               │  or streamable-http    │
└─────────────────────┘               └────────────────────────┘
```

---

## Updated Folder Structure (v1.1)

```
project-root/
│
├── app/                              # FastAPI application — MODIFIED
│   ├── __init__.py
│   ├── main.py                       # + mount frontend/ StaticFiles at /ui
│   ├── database.py                   # UNCHANGED
│   ├── models.py                     # + description_hash: Optional[str]
│   ├── config.py                     # UNCHANGED
│   └── routers/
│       └── companies.py              # + filter/search query params
│
├── mcp_server/                       # NEW — Third entrypoint, standalone process
│   ├── __init__.py
│   └── server.py                     # FastMCP server with 3 tools
│
├── frontend/                         # NEW — Static HTML/JS/CSS files
│   ├── index.html
│   ├── app.js
│   └── style.css
│
├── scraper/
│   └── yc_scraper.py                 # UNCHANGED
│
├── agent/
│   └── analyzer.py                   # MODIFIED: skip if description_hash matches
│
├── scripts/
│   ├── run_pipeline.py               # UNCHANGED (pipeline entrypoint)
│   ├── migrate_add_hash.py           # NEW — one-time ALTER TABLE migration
│   └── ai_code_review.py             # NEW — agentic PR reviewer (runs in CI)
│
├── .github/
│   └── workflows/
│       └── code-review.yml           # NEW — GitHub Actions CI trigger
│
├── data/
│   └── companies.db                  # SQLite (shared by all 3 entrypoints)
│
├── requirements.txt                  # + fastmcp
└── .env                              # + OPENAI_API_KEY already present
```

---

## Component Boundaries (v1.1)

| Component | Responsibility | Imports From | Never Imports From |
|-----------|---------------|--------------|-------------------|
| `scraper/yc_scraper.py` | HTTP + JSON fetch from YC API | `requests` | `app/`, `agent/`, `mcp_server/` |
| `agent/analyzer.py` | OpenAI calls + hash check for caching | `openai`, `app/models`, `hashlib` | `scraper/`, `mcp_server/` |
| `scripts/run_pipeline.py` | Orchestrate: scrape → analyze → store | `scraper/`, `agent/`, `app/models`, `app/database` | `mcp_server/`, `frontend/` |
| `scripts/migrate_add_hash.py` | One-time ALTER TABLE + CREATE INDEX | `app/database` (engine path), `sqlite3` | anything else |
| `app/models.py` | SQLModel Company table + schema | `sqlmodel` | `scraper/`, `agent/`, `mcp_server/` |
| `app/database.py` | Engine, get_db() | `sqlmodel`, `pathlib` | anything else |
| `app/config.py` | Typed settings from .env | `pydantic-settings` | anything |
| `app/routers/companies.py` | GET /companies (with filters), GET /companies/{id} | `app/models`, `app/database`, `sqlmodel` | `scraper/`, `agent/`, `mcp_server/` |
| `app/main.py` | App factory, routers, StaticFiles mount | `app/routers/`, `app/database`, `fastapi.staticfiles` | `scraper/`, `agent/`, `mcp_server/` |
| `mcp_server/server.py` | MCP tools: query DB for AI agents | `app/database`, `app/models`, `fastmcp` | `scraper/`, `agent/`, `app/routers/` |
| `scripts/ai_code_review.py` | Fetch PR diff, send to OpenAI, post comment | `openai`, `httpx`, `os` (env vars) | anything local |

**Key rule:** `mcp_server/` imports FROM `app/` — never the reverse. No circular dependency risk.

---

## Feature 1: MCP Server

### File Location: `mcp_server/server.py`

**Decision: Separate directory (`mcp_server/`), NOT `app/mcp.py`**

Rationale verified by code inspection:
- `app/mcp.py` implies the MCP logic is part of the FastAPI application and would need to be imported by `app/main.py` — creating architectural coupling.
- `mcp_server/server.py` is a **standalone process** with its own `if __name__ == "__main__": mcp.run()` entry. It signals "third entrypoint" just like `scripts/run_pipeline.py` signals "CLI entrypoint".
- `app.database` and `app.models` import cleanly from any script in the project root — **verified with live imports** (`engine` resolves to the correct absolute path in `data/companies.db`).

### No Circular Dependency Risk

```
mcp_server/server.py
    └── imports → app/database.py (engine, get_db)
    └── imports → app/models.py (Company)
    └── imports → fastmcp (FastMCP)

app/main.py
    └── imports → app/routers/ (never mcp_server/)

Result: One-way dependency graph. No cycles.
```

### Process Model: Separate Process

The MCP server runs as a **completely separate OS process** — not embedded in the FastAPI app. Both processes read from the same `data/companies.db` SQLite file. SQLite allows concurrent reads from multiple processes.

**Why not mount FastMCP onto FastAPI (same process)?**
`mcp.http_app()` returns a Starlette app that *can* be mounted onto FastAPI with `fastapi_app.mount('/mcp', mcp.http_app())` — verified in testing. But this couples the MCP server to the FastAPI lifecycle, meaning both die together. Separate processes are simpler to start/stop independently and cleaner for a demo.

### Transport Protocol: stdio (default) + streamable-http (optional)

Verified by inspecting FastMCP 3.2.0 source:

```python
# fastmcp.settings.transport defaults to "stdio"
# Valid values: "stdio", "http", "streamable-http", "sse"
```

**Use stdio for Claude Desktop** (most common demo scenario):
```python
if __name__ == "__main__":
    mcp.run()  # defaults to stdio transport
```

Claude Desktop config (`~/.claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "yc-research-agent": {
      "command": "python",
      "args": ["mcp_server/server.py"],
      "cwd": "/path/to/project"
    }
  }
}
```

**Use streamable-http for web-based MCP clients:**
```python
if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8001)
    # Endpoint: http://127.0.0.1:8001/mcp
```

### Pattern: mcp_server/server.py

```python
"""
MCP server exposing YC company data to AI agents.
Run: python mcp_server/server.py
Transport: stdio (Claude Desktop) or streamable-http (web clients)
"""
import sys
from pathlib import Path

# Make app/ importable from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastmcp import FastMCP
from sqlmodel import Session, select, col
from app.database import engine
from app.models import Company

mcp = FastMCP("YC Research Agent")


@mcp.tool
def get_all_companies() -> list[dict]:
    """Get all YC companies from the database with AI-generated insights."""
    with Session(engine) as session:
        companies = session.exec(select(Company)).all()
        return [c.model_dump() for c in companies]


@mcp.tool
def get_company_by_id(company_id: int) -> dict | None:
    """Get a specific YC company by database ID."""
    with Session(engine) as session:
        company = session.get(Company, company_id)
        return company.model_dump() if company else None


@mcp.tool
def search_companies(
    industry: str | None = None,
    business_model: str | None = None,
    search: str | None = None,
) -> list[dict]:
    """Search companies by industry, business model, or keyword."""
    with Session(engine) as session:
        stmt = select(Company)
        if industry:
            stmt = stmt.where(col(Company.industry) == industry)
        if business_model:
            stmt = stmt.where(col(Company.business_model) == business_model)
        if search:
            stmt = stmt.where(
                col(Company.company_name).contains(search)
                | col(Company.description).contains(search)
            )
        return [c.model_dump() for c in session.exec(stmt).all()]


if __name__ == "__main__":
    mcp.run()  # stdio by default; pass transport="streamable-http" for HTTP
```

**Session pattern:** `Session(engine)` context manager — identical to `get_db()` in FastAPI routes. No new DB session factory needed. SQLite handles concurrent reads from the API process and MCP process simultaneously.

---

## Feature 2: Filtering / Search on GET /companies

### Approach: Optional Query Params + Chained `.where()` Clauses

**Verified pattern** — all combinations tested with SQLModel 0.0.38 + SQLAlchemy 2.0.49:

```python
# app/routers/companies.py — MODIFIED

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select, col
from app.database import get_db
from app.models import Company

router = APIRouter()


@router.get("/companies", response_model=list[Company])
def get_companies(
    industry: Optional[str] = Query(default=None, description="Filter by industry"),
    business_model: Optional[str] = Query(default=None, description="Filter by business model"),
    search: Optional[str] = Query(default=None, description="Keyword search in name + description"),
    db: Session = Depends(get_db),
):
    stmt = select(Company)

    if industry:
        stmt = stmt.where(col(Company.industry) == industry)
    if business_model:
        stmt = stmt.where(col(Company.business_model) == business_model)
    if search:
        stmt = stmt.where(
            col(Company.company_name).contains(search)
            | col(Company.description).contains(search)
        )

    return db.exec(stmt).all()
```

**Key findings:**
- `col()` is imported from `sqlmodel` (not `sqlalchemy`) — it's SQLModel's typed column accessor
- `.contains(search)` generates `LIKE %search%` in SQLite — case-insensitive by default
- `|` operator generates SQL `OR` — works correctly with SQLModel/SQLAlchemy 2.x
- No query param = no WHERE clause = returns all records (backward-compatible with v1.0 clients)
- All 3 params can be combined (AND logic between params, OR logic within search)

### Index Strategy

Add `index=True` to `industry` and `business_model` fields in `app/models.py`:

```python
# app/models.py — MODIFIED
class Company(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    company_name: str
    description: str
    website: Optional[str] = None
    industry: Optional[str] = Field(default=None, index=True)       # + index
    business_model: Optional[str] = Field(default=None, index=True) # + index
    summary: Optional[str] = None
    use_case: Optional[str] = None
    description_hash: Optional[str] = Field(default=None, index=True)  # new in v1.1
```

**Index caveat:** `Field(index=True)` creates the index via `SQLModel.metadata.create_all()` — but **only for new tables**. For the existing `company` table, `create_all` is a no-op (verified by test: it does not ALTER existing tables). The migration script (`scripts/migrate_add_hash.py`) must also create the indexes explicitly with `CREATE INDEX IF NOT EXISTS`.

At 50-500 records, query speed is negligible with or without indexes. Add them anyway — it's one line per field and sets the right precedent.

---

## Feature 3: AI Caching (description_hash)

### Column Design

Add to `app/models.py`:
```python
description_hash: Optional[str] = Field(default=None, index=True)
```

- **Type:** `Optional[str]` (TEXT in SQLite) — stores 32-char MD5 hex digest
- **Index:** Yes — the analyzer looks up companies by hash to check if re-analysis is needed
- **Default:** `None` — existing rows get NULL after migration (triggers re-analysis on next run)

### Migration: ALTER TABLE (not create_all)

**Critical finding:** `SQLModel.metadata.create_all(engine)` does **NOT** add columns to existing tables. Verified by test:

```
V1 table created → create_all with V2 model (+ description_hash) called
Result: No error raised, but column NOT added to existing table
Columns after create_all: ['id', 'company_name', 'description']  ← unchanged
```

**Required migration approach — `scripts/migrate_add_hash.py`:**

```python
"""
One-time migration: add description_hash column to the company table.
Safe to run multiple times (IF NOT EXISTS guard).

Run: python scripts/migrate_add_hash.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "companies.db"


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if column already exists (idempotent)
    cols = [row[1] for row in cursor.execute("PRAGMA table_info(company)").fetchall()]
    if "description_hash" not in cols:
        cursor.execute("ALTER TABLE company ADD COLUMN description_hash TEXT")
        print("Added description_hash column")
    else:
        print("description_hash already exists — skipping")

    # Add index (IF NOT EXISTS = idempotent)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_company_description_hash "
        "ON company (description_hash)"
    )
    # Add indexes for industry and business_model while we're here
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_company_industry ON company (industry)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_company_business_model ON company (business_model)"
    )
    conn.commit()
    conn.close()
    print("Migration complete")


if __name__ == "__main__":
    migrate()
```

**Why not Alembic?** At this scale (single SQLite file, 3-4 column additions), Alembic adds 5+ config files and a learning curve for zero benefit. A 30-line migration script is more readable, less failure-prone, and faster to write.

### Caching Logic in agent/analyzer.py

```python
import hashlib

def compute_description_hash(description: str) -> str:
    """MD5 hash of description — 32-char hex string."""
    return hashlib.md5((description or "").encode()).hexdigest()


def should_analyze(company: Company) -> bool:
    """True if company needs (re-)analysis."""
    if company.industry is None:
        return True  # Never analyzed
    if company.description_hash is None:
        return True  # Pre-v1.1 record — analyze to populate hash
    current_hash = compute_description_hash(company.description or "")
    return current_hash != company.description_hash  # Description changed


# In the analysis loop (run_pipeline.py):
for company in companies:
    if not should_analyze(company):
        print(f"Skipping {company.company_name} — description unchanged")
        continue
    result = analyze_company(company)  # OpenAI call
    company.industry = result.industry
    company.description_hash = compute_description_hash(company.description or "")
    session.add(company)
    session.commit()
```

**Data flow for caching:**
```
run_pipeline.py
    ├── scraper writes company_name + description to DB
    └── analyzer checks: description_hash matches current description?
            YES → skip OpenAI call (saves API cost)
            NO / NULL → call OpenAI → save result + update hash
```

---

## Feature 4: Simple Frontend

### Approach: StaticFiles mounted at /ui in FastAPI

**Decision: `app.mount("/ui", StaticFiles(...))` — NOT a separate server**

Verified with FastAPI + Starlette:
```python
# app/main.py — MODIFIED
from fastapi.staticfiles import StaticFiles

app.mount("/ui", StaticFiles(directory="frontend", html=True), name="frontend")
```

**Why `/ui` not `/`?**
- Mounting at `/` causes routing conflicts — the catch-all static route intercepts all unmatched paths before FastAPI 404 handlers (verified by test: route ordering matters)
- Mounting at `/ui` keeps `/docs`, `/companies`, `/openapi.json` fully functional
- `/ui` is also clearer in demos: `http://localhost:8000/ui` vs `http://localhost:8000/`

**Why NOT a separate `open index.html`?**
- A bare `index.html` opened as `file://` cannot make `fetch()` calls to `http://localhost:8000` — browsers block cross-origin `file://` → `http://` requests (CORS + mixed-content policy)
- Serving via FastAPI eliminates this entirely: both at `http://localhost:8000`, same origin

**`html=True` flag:** Enables `index.html` fallback for any path under `/ui/` — correct behavior for a single-page app. Without it, `GET /ui/` returns 404 instead of serving `index.html`.

**Mount order rule:** `app.mount()` calls must come **after** all `app.include_router()` calls. FastAPI matches routes in order; static mount is a catch-all for its prefix.

```python
# app/main.py — correct order
app = FastAPI(lifespan=lifespan)
app.include_router(companies_router)      # 1. API routes first
app.mount("/ui", StaticFiles(...), ...)   # 2. Static mount last
```

### Frontend Files: frontend/

```
frontend/
├── index.html    # table layout, filter inputs, script src="app.js"
├── app.js        # fetch("/companies?industry=..."), build DOM table rows
└── style.css     # minimal table/card styling, no framework needed
```

**Frontend data flow:**
```
Browser → GET /ui/index.html (served by FastAPI StaticFiles)
         → loads app.js
         → app.js: fetch("/companies")      or
                   fetch("/companies?industry=fintech&search=payments")
         → JSON response → render table rows → display
```

**Keep it simple:** Vanilla JS, no framework. The goal is a working demo with companies in a table, filter inputs, and a search box. No build step, no npm.

---

## Feature 5: GitHub Actions CI/CD

### File Location: `.github/workflows/code-review.yml`

The `.github/workflows/` directory must be created — only `.github/copilot-instructions.md` exists today.

### Trigger: pull_request with types

```yaml
on:
  pull_request:
    types: [opened, synchronize]
```

- `opened` — fires when a new PR is created
- `synchronize` — fires when new commits are pushed to an existing PR
- **Do NOT use `reopened`** — redundant for code review purposes

### Permissions: Minimal Required Set

```yaml
permissions:
  contents: read        # checkout the repo and read changed files
  pull-requests: write  # post review comments on the PR
```

`GITHUB_TOKEN` is automatically injected by the Actions runtime — no manual secret. Only `OPENAI_API_KEY` needs to be added to repo secrets manually (`Settings → Secrets → Actions → New repository secret`).

### Workflow Pattern

```yaml
# .github/workflows/code-review.yml
name: AI Code Review

on:
  pull_request:
    types: [opened, synchronize]

permissions:
  contents: read
  pull-requests: write

jobs:
  ai-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # full history for accurate diff

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install openai httpx

      - name: Run AI Code Review
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
          REPO: ${{ github.repository }}
        run: python scripts/ai_code_review.py
```

### Agent Script: scripts/ai_code_review.py

```python
"""
AI code reviewer: fetches PR diff from GitHub API, sends to OpenAI,
posts result as a PR comment.

Runs inside GitHub Actions. Requires env vars:
  OPENAI_API_KEY — from repo secrets
  GITHUB_TOKEN   — auto-injected by Actions
  PR_NUMBER      — from github.event.pull_request.number
  REPO           — from github.repository ("owner/repo")
"""
import os
import httpx
from openai import OpenAI

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
PR_NUMBER = os.environ["PR_NUMBER"]
REPO = os.environ["REPO"]

GITHUB_API = "https://api.github.com"
HEADERS = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3.diff"}


def get_pr_diff() -> str:
    url = f"{GITHUB_API}/repos/{REPO}/pulls/{PR_NUMBER}"
    response = httpx.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.text  # GitHub returns diff when Accept header is set


def review_with_openai(diff: str) -> str:
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a Python code reviewer. Review the following git diff "
                    "and provide: 1) a summary of changes, 2) potential bugs or issues, "
                    "3) suggestions for improvement. Be concise and specific."
                ),
            },
            {"role": "user", "content": f"Review this diff:\n\n{diff[:8000]}"},  # token limit
        ],
    )
    return response.choices[0].message.content


def post_pr_comment(review: str) -> None:
    url = f"{GITHUB_API}/repos/{REPO}/issues/{PR_NUMBER}/comments"
    headers = {**HEADERS, "Accept": "application/vnd.github.v3+json", "Content-Type": "application/json"}
    body = {"body": f"## 🤖 AI Code Review\n\n{review}"}
    response = httpx.post(url, headers=headers, json=body)
    response.raise_for_status()
    print(f"Posted review comment to PR #{PR_NUMBER}")


if __name__ == "__main__":
    diff = get_pr_diff()
    review = review_with_openai(diff)
    post_pr_comment(review)
```

---

## Build Order for v1.1

Dependencies determine order. Each phase can be built and tested independently.

```
Phase 5.1: description_hash column
  - Modify app/models.py (add column)
  - Create scripts/migrate_add_hash.py
  - Run migration on dev DB
  UNBLOCKS: Phase 5.2 (filtering indexes), Phase 5.3 (caching in analyzer)

Phase 5.2: Filtering / Search
  - Modify app/routers/companies.py (query params + where clauses)
  - Test: GET /companies?industry=fintech returns subset
  REQUIRES: migration run (for index creation)
  UNBLOCKS: Phase 5.4 (frontend uses filters), Phase 5.5 (MCP uses search)

Phase 5.3: MCP Server
  - Create mcp_server/__init__.py + mcp_server/server.py
  - Add fastmcp to requirements.txt
  - Test: run server.py, connect Claude Desktop via stdio
  REQUIRES: Phase 5.1 complete (description_hash in model)
  INDEPENDENT OF: Phase 5.2 (MCP has its own filter logic)

Phase 5.4: Frontend
  - Create frontend/ directory with index.html, app.js, style.css
  - Modify app/main.py to mount StaticFiles at /ui
  - Test: http://localhost:8000/ui shows company table
  REQUIRES: Phase 5.2 complete (frontend uses filter query params)

Phase 5.5: CI/CD
  - Create .github/workflows/code-review.yml
  - Create scripts/ai_code_review.py
  - Add OPENAI_API_KEY to GitHub repo secrets
  - Test: open PR, verify AI comment appears
  INDEPENDENT OF: all other v1.1 phases (infrastructure only)
  BUILD LAST: no code depends on it
```

**Recommended execution order:**

| Phase | Feature | Reason |
|-------|---------|--------|
| 5.1 | description_hash + migration | Schema change must land first; unblocks everything |
| 5.2 | Filtering | Modifies existing route; self-contained; unlocks frontend |
| 5.3 | MCP Server | New entrypoint; good standalone demo artifact |
| 5.4 | Frontend | Depends on filtering; visual payoff for the milestone |
| 5.5 | CI/CD | Infrastructure; independent; no other feature depends on it |

---

## Data Flow Changes (v1.1)

### Pipeline Mode (modified)

```
scripts/run_pipeline.py
    │
    ├─► scraper/yc_scraper.py → list[dict] (unchanged)
    │
    └─► for each company:
            │
            ├─► should_analyze(company)?
            │       compare description_hash(current) vs stored hash
            │       NO match OR hash is NULL → proceed to OpenAI
            │       MATCH → skip (return early, log "skipping")
            │
            └─► agent/analyzer.py.analyze(company)
                    └─► OpenAI structured output (unchanged)
                    └─► company.description_hash = md5(description)
                    └─► session.commit() per company (unchanged)
```

### API Mode (modified GET /companies)

```
GET /companies?industry=fintech&search=payments
    │
    ▼
app/routers/companies.py
    │
    stmt = select(Company)
    stmt = stmt.where(col(Company.industry) == "fintech")
    stmt = stmt.where(col(Company.company_name).contains("payments") |
                      col(Company.description).contains("payments"))
    │
    ▼
SQLite: SELECT * FROM company WHERE industry='fintech'
        AND (company_name LIKE '%payments%' OR description LIKE '%payments%')
    │
    ▼
JSON response: [{ ...company fields... }, ...]
```

### MCP Mode (new)

```
Claude Desktop / MCP Client
    │
    │  stdio: {"method": "tools/call", "params": {"name": "search_companies",
    │           "arguments": {"industry": "fintech"}}}
    │
    ▼
mcp_server/server.py
    │
    Session(engine)  ← same engine as FastAPI (same SQLite file)
    select(Company).where(col(Company.industry) == "fintech")
    │
    ▼
data/companies.db  (concurrent read — SQLite supports this)
    │
    ▼
[{company dict}, ...] → JSON serialized → stdio response to Claude
```

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Using create_all for Schema Migration
**What:** Adding `description_hash` to `Company` model and expecting `create_all(engine)` to add it to the existing table.
**Why bad:** `create_all` uses `checkfirst=True` — it only creates tables that don't exist. **Verified by test**: calling `create_all` with a model containing the new column leaves the existing table completely unchanged. The column will be absent at runtime, causing silent failures when the analyzer tries to write `company.description_hash`.
**Instead:** Use `scripts/migrate_add_hash.py` with `ALTER TABLE company ADD COLUMN description_hash TEXT` before any code that reads/writes the field.

### Anti-Pattern 2: MCP Server in app/mcp.py
**What:** Creating `app/mcp.py` and importing it in `app/main.py`.
**Why bad:** The MCP server is a **third standalone entrypoint**, not a FastAPI extension. Putting it in `app/` implies it shares the uvicorn lifecycle. It also tempts importing `app/routers/` which breaks the component boundary principle.
**Instead:** `mcp_server/server.py` — same pattern as `scripts/run_pipeline.py` (separate entrypoint that imports from `app/`, but is never imported by `app/`).

### Anti-Pattern 3: Mounting Static Files at "/"
**What:** `app.mount("/", StaticFiles(directory="frontend", html=True))`
**Why bad:** The `/` mount is a catch-all that intercepts all requests **after** matched routes, but since StaticFiles returns 404 for missing files, it interferes with FastAPI's error handling and makes the routing harder to reason about. Worse, if placed before `include_router()`, it shadows all API routes.
**Instead:** Mount at `/ui` — explicit, clean separation, `/docs` and `/companies` unaffected.

### Anti-Pattern 4: stdio MCP Server Behind Reverse Proxy
**What:** Running the MCP server with stdio transport but trying to expose it via nginx/ngrok.
**Why bad:** stdio transport is a pipe-based protocol designed for **direct process communication** (Claude Desktop spawns the process). It has no HTTP interface to proxy.
**Instead:** Use `transport="streamable-http"` if you need the MCP server accessible over HTTP: `mcp.run(transport="streamable-http", port=8001)`.

### Anti-Pattern 5: Sharing Session Objects Across MCP Tool Calls
**What:** Creating one `Session(engine)` at module level in `mcp_server/server.py` and reusing it across multiple tool calls.
**Why bad:** MCP tool calls may be concurrent. A shared session across calls creates the same threading problem as FastAPI without `Depends(get_db)`. SQLite raises `ProgrammingError: SQLite objects created in a thread can only be used in that same thread`.
**Instead:** Create a new `Session(engine)` context manager inside each `@mcp.tool` function — identical pattern to FastAPI routes.

---

## Modified Files Checklist

| File | Change Type | What Changes |
|------|------------|--------------|
| `app/models.py` | Modify | Add `description_hash: Optional[str] = Field(default=None, index=True)` + `index=True` on `industry` + `business_model` |
| `app/routers/companies.py` | Modify | Add `industry`, `business_model`, `search` Optional query params + `where()` clauses |
| `app/main.py` | Modify | Add `from fastapi.staticfiles import StaticFiles` + `app.mount("/ui", StaticFiles(directory="frontend", html=True), name="frontend")` |
| `agent/analyzer.py` | Modify | Add `should_analyze()` hash check, compute + store `description_hash` after analysis |
| `requirements.txt` | Modify | Add `fastmcp==3.2.0` |

## New Files Checklist

| File | Purpose |
|------|---------|
| `mcp_server/__init__.py` | Python package marker |
| `mcp_server/server.py` | FastMCP server with 3 tools (get_all, get_by_id, search) |
| `frontend/index.html` | Company table with filter inputs |
| `frontend/app.js` | fetch() calls to /companies, DOM rendering |
| `frontend/style.css` | Minimal styling |
| `scripts/migrate_add_hash.py` | One-time ALTER TABLE + CREATE INDEX (idempotent) |
| `.github/workflows/code-review.yml` | GitHub Actions CI trigger |
| `.github/workflows/__init__.py` | Not needed — GitHub Actions reads YAML directly |
| `scripts/ai_code_review.py` | Agentic PR reviewer (diff → OpenAI → PR comment) |

---

## Sources

All findings verified by live code inspection (not training data only):

- **FastMCP 3.2.0** — installed and inspected: `run()`, `run_async()`, `http_app()`, `tool` decorator, `mount()`, default transport settings. Confirmed: `stdio` is default; `streamable-http` available; Starlette app mountable on FastAPI.
- **SQLModel 0.0.38 + SQLAlchemy 2.0.49** — tested: `col()` + `where()` chaining with Optional params; `|` OR operator; `contains()` for LIKE queries; `create_all` does NOT alter existing tables.
- **SQLite ALTER TABLE** — tested: `ADD COLUMN description_hash TEXT` adds column with NULL default for existing rows; `CREATE INDEX IF NOT EXISTS` is idempotent.
- **FastAPI StaticFiles** — tested: `/ui` mount vs `/` routing conflict; `html=True` flag behavior; mount ordering relative to `include_router()`.
- **GitHub Actions** — standard patterns: `pull_request` trigger with `types`, `GITHUB_TOKEN` auto-injection, `permissions` block for PR write access.
