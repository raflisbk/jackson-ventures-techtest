# Technology Stack — v1.1 Additions

**Project:** AI Company Research Agent (v1.1 milestone)
**Researched:** 2026-04-07 (v1.1 update, overwriting stale v1.0 Playwright content)
**Source verification:** PyPI live version checks, GitHub API release queries, official docs

> **Scope:** This file covers only **new additions** for the 5 v1.1 features.
> Existing stack (Python 3.13, FastAPI 0.135.3, SQLModel 0.0.38, OpenAI 2.30.0,
> pydantic-settings 2.7.1, tenacity 9.1.4, requests 2.32.3, SQLite, uvicorn 0.44.0)
> is retained as-is. **Zero changes** to existing dependencies are required.

---

## Existing Stack Compatibility Snapshot

Before adding anything, the existing venv was verified:

| Package | Installed | FastMCP 3.2.0 Requires | Compatible? |
|---------|-----------|------------------------|-------------|
| pydantic | 2.12.5 | `>=2.11.7` | ✅ Yes |
| uvicorn | 0.44.0 | `>=0.35` | ✅ Yes |
| openapi-pydantic | 0.5.1 | `>=0.5.1` | ✅ Yes (exact match) |
| Python | 3.13 | `>=3.10` | ✅ Yes |

**Only one new Python package is required for all 5 features combined: `fastmcp`.**

---

## Recommended Stack — v1.1 New Additions

---

### Feature 1: MCP Server

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `fastmcp` | `3.2.0` | MCP server framework | The standard Python MCP framework — used by 70% of MCP servers across all languages. `@mcp.tool` decorator auto-generates MCP schemas from Python function signatures. Owned by PrefectHQ, originally by FastAPI-aligned author Jeremiah Lowin (jlowin). Python 3.13 compatible. |

**FastMCP 3.x background:** FastMCP 1.0 was incorporated into the official MCP Python SDK in 2024. FastMCP 2.x/3.x is the standalone project (PrefectHQ/fastmcp) with continued active development. 3.x adds better transport options and middleware but the core `@mcp.tool` + `mcp.run()` API is stable since 1.0.

**Integration with existing SQLModel/SQLite:**

The MCP server is a **separate Python process** (`mcp/server.py`) that imports the same `engine` and `Session` from `app/database.py`. No shared process, no shared state — each tool call opens its own SQLModel `Session`. This is the same pattern as the FastAPI routes.

```python
# mcp/server.py — standalone process, import existing DB layer
from fastmcp import FastMCP
from sqlmodel import Session, select, col
from app.database import engine
from app.models import Company

mcp = FastMCP(
    "Company Research MCP",
    instructions="Provides tools to query the YC company research database.",
)

@mcp.tool
def list_companies() -> list[dict]:
    """Return all companies in the database."""
    with Session(engine) as session:
        companies = session.exec(select(Company)).all()
        return [c.model_dump() for c in companies]

@mcp.tool
def get_company(company_id: int) -> dict | None:
    """Get a single company by ID. Returns None if not found."""
    with Session(engine) as session:
        company = session.get(Company, company_id)
        return company.model_dump() if company else None

@mcp.tool
def search_companies(query: str) -> list[dict]:
    """Search companies by name or description (case-insensitive substring match)."""
    with Session(engine) as session:
        stmt = select(Company).where(
            col(Company.company_name).contains(query) |
            col(Company.description).contains(query)
        )
        return [c.model_dump() for c in session.exec(stmt).all()]

if __name__ == "__main__":
    mcp.run()  # STDIO transport by default — correct for LLM client subprocess mode
```

**Transport:** STDIO (default) is correct for local LLM client integration (Claude Desktop, Cursor, etc. all launch the server as a subprocess). HTTP transport (`mcp.run(transport="http", port=9000)`) is available if remote access is needed in future.

**Run command:**
```bash
python mcp/server.py
```

**MCP client config (Claude Desktop `claude_desktop_config.json`):**
```json
{
  "mcpServers": {
    "company-research": {
      "command": "python",
      "args": ["mcp/server.py"],
      "cwd": "/path/to/project"
    }
  }
}
```

---

### Feature 2: Filtering/Search on GET /companies

**No new packages.** SQLModel's `select().where()` with `col()` handles this.

```python
# app/routers/companies.py — add Optional query params
from typing import Optional
from fastapi import Query
from sqlmodel import col

@app.get("/companies", response_model=list[Company])
def get_companies(
    industry: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    stmt = select(Company)
    if industry:
        stmt = stmt.where(col(Company.industry) == industry)
    if q:
        stmt = stmt.where(
            col(Company.company_name).contains(q) |
            col(Company.description).contains(q)
        )
    return db.exec(stmt).all()
```

**SQLite LIKE caveat:** SQLite's `LIKE` (what `.contains()` maps to) is case-insensitive for ASCII characters by default. Unicode characters (non-ASCII) are case-sensitive. For an English-language startup database this is fine. Do NOT add `func.lower()` unless needed — it prevents SQLite from using any future index on those columns.

---

### Feature 3: AI Response Caching (SHA-256)

**No new packages.** `hashlib` is Python stdlib.

**Confirmed correct approach.** SHA-256 via `hashlib` is the standard pattern for content-addressed caching. The hash fits in a `VARCHAR(64)` column (64 hex chars) and is cheap to compute.

**Model change** — add `description_hash` field to `app/models.py`:

```python
class Company(SQLModel, table=True):
    # ... existing fields ...
    description_hash: Optional[str] = Field(default=None, index=True)
    # index=True: lookup by hash is the hot path; 50 records makes this negligible
    # but it's a good habit and costs nothing
```

**Caching pattern** in the AI analysis pipeline:

```python
import hashlib

def get_description_hash(description: str) -> str:
    # CRITICAL: .strip() before hashing — trailing whitespace changes the hash
    # and would cause cache misses for functionally identical descriptions
    return hashlib.sha256(description.strip().encode("utf-8")).hexdigest()

def analyze_company(company: Company, session: Session) -> Company:
    new_hash = get_description_hash(company.description)

    # Cache hit: skip OpenAI call entirely
    if company.description_hash == new_hash and company.summary is not None:
        return company  # already analyzed, nothing to do

    # Cache miss: call OpenAI, then store hash
    result = call_openai(company.description)  # existing logic
    company.industry = result["industry"]
    company.summary = result["summary"]
    # ... other fields ...
    company.description_hash = new_hash  # mark as analyzed
    session.add(company)
    session.commit()
    return company
```

**Gotchas:**
1. **Must `.strip()` before hashing** — a trailing newline from the scraper will cause perpetual cache misses.
2. **Two-condition cache check** — hash match AND `summary is not None`. If a record has a hash but `summary` is null (e.g. failed mid-write), it must re-analyze.
3. **Schema migration** — existing DB rows won't have `description_hash`. SQLite `ALTER TABLE ADD COLUMN` is safe when the column has a default (None). `SQLModel.metadata.create_all()` does NOT add columns to existing tables. Either drop-and-recreate for dev, or add a one-time migration script for prod.

---

### Feature 4: Static Frontend

**No new packages.** FastAPI's built-in `StaticFiles` serves static HTML/JS with no framework needed.

**Decision: Vanilla HTML/JS — no build step, no framework, no new dependencies.**

Rationale: The UI needs company cards + an industry filter dropdown + a text search box. This is ~100 lines of HTML and ~80 lines of JavaScript. Any framework (Alpine.js, Vue CDN, React) would add cognitive overhead for a problem that `fetch()` + `document.createElement()` solves directly. Build steps (Vite, Webpack) are completely unnecessary.

**FastAPI integration** — add to `main.py`:
```python
from fastapi.staticfiles import StaticFiles

# Mount after all API routes to avoid shadowing /companies
app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")
# Accessible at http://localhost:8000/app/
```

**Frontend structure:**
```
frontend/
  index.html   # company browser UI
  app.js       # fetch + render logic
```

**Core fetch pattern in `app.js`:**
```javascript
async function loadCompanies(industry = '', query = '') {
  const params = new URLSearchParams();
  if (industry) params.set('industry', industry);
  if (query) params.set('q', query);

  const resp = await fetch(`/companies?${params}`);
  const companies = await resp.json();
  renderCards(companies);
}

function renderCards(companies) {
  const grid = document.getElementById('company-grid');
  grid.innerHTML = companies.map(c => `
    <div class="card">
      <h3>${escapeHtml(c.company_name)}</h3>
      <span class="badge">${escapeHtml(c.industry ?? 'Unknown')}</span>
      <p>${escapeHtml(c.summary ?? c.description)}</p>
    </div>
  `).join('');
}
```

**XSS note:** Always `escapeHtml()` when setting innerHTML with API data. Use `textContent` for plain text nodes, or a minimal escape function for HTML injection.

---

### Feature 5: CI/CD — GitHub Actions with Agentic Code Review

**No Python packages.** GitHub Actions YAML only. One secret required: `ANTHROPIC_API_KEY`.

**Chosen action: `anthropics/claude-code-action@v1`** — the official Anthropic GitHub Action, latest stable release (v1.0). Auto-detects PR review mode when triggered on `pull_request` events. Posts inline code annotations and top-level review comments directly on the PR.

**Why not alternatives:**
- `github/copilot-for-prs` — requires GitHub Copilot Enterprise subscription (~$39/user/month). Overkill for a solo/small project.
- Rolling your own with `openai` in a workflow step — requires custom prompt engineering, GitHub API calls for diff fetching, manual comment posting. The claude-code-action handles all of this.
- `coderabbitai` — subscription SaaS product, not a GitHub Action you control.

**Complete workflow — `.github/workflows/ci.yml`:**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]

jobs:
  # --- Job 1: Run tests on every push and PR ---
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6

      - uses: actions/setup-python@v6
        with:
          python-version: "3.13"
          cache: "pip"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run tests
        run: pytest tests/ -v

  # --- Job 2: Agentic PR code review (PR events only) ---
  code-review:
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    permissions:
      contents: read
      pull-requests: write
      id-token: write
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 1

      - uses: anthropics/claude-code-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          prompt: |
            REPO: ${{ github.repository }}
            PR NUMBER: ${{ github.event.pull_request.number }}

            Review this pull request for an AI company research agent (Python/FastAPI/SQLModel).
            Focus on:
            - Correctness of SQLModel queries and session handling
            - OpenAI API usage patterns (error handling, retries)
            - FastAPI route logic and response models
            - Security issues (SQL injection, input validation, secret exposure)
            - Missing tests for new behavior

            Note: The PR branch is already checked out.
            Use `gh pr comment` for top-level feedback.
            Use `mcp__github_inline_comment__create_inline_comment` (with `confirmed: true`) for inline code issues.
          claude_args: |
            --allowedTools "mcp__github_inline_comment__create_inline_comment,Bash(gh pr comment:*),Bash(gh pr diff:*),Bash(gh pr view:*)"
```

**Required GitHub secret:** Add `ANTHROPIC_API_KEY` in repo Settings → Secrets and variables → Actions.

**`actions/checkout@v6`** — verified latest (v6.0.2, published 2026-01-09).
**`actions/setup-python@v6`** — verified latest (v6.2.0, published 2026-01-22). The `cache: "pip"` input caches pip downloads between runs for faster CI.

---

## Updated `requirements.txt`

Only one line added versus v1.0:

```txt
# AI / OpenAI
openai==2.30.0
tenacity==9.1.4

# Database
sqlmodel==0.0.38

# API
fastapi[standard]==0.135.3

# Config
pydantic-settings==2.7.1
python-dotenv==1.2.2

# HTTP (scraper)
requests==2.32.3

# MCP Server (v1.1 new)
fastmcp==3.2.0

# Testing
pytest==9.0.2
httpx==0.28.1
```

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| MCP framework | `fastmcp==3.2.0` | `mcp==1.27.0` (raw SDK) | `mcp` requires manual schema definition, transport boilerplate, and lifecycle management. FastMCP is the standard layer that the MCP SDK itself incorporated — use it. |
| MCP framework | `fastmcp==3.2.0` | FastMCP 2.x | 3.x is the current stable branch with Python 3.13 support and active maintenance. 2.x is deprecated. |
| Frontend | Vanilla HTML/JS | Alpine.js (CDN) | Alpine adds reactivity syntax (`x-data`, `x-for`) but the problem (filter + card render) is solved in 80 lines of plain JS with no learning curve. |
| Frontend | Vanilla HTML/JS | Vue.js (CDN) | Vue CDN usage without a build step loses IDE support and type safety. Unjustified complexity for ~100 lines of UI. |
| Frontend | Vanilla HTML/JS | HTMX | HTMX requires server-side HTML rendering. Our FastAPI routes return JSON; adding server-side templates means adding Jinja2 and restructuring routes. Not worth it. |
| CI code review | `claude-code-action@v1` | `github/copilot-for-prs` | Requires GitHub Copilot Enterprise ($39+/user/month). |
| CI code review | `claude-code-action@v1` | Custom OpenAI workflow step | Manual: must fetch diff via GitHub API, build prompt, call OpenAI, parse response, post comment. The action does all of this. |
| Caching hash | `hashlib.sha256` (stdlib) | `hashlib.md5` | SHA-256 is collision-resistant and the modern default. MD5 has known collision vulnerabilities — not a real risk here but no reason to use it when SHA-256 is equally fast. |
| Caching hash | `hashlib.sha256` (stdlib) | Redis/external cache | SQLite column is sufficient — no network hop, no new infrastructure, no new process. |

---

## What NOT to Add

| Package | Why to Avoid |
|---------|-------------|
| `alembic` | SQLite + SQLModel at 50 records doesn't need migration tooling. `SQLModel.metadata.create_all()` is fine. For the `description_hash` column addition, a one-time `ALTER TABLE` script is sufficient. |
| `celery` / `rq` | Background job queue not needed — AI analysis runs synchronously in the pipeline script, not as an API request. |
| `redis` | No distributed caching needed — single-process, SQLite-backed cache is sufficient. |
| `jinja2` / `aiofiles` | Server-side HTML templates are unnecessary when `StaticFiles` serves pre-built HTML/JS. |
| `pytest-asyncio` | Not needed for v1.1 tests. The MCP server and FastAPI routes are synchronous. Only add if async tests are needed. |
| `Alpine.js` / `Vue` / `React` | Static HTML/JS is sufficient for the company browser. No build pipeline, no framework. |
| `scrapy` / `playwright` / `beautifulsoup4` | Scraping is done in v1.0 via `requests`. These are not needed for v1.1 features. |

---

## Version Compatibility Matrix

| Package | Version | Constraint Source | Status |
|---------|---------|-------------------|--------|
| `fastmcp` | 3.2.0 | New in v1.1 | ✅ Compatible with all existing deps |
| `pydantic` | 2.12.5 (installed) | FastMCP requires `>=2.11.7` | ✅ Satisfied without upgrade |
| `uvicorn` | 0.44.0 (installed) | FastMCP requires `>=0.35` | ✅ Satisfied without upgrade |
| `openapi-pydantic` | 0.5.1 (installed) | FastMCP requires `>=0.5.1` | ✅ Exact match |
| Python | 3.13 | FastMCP requires `>=3.10` | ✅ Compatible |
| `actions/checkout` | v6 (v6.0.2) | GitHub Actions | ✅ Verified latest (2026-01-09) |
| `actions/setup-python` | v6 (v6.2.0) | GitHub Actions | ✅ Verified latest (2026-01-22) |
| `claude-code-action` | v1 (v1.0) | Anthropic | ✅ Latest stable |

**FastMCP transitive deps pulled on install** (not in requirements.txt but resolved by pip):
`authlib`, `cyclopts`, `mcp>=1.24.0`, `opentelemetry-api`, `pyyaml`, `rich`, `watchfiles`, `websockets`, and others. None conflict with existing deps.

---

## Installation — v1.1 Delta

```bash
# Activate existing venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Unix/Mac

# Add the only new Python package for v1.1
pip install fastmcp==3.2.0

# No other Python packages needed for v1.1 features:
# - Filtering: SQLModel (already installed)
# - Caching: hashlib (stdlib)
# - Frontend: FastAPI StaticFiles (already installed)
# - CI/CD: GitHub Actions YAML (no Python package)
```

**GitHub Actions setup:**
1. Add `ANTHROPIC_API_KEY` secret in repo Settings → Secrets → Actions
2. Create `.github/workflows/ci.yml` with the YAML above
3. Create `frontend/index.html` + `frontend/app.js`
4. Create `mcp/server.py` with FastMCP tools

---

## Sources

| Source | What It Confirmed | Confidence |
|--------|-------------------|------------|
| PyPI `fastmcp` API (live, 2026-04-07) | v3.2.0 is latest; Python 3.13 compat; pydantic>=2.11.7; uvicorn>=0.35 | HIGH |
| PyPI `mcp` API (live, 2026-04-07) | v1.27.0; fastmcp depends on `mcp>=1.24.0` | HIGH |
| PrefectHQ/fastmcp README (GitHub raw, live) | `@mcp.tool` + `mcp.run()` pattern; STDIO default; HTTP available | HIGH |
| PrefectHQ/fastmcp docs/servers/server.mdx (GitHub raw, live) | Server creation, component types, transport options | HIGH |
| PrefectHQ/fastmcp docs/servers/tools.mdx (GitHub raw, live) | `@mcp.tool` decorator, schema auto-generation | HIGH |
| `anthropics/claude-code-action` action.yml (GitHub raw, live) | `anthropic_api_key`, `prompt`, `claude_args` inputs; v1 tag | HIGH |
| `anthropics/claude-code-action` docs/solutions.md (GitHub raw, live) | PR review YAML pattern; `actions/checkout@v6`; permissions block | HIGH |
| GitHub API `actions/checkout` releases/latest (live) | v6.0.2, published 2026-01-09 | HIGH |
| GitHub API `actions/setup-python` releases/latest (live) | v6.2.0, published 2026-01-22 | HIGH |
| Project `.venv` pip list (live, this machine) | pydantic 2.12.5, uvicorn 0.44.0, openapi-pydantic 0.5.1 installed | HIGH |
| Python stdlib `hashlib` (verified in Python 3.13) | SHA-256 available; `.strip()` gotcha demonstrated | HIGH |
