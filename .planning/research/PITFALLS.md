# Domain Pitfalls: AI Company Research Agent

**Domain:** AI agent + web scraping + FastAPI + SQLite
**Researched:** 2026-04-07 (v1.0) · Updated 2025-01-01 (v1.1 integration pitfalls appended)
**Verification:** All pitfalls verified via live code execution or official library inspection

---

## v1.1 Integration Pitfalls

> **Scope:** These pitfalls are specific to ADDING v1.1 features (MCP server, filtering, AI caching, static frontend, GitHub Actions CI) to the existing v1.0 Python/FastAPI/SQLModel/SQLite app. Generic FastAPI/Python pitfalls are in the v1.0 section below.

---

### MCP-1: FastMCP stdio Transport Corrupts the Protocol Stream with `print()`

**Feature:** MCP server
**Phase:** MCP Server phase

**What goes wrong:**
FastMCP's default `stdio` transport uses **stdout as the JSON-RPC protocol channel**. Every `print()` call in your tool code — including any `print()` in imported modules — writes to stdout and corrupts the JSON-RPC framing. The MCP client (Claude Desktop, Cursor, etc.) silently fails to parse the response, or crashes with a JSON decode error. There is no obvious error message explaining why.

**Why it happens:**
The existing FastAPI app and pipeline scripts use `print()` for logging. If any of those modules are imported into the MCP server (`from app.models import Company` etc.), top-level module-scope `print()` statements run during import and corrupt the stream before a single tool call is made.

**Consequences:**
- MCP client receives garbled output, drops the connection, shows "server disconnected" with no useful error.
- Extremely hard to debug because the corruption happens before any tool runs.

**Prevention:**
```python
# ✅ In the MCP server file: redirect all logging to stderr before any imports
import sys
import logging
logging.basicConfig(stream=sys.stderr, level=logging.INFO)

# ✅ In tool code: never use print() — use ctx.log() or logging
@mcp.tool
def list_companies(ctx: Context) -> list[dict]:
    """List all companies from the database."""
    ctx.log("info", "Fetching companies")  # Goes to MCP logging protocol
    # logging.info("Fetching")  # Goes to stderr — safe for stdio
    ...

# ❌ Wrong
@mcp.tool
def list_companies() -> list[dict]:
    print("Fetching companies")  # CORRUPTS STDOUT PROTOCOL STREAM
    ...
```

**Detection:**
Run the MCP server manually: `python mcp_server.py`. If it prints anything to stdout before you send a request, that's a corruption source. All startup output must go to stderr.

---

### MCP-2: Two Processes, One SQLite File — Default Journal Mode Causes `SQLITE_BUSY`

**Feature:** MCP server (standalone process) sharing the SQLite DB with the FastAPI app
**Phase:** MCP Server phase

**What goes wrong:**
The MCP server runs as a **separate OS process** (stdio transport spawns a subprocess per client session). Both the FastAPI app and the MCP server create their own SQLAlchemy engines pointing at the same `data/companies.db` file. SQLite's default journal mode is `delete` (rollback journal). Under this mode, a write from one process acquires an exclusive lock on the entire file. Any concurrent read from the other process fails with `OperationalError: database is locked (SQLITE_BUSY)`.

**Verified:** Live test confirmed:
```
Default journal mode: delete
Two processes writing concurrently → SQLITE_BUSY
```

**Why it happens:**
The v1.0 app was designed as single-process. `check_same_thread=False` fixes the threading issue within one process, but it does nothing for cross-process locking.

**Prevention:**
Enable WAL (Write-Ahead Logging) mode on the engine. WAL allows **multiple concurrent readers + one writer** without locking conflicts:

```python
# In mcp_server.py — create its own engine pointing to the SAME file
from sqlmodel import create_engine
from sqlalchemy import event

_DB_PATH = Path(__file__).resolve().parent / "data" / "companies.db"
engine = create_engine(
    f"sqlite:///{_DB_PATH}",
    connect_args={"check_same_thread": False},
)

# Enable WAL mode once at engine creation — persists in the DB file
@event.listens_for(engine, "connect")
def set_wal_mode(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()
```

Add the same WAL pragma to `app/database.py` so both processes use WAL consistently.

**Important:** MCP server must create its **own engine** — it cannot share `app.database.engine` because they are in different OS processes (no shared memory). Importing `from app.database import engine` in the MCP server creates a new engine in the MCP process, which is correct behavior.

---

### MCP-3: FastMCP v3 Constructor Rejects Transport Arguments — Old Tutorials Break

**Feature:** MCP server
**Phase:** MCP Server phase

**What goes wrong:**
FastMCP 3.x (current version: 3.2.0) **removed transport settings from the constructor**. Code written following FastMCP 1.x/2.x tutorials will fail with `TypeError` immediately:

```python
# ❌ FastMCP v2 pattern — CRASHES in v3 with TypeError
mcp = FastMCP("Companies", host="127.0.0.1", port=9000)

# ✅ FastMCP v3 pattern — transport settings go in run()
mcp = FastMCP("Companies")
mcp.run(transport="http", host="127.0.0.1", port=9000)
```

The SSE transport is also **deprecated in v3** — use `stdio` (for Claude Desktop) or `http` (for network access).

**Other v3 breaking changes that affect this project:**
- `@mcp.tool` decorated functions return the original function (not a component object) — don't access `.name` on the result
- `on_duplicate_tools`, `on_duplicate_resources` kwargs removed — use `on_duplicate=` unified param

**Prevention:**
Pin to `fastmcp>=3.0.0,<4` in requirements and follow gofastmcp.com docs (not older tutorials). Use this boilerplate:

```python
from fastmcp import FastMCP

mcp = FastMCP("Company Research MCP")

if __name__ == "__main__":
    mcp.run()  # stdio by default — correct for Claude Desktop
```

---

### MCP-4: Importing `app.models` in the MCP Process Triggers FastAPI Startup Side Effects

**Feature:** MCP server importing shared models from the FastAPI app
**Phase:** MCP Server phase

**What goes wrong:**
The MCP server needs the `Company` SQLModel class for type annotations. The natural import is `from app.models import Company`. However, `app/models.py` may import from `app/database.py`, which creates the SQLAlchemy engine at module scope and calls `create_db_and_tables()`. In the MCP process this runs during import — creating the database file if it doesn't exist, which is harmless, but also **failing if `OPENAI_API_KEY` is required** by `app/config.py` at import time.

The existing `app/config.py` creates `settings = Settings()` at module scope, which reads `OPENAI_API_KEY` from the environment. If the MCP server process doesn't have `OPENAI_API_KEY` set (it doesn't need it — the MCP server is read-only), the import crashes.

**Prevention:**
Keep `app/models.py` free of startup side-effects — it currently is (good). The issue is `app/config.py`'s module-level `settings = Settings()`. If the import chain reaches it, it will fail.

**Two safe patterns:**
```python
# Option A: Copy just the Company model definition into mcp_server.py (no app imports)
# Best for keeping MCP fully standalone

# Option B: Import only models, not config
from app.models import Company  # Safe if models.py doesn't import config.py
# Don't import from app.config in the MCP server — it needs OPENAI_API_KEY
```

---

### FILTER-1: Empty String Query Param Is NOT None — Triggers Unintended `WHERE` Clause

**Feature:** `GET /companies?industry=` filtering
**Phase:** Filtering phase

**What goes wrong:**
FastAPI passes an empty string `""` when the client sends `?industry=` (param present but empty). The value is `not None`, so a guard like `if industry is not None:` triggers and runs `WHERE industry = ""`, which returns **zero results**. Users sending `?industry=` intend "no filter" but get an empty list.

**Verified:** Live test confirmed:
```
GET /companies?industry=  →  Count: 0 (empty string treated as real filter)
```

**Prevention:**
```python
# ❌ Wrong — empty string passes the None check
@app.get("/companies")
def list_companies(industry: Optional[str] = None):
    if industry is not None:  # "" is not None!
        query = query.where(Company.industry == industry)

# ✅ Correct — treat both None AND empty string as "no filter"
@app.get("/companies")
def list_companies(industry: Optional[str] = None):
    if industry:  # Falsy check: rejects None, "", "   "
        query = query.where(Company.industry == industry.strip())
```

---

### FILTER-2: LIKE Wildcard Characters `%` and `_` in Search Input Match Unintended Records

**Feature:** `GET /companies?q=` text search
**Phase:** Filtering phase

**What goes wrong:**
SQLModel's `.contains(value)` translates to `LIKE '%value%'`. If `value` itself contains `%` (matches any sequence) or `_` (matches any single character), those are treated as LIKE wildcards, not literal characters.

**Verified:**
```
GET /companies?q=%   →  All 3 companies returned (% = wildcard)
GET /companies?q=_   →  All 3 companies returned (_ = single char wildcard)
```

This is not SQL injection in the traditional sense (parameterized queries prevent SQL injection), but it is **unintended result set expansion** — a `q=%` search returns everything.

**Prevention:**
Escape LIKE special characters before calling `.contains()`:

```python
def escape_like(value: str) -> str:
    """Escape LIKE wildcards in user-provided search strings."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

@app.get("/companies")
def list_companies(q: Optional[str] = None):
    if q:
        safe_q = escape_like(q.strip())
        # Use ilike for case-insensitive (SQLAlchemy handles escaping with escape param)
        query = query.where(Company.company_name.ilike(f"%{safe_q}%", escape="\\"))
```

**Note on SQLite case sensitivity:** SQLite's `LIKE` is case-insensitive for ASCII by default (verified: `q=acme` matches "Acme SaaS"). This is good UX. Use `ilike` in your code to make the intent explicit and portable.

---

### HASH-1: `SQLModel.metadata.create_all()` Does NOT Add New Columns to Existing Tables

**Feature:** `description_hash` column added to the `Company` model
**Phase:** AI Caching phase

**What goes wrong:**
Adding `description_hash: Optional[str] = None` to the `Company` SQLModel class and calling `create_db_and_tables()` (which calls `SQLModel.metadata.create_all(engine)`) does **nothing** for an already-existing table. `create_all` only creates tables that don't exist yet — it never alters existing schema.

**Verified:**
```
# Added description_hash to Company model, ran create_all again
ERROR: (sqlite3.OperationalError) no such column: company.description_hash
```

No error is raised by `create_all` — it silently skips the existing table. The error appears later, at query time.

**Prevention:**
Write an idempotent migration script that runs at startup (or as a one-off):

```python
# scripts/migrate_add_hash.py  (or inline in database.py create_db_and_tables)
from sqlalchemy import text
from app.database import engine

def add_description_hash_column():
    """Idempotent: adds description_hash column only if it doesn't exist."""
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(company)"))
        existing_cols = [row[1] for row in result]
        
        if "description_hash" not in existing_cols:
            conn.execute(text(
                "ALTER TABLE company ADD COLUMN description_hash TEXT"
            ))
            conn.commit()
            print("Migration: added description_hash column")
        else:
            print("Migration: description_hash already exists, skipping")

if __name__ == "__main__":
    add_description_hash_column()
```

Call this migration before running the app or pipeline. The `PRAGMA table_info` check makes it safe to run multiple times.

---

### HASH-2: SQLModel ORM Object and DB Schema Must Be Updated in the Same Deployment Step

**Feature:** `description_hash` column
**Phase:** AI Caching phase

**What goes wrong:**
If the migration runs (column added to DB) but the `Company` SQLModel class doesn't yet include `description_hash`, every ORM query that touches a `Company` instance raises:
```
AttributeError: 'Company' object has no attribute 'description_hash'
```

Conversely, if the class is updated but the migration hasn't run:
```
OperationalError: no such column: company.description_hash
```

Both failures are silent during development if you're not testing against a production-equivalent database.

**Verified:** Both scenarios confirmed live.

**Prevention:**
Make the migration run **at app startup**, not as a separate step:

```python
# app/database.py
def create_db_and_tables() -> None:
    """Create tables and run pending schema migrations."""
    SQLModel.metadata.create_all(engine)
    _run_migrations()

def _run_migrations() -> None:
    """Apply any pending column additions. Idempotent."""
    with engine.connect() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(company)"))]
        if "description_hash" not in cols:
            conn.execute(text("ALTER TABLE company ADD COLUMN description_hash TEXT"))
            conn.commit()
```

This guarantees: class field exists ↔ DB column exists, because they're deployed together.

---

### HASH-3: `None` Description Crashes SHA-256 Hashing — Hash Empty Descriptions Consistently

**Feature:** AI caching via `description_hash`
**Phase:** AI Caching phase

**What goes wrong:**
The existing `Company` model has `description: str` (required), but the v1.0 scraper uses a fallback chain that may store a placeholder string. If `description` is ever `None` (or you change it to `Optional[str]`), calling `.encode()` on it crashes:

```python
description_hash = hashlib.sha256(company.description.encode("utf-8")).hexdigest()
# AttributeError: 'NoneType' object has no attribute 'encode'
```

Also: an empty description `""` produces a valid hash (`e3b0c44...`) but caching against it means "skip AI analysis for this empty record" — almost certainly wrong behavior.

**Verified:** `None.encode()` → `AttributeError`. Empty string → valid 64-char hex hash.

**Prevention:**
```python
import hashlib

def compute_description_hash(description: Optional[str]) -> Optional[str]:
    """
    Returns SHA-256 hex digest of description.encode('utf-8').
    Returns None if description is None or empty (treat as uncacheable).
    Always strip() before hashing to prevent whitespace drift.
    """
    if not description or not description.strip():
        return None
    normalized = description.strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
```

The `.strip()` call prevents two identical descriptions with different trailing whitespace from having different hashes (a subtle cache miss bug).

---

### STATIC-1: Mounting `StaticFiles` at `/` Before API Routes Makes All Routes Return 404

**Feature:** Static frontend served via FastAPI
**Phase:** Frontend phase

**What goes wrong:**
`StaticFiles` mounts act as a catch-all router — they intercept ALL paths under the mount prefix. Mounting at `/` before your API routes are registered means the static mount claims all paths first, so `GET /api/companies` returns a 404 from the static file handler (file not found), not from FastAPI routing.

**Verified:**
```python
app.mount("/", StaticFiles(directory="frontend", html=True))
@app.get("/api/companies")  # Registered AFTER mount — 404!
def companies(): ...

# GET /api/companies → 404 (static file handler can't find /api/companies file)
```

**Prevention — Option A (recommended): Mount at `/static`, prefix all API routes with `/api`**
```python
# Cleanest separation:
app.include_router(companies_router, prefix="/api")
app.mount("/static", StaticFiles(directory="frontend/dist"), name="static")
# Serve index.html explicitly for SPA root:
@app.get("/")
def serve_spa():
    return FileResponse("frontend/dist/index.html")
```

**Prevention — Option B: Mount `/` LAST (after all route definitions)**
```python
# Define all API routes first
@app.get("/api/companies")
def companies(): ...

# Mount static files AFTER — routes registered first take priority
app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="static")
# GET /api/companies → 200 ✅ (API route matches before static catch-all)
```

**Verified:** Option B works — API routes registered before the static mount return 200 correctly.

---

### STATIC-2: Frontend Directory Must Exist at FastAPI Startup — No Graceful Fallback

**Feature:** Static frontend
**Phase:** Frontend phase

**What goes wrong:**
If the `frontend/dist` (or `frontend/`) directory doesn't exist at the time FastAPI starts (e.g., the frontend hasn't been built, the directory is gitignored, or you're running in CI without building), `StaticFiles` raises:

```
RuntimeError: Directory 'frontend/dist' does not exist
```

This crashes the **entire** FastAPI application startup — not just the static files. The REST API becomes unavailable.

**Why it matters:** In v1.1, CI may run API tests without building the frontend. The MCP server tests have no frontend dependency. A missing `frontend/dist` shouldn't break the API.

**Prevention:**
Make the static files mount conditional:

```python
import os
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

# Only mount if the directory exists (dev/CI without frontend build is OK)
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")
else:
    @app.get("/")
    def no_frontend():
        return {"message": "Frontend not built. Run: npm run build"}
```

---

### STATIC-3: SPA Client-Side Routes Return 404 on Direct URL Access

**Feature:** Static frontend (if it's a single-page application)
**Phase:** Frontend phase

**What goes wrong:**
A single-page app (React, Vue, plain JS with client-side routing) handles routes like `/companies/123` in JavaScript. If a user navigates directly to `http://localhost:8000/companies/123` (or refreshes the page), FastAPI looks for a static file at `frontend/dist/companies/123` — which doesn't exist — and returns 404.

**Why `html=True` doesn't fully fix this:**
`StaticFiles(html=True)` serves `index.html` for directory roots (e.g., `/`) but NOT for paths that look like files with no extension or don't match a real file.

**Prevention:**
Add a catch-all route that serves `index.html` for any unmatched path:

```python
from fastapi.responses import FileResponse

@app.get("/{full_path:path}")
async def serve_spa_fallback(full_path: str):
    """Serve index.html for any unmatched path (SPA client-side routing)."""
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"error": "Frontend not found"}
```

Register this route LAST, after all API routes.

---

### CI-1: `pull_request` Workflows from Forks Get Read-Only `GITHUB_TOKEN` — Agentic Reviewer Cannot Post Comments

**Feature:** GitHub Actions CI with agentic code review
**Phase:** CI/CD phase

**What goes wrong:**
When a fork opens a PR, GitHub runs the `pull_request` workflow in the **fork's repository context** with a read-only `GITHUB_TOKEN`. The agentic reviewer (Copilot, Claude, or a custom bot) needs `pull-requests: write` permission to post review comments. The workflow silently exits with `Resource not accessible by integration (403)` — no review comment appears.

**Prevention:**
Declare permissions explicitly in the workflow. For PRs from the same repo (not forks):

```yaml
# .github/workflows/review.yml
name: Agentic Code Review

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  pull-requests: write
  contents: read

jobs:
  review:
    # Skip draft PRs (see CI-2) and fork PRs (no write token)
    if: |
      github.event.pull_request.draft == false &&
      github.event.pull_request.head.repo.full_name == github.repository
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      ...
```

The `head.repo.full_name == github.repository` condition skips fork PRs entirely rather than failing silently.

---

### CI-2: Draft PRs Trigger Agentic Review Workflows — Wastes API Credits

**Feature:** GitHub Actions agentic code review
**Phase:** CI/CD phase

**What goes wrong:**
`pull_request` events trigger on draft PRs by default (event type `draft` is included in `opened`). An agentic reviewer (using OpenAI or Anthropic APIs) runs on every draft update, burning API credits on code that isn't ready for review.

**Prevention:**
Filter by `pull_request.draft == false`:

```yaml
jobs:
  review:
    if: github.event.pull_request.draft == false
    ...
```

Or handle it via `types` + draft status check — `ready_for_review` type event triggers when a draft is promoted:

```yaml
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
jobs:
  review:
    if: github.event.pull_request.draft == false
```

---

### CI-3: `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` Secrets Are Not Passed to Fork PR Workflows

**Feature:** Agentic code review using OpenAI/Anthropic API
**Phase:** CI/CD phase

**What goes wrong:**
GitHub explicitly blocks repository secrets from being passed to workflows triggered by fork PRs (by design — prevents secret exfiltration). If your agentic review calls the OpenAI/Anthropic API, the key is missing and the workflow fails. Worse, if the failure isn't handled, the review job may silently succeed (exit 0) while the actual review never ran.

**Why this matters for this project:** The main `OPENAI_API_KEY` used by the pipeline is the same one needed for agentic review. Mixing pipeline secrets with CI secrets creates dependency confusion.

**Prevention:**
1. Only run agentic review on same-repo PRs (see CI-1 condition)
2. Explicitly fail if the required secret is missing, to make the problem visible:

```yaml
- name: Verify API key is available
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  run: |
    if [ -z "$OPENAI_API_KEY" ]; then
      echo "::error::OPENAI_API_KEY secret is not set. Agentic review skipped."
      exit 1
    fi
```

3. Add the key to GitHub repo Settings → Secrets and variables → Actions → Repository secrets (not environment secrets, which don't apply to PR workflows).

---

### CI-4: Agentic Review Bot Can Trigger Itself in an Infinite Loop

**Feature:** Agentic code review automation
**Phase:** CI/CD phase

**What goes wrong:**
If the code review bot uses a **Personal Access Token (PAT)** or a **GitHub App token** (rather than the default `GITHUB_TOKEN`) to post comments, its PR comments can trigger subsequent `pull_request_review` or `issue_comment` workflows — including the review workflow itself. This creates an infinite loop of reviews.

The default `GITHUB_TOKEN` has built-in loop prevention (workflows triggered by `GITHUB_TOKEN` don't trigger further workflows). A PAT or App token does not have this protection.

**Prevention:**
- Use `GITHUB_TOKEN` (not a PAT) for posting review comments when possible
- Add a bot-actor guard as a second line of defense:

```yaml
jobs:
  review:
    if: |
      github.actor != 'github-actions[bot]' &&
      github.actor != 'copilot-code-review[bot]' &&
      github.event.pull_request.draft == false
```

---

### CI-5: Missing `pull-requests: write` Permission on Newer GitHub Repos (Default Deny)

**Feature:** GitHub Actions CI
**Phase:** CI/CD phase

**What goes wrong:**
Repositories created after late 2023 default to **restricted permissions** — `GITHUB_TOKEN` only gets `contents: read`. Any step that calls the GitHub API to post a review, create a comment, or update a check run fails silently with `403 Resource not accessible by integration`.

This affects: Copilot code review actions, custom review bots, status check reporters, and any `gh pr comment` calls.

**Prevention:**
Always declare permissions explicitly in every workflow that interacts with the PR:

```yaml
permissions:
  contents: read       # checkout
  pull-requests: write # post review comments
  checks: write        # update check run status (if used)
```

Or set a permissive default at the repo level (Settings → Actions → General → Workflow permissions → "Read and write permissions") — but explicit per-workflow declarations are safer and clearer.

---

## v1.1 Phase-Specific Warnings

| Phase | Feature | Pitfall ID | Likely Problem | Prevention |
|-------|---------|-----------|---------------|------------|
| MCP Server | FastMCP stdio | MCP-1 | `print()` in tool code corrupts JSON-RPC stream | Use `ctx.log()` or `logging` to stderr |
| MCP Server | Two-process SQLite | MCP-2 | `SQLITE_BUSY` on concurrent access | Enable WAL mode on both engines |
| MCP Server | FastMCP v3 | MCP-3 | Transport args in constructor → TypeError | Move host/port to `mcp.run(transport=...)` |
| MCP Server | Shared app imports | MCP-4 | `OPENAI_API_KEY` required at import → crash in MCP process | Keep MCP server self-contained, don't import `app.config` |
| Filtering | Empty string param | FILTER-1 | `?industry=` returns 0 results instead of all | Use falsy check `if industry:` not `if industry is not None:` |
| Filtering | LIKE injection | FILTER-2 | `?q=%` matches all records | Escape `%` and `_` before `.contains()` call |
| AI Caching | Schema migration | HASH-1 | `create_all()` silently skips column addition | Write idempotent `ALTER TABLE` + `PRAGMA table_info` check |
| AI Caching | ORM/DB sync | HASH-2 | Class updated but migration not run (or vice versa) = crash | Run migration inside `create_db_and_tables()` at startup |
| AI Caching | None description | HASH-3 | `None.encode()` → `AttributeError` | Guard: `if not description: return None` |
| Frontend | Mount order | STATIC-1 | `StaticFiles("/")` before routes → all API routes 404 | Mount static files LAST, or use `/static` prefix |
| Frontend | Missing dist dir | STATIC-2 | `frontend/dist` not built → FastAPI startup crash | Conditional mount: `if FRONTEND_DIR.exists():` |
| Frontend | SPA routing | STATIC-3 | Direct URL to `/companies/123` returns 404 | Add `/{full_path:path}` catch-all serving `index.html` |
| CI/CD | Fork PR token | CI-1 | Read-only GITHUB_TOKEN on fork PRs → silent 403 | Condition: `head.repo.full_name == github.repository` |
| CI/CD | Draft PRs | CI-2 | Agentic review runs on every draft commit | Condition: `pull_request.draft == false` |
| CI/CD | Secrets on forks | CI-3 | `OPENAI_API_KEY` missing on fork workflows | Same-repo-only condition + explicit secret validation |
| CI/CD | Bot loop | CI-4 | Bot PAT triggers workflow loop | Use `GITHUB_TOKEN`; add bot-actor guard |
| CI/CD | Permissions | CI-5 | New repos deny `pull-requests: write` by default | Explicit `permissions:` block in every workflow |

---

## v1.1 Sources

| Claim | Confidence | How Verified |
|-------|------------|--------------|
| FastMCP stdio uses stdout as JSON-RPC channel | HIGH | Official FastMCP docs (gofastmcp.com/deployment/running-server) + MCP spec |
| FastMCP current version is 3.2.0 (PrefectHQ) | HIGH | `pip install fastmcp --dry-run` confirmed 3.2.0 |
| FastMCP v3 removed transport args from constructor | HIGH | Official upgrade guide (gofastmcp.com/getting-started/upgrading/from-fastmcp-2) |
| Default SQLite journal mode is `delete` | HIGH | Live test: `PRAGMA journal_mode` returned `delete` |
| WAL mode allows concurrent reads + writes | HIGH | Live test: WAL enabled, two engines confirmed |
| `create_all()` silently skips existing table columns | HIGH | Live Python test: `OperationalError: no such column` after class update + `create_all()` |
| ORM AttributeError when class not updated | HIGH | Live Python test: `'Company' object has no attribute 'description_hash'` |
| `None.encode()` raises AttributeError | HIGH | Live Python test confirmed |
| Empty string `?industry=` is not None in FastAPI | HIGH | Live TestClient test: `Count: 0` with `?industry=` |
| `.contains("%")` matches all records (LIKE wildcard) | HIGH | Live TestClient test: `Count: 3` with `?q=%25` |
| SQLite LIKE is case-insensitive for ASCII | HIGH | Live test: `q=acme` matched "Acme SaaS" |
| `StaticFiles("/")` before routes → 404 | HIGH | Live FastAPI TestClient test confirmed |
| `StaticFiles("/")` after routes → works | HIGH | Live FastAPI TestClient test confirmed |
| Fork PR `GITHUB_TOKEN` is read-only | HIGH | GitHub official docs (automatic-token-authentication) |
| GitHub secrets not passed to fork PR workflows | HIGH | GitHub security model, officially documented |
| Draft PRs trigger `pull_request` by default | MEDIUM | GitHub Actions docs (events-that-trigger-workflows); `github.event.pull_request.draft` field verified |
| New repos default to restricted GITHUB_TOKEN permissions | MEDIUM | Training data (post-2023 default change); verify at repo Settings → Actions |

---

---

## v1.0 Pitfalls (Original)

> These pitfalls apply to the base v1.0 system. Retained for reference.

---

## Critical Pitfalls

Mistakes that cause broken builds, silent data loss, or complete rewrites.

---

### Pitfall 1: Scraping the YC HTML Page Instead of Using the API

**Phase:** Data Collection

**What goes wrong:**
`ycombinator.com/companies` is a JavaScript-rendered React SPA. A `requests.get()` call returns an 18KB HTML shell with zero company data — no names, no descriptions, nothing. Every attempt to parse it with BeautifulSoup returns empty results, with no error to tell you why.

**Verified:** Live request to `ycombinator.com/companies` confirmed: `Has company data in first 5k: False`. Page is pure React bootstrapping JS.

**Why it happens:**
It looks like a normal webpage. Developers try `requests + BeautifulSoup` first because it's the obvious Python scraping stack. The page returns 200 OK, so there's no immediate signal that it failed.

**Consequences:**
- Zero data collected. Silent failure if you're not asserting results.
- You pivot to Playwright/Selenium (adds heavy browser dependency, slower, harder to run headlessly on CI).

**Prevention:**
Use the undocumented but stable public JSON API instead:
```
GET https://api.ycombinator.com/v0.1/companies?page=1
```
Returns structured JSON: 25 companies per page, 234 total pages (~5,850 companies).
Fields: `id`, `name`, `slug`, `website`, `oneLiner`, `longDescription`, `teamSize`, `batch`, `tags`, `industries`, `status`, `locations`.

**Detection:** After fetching, assert `len(soup.find_all('div', class_=...)) > 0` — you'll get 0 and catch this immediately.

---

### Pitfall 2: SQLite `check_same_thread` Error Crashing FastAPI

**Phase:** API / Database Layer

**What goes wrong:**
SQLite's default Python binding raises `ProgrammingError: SQLite objects created in a thread can only be used in that same thread` the moment a second concurrent request arrives. FastAPI routes run across a thread pool — the connection created at startup will almost always be used from a different thread.

**Verified:** Live test confirmed exact error: `ProgrammingError: SQLite objects created in thread id X and this is thread id Y`.

**Why it happens:**
SQLite's Python binding enforces single-thread use by default as a safety guard. FastAPI with `uvicorn` uses a thread pool for sync routes and the event loop for async routes — neither guarantees same-thread execution.

**Consequences:**
- API works fine in single-threaded testing, crashes under any real load (even two concurrent browser tabs).
- The error is not obvious — it surfaces as a 500 with a cryptic SQLAlchemy/sqlite3 traceback.

**Prevention:**
Two required fixes together:
```python
# 1. Create engine with check_same_thread disabled
engine = create_engine(
    "sqlite:///./companies.db",
    connect_args={"check_same_thread": False}
)

# 2. Use per-request sessions via FastAPI Depends (NOT a global session)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/companies")
def list_companies(db: Session = Depends(get_db)):
    return db.query(Company).all()
```

**Detection:** Run two requests simultaneously against the API. If you get `ProgrammingError`, this pitfall is active.

---

### Pitfall 3: Shared SQLAlchemy Session Across Requests

**Phase:** API / Database Layer

**What goes wrong:**
Using a single global `Session` object (e.g., `db = SessionLocal()` at module level, reused in all routes) causes `InvalidRequestError: This session is provisioning a new connection; concurrent operations are not permitted`.

**Verified:** Live test with 5 concurrent threads sharing one session: 3 of 5 failed with `InvalidRequestError` (exact error message confirmed).

**Why it happens:**
SQLAlchemy sessions are not thread-safe. They maintain internal state (pending writes, identity map) that becomes corrupted under concurrent access, even with `check_same_thread=False` on the SQLite engine.

**Consequences:**
- Data corruption risk — writes from one request bleed into another's transaction.
- Random 500 errors that only appear under concurrent load, making them hard to reproduce.

**Prevention:**
Always use `Depends(get_db)` with a session factory pattern (see Pitfall 2 above). Never import or reuse a session instance across route handlers.

---

### Pitfall 4: Pydantic v2 `orm_mode` and `validator` Silent Deprecations

**Phase:** API / Schema Definition

**What goes wrong:**
The installed Pydantic is **v2.12.5**. Pydantic v1 patterns still run but emit deprecation warnings (or silently misbehave):
- `class Config: orm_mode = True` → renamed to `model_config = ConfigDict(from_attributes=True)`
- `@validator` → renamed to `@field_validator` with different signature
- `.dict()` → renamed to `.model_dump()`
- `.json()` → renamed to `.model_dump_json()`

**Verified:** Live test confirmed v2.12.5 installed. `orm_mode` emits: `UserWarning: Valid config keys have changed in V2: 'orm_mode' has been renamed to 'from_attributes'`

**Why it happens:**
Tutorials and Stack Overflow answers are overwhelmingly v1 style. Pydantic v2 ships with a compatibility shim that silently accepts v1 syntax, so bugs only surface later (e.g., validators not firing, serialization behaving unexpectedly).

**Consequences:**
- `orm_mode` works but will break in Pydantic v3. More importantly, the compatibility shim can mask validator errors.
- `.dict()` still works but is deprecated — mixing v1/v2 patterns in the same codebase is a maintenance landmine.

**Prevention:**
Write v2-native from the start:
```python
from pydantic import BaseModel, ConfigDict, field_validator

class CompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    industry: str

    @field_validator("industry")
    @classmethod
    def normalize_industry(cls, v: str) -> str:
        return v.strip().title()
```

---

### Pitfall 5: OpenAI JSON Mode Without Schema Enforcement

**Phase:** AI Analysis

**What goes wrong:**
Using `response_format={"type": "json_object"}` (JSON mode) instructs the model to return valid JSON but does NOT enforce a specific schema. The model can:
- Return different field names on different runs (`"industry"` vs `"Industry"` vs `"sector"`)
- Omit fields entirely when it's uncertain
- Return extra fields not in your schema
- Use inconsistent value vocabularies (`"SaaS"` vs `"B2B SaaS"` vs `"Software"`)

**Why it happens:**
JSON mode = syntactic guarantee (valid JSON). Structured Outputs = semantic guarantee (matches your schema). These are different features. gpt-4o-mini is more prone to schema drift than gpt-4o.

**Consequences:**
- `KeyError` crashes when accessing `.get("industry")` on a response that returned `"sector"` instead.
- Inconsistent data in the database makes filtering/grouping unreliable.
- Hard to catch without asserting every field on every response.

**Prevention:**
Use Structured Outputs with a Pydantic model (OpenAI SDK >= 1.40):
```python
from pydantic import BaseModel
from openai import OpenAI

class CompanyAnalysis(BaseModel):
    industry: str
    business_model: str
    summary: str
    use_case: str

client = OpenAI()
response = client.beta.chat.completions.parse(
    model="gpt-4o-mini",
    messages=[...],
    response_format=CompanyAnalysis,
)
analysis = response.choices[0].message.parsed  # Typed Python object
```

**Detection:** Log raw response strings during development. Any response missing a required key or with an unexpected structure means JSON mode is insufficient.

---

### Pitfall 6: `@app.on_event("startup")` Is Deprecated

**Phase:** Application Bootstrap

**What goes wrong:**
`@app.on_event("startup")` and `@app.on_event("shutdown")` are deprecated in FastAPI (confirmed in v0.135.2). Using them emits a deprecation warning today and will be removed in a future version.

**Verified:** Live test confirmed exact warning: `DeprecationWarning: on_event is deprecated, use lifespan event handlers instead.`

**Why it happens:**
Every FastAPI tutorial written before 2023 uses `on_event`. It's the first result on most searches.

**Prevention:**
Use the `lifespan` context manager instead:
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create DB tables, validate config
    Base.metadata.create_all(bind=engine)
    validate_openai_key()
    yield
    # Shutdown: cleanup if needed

app = FastAPI(lifespan=lifespan)
```

---

## Moderate Pitfalls

Mistakes that cause bugs, poor data quality, or operational pain but not full breakage.

---

### Pitfall 7: No Handling for Empty `longDescription` from YC API

**Phase:** Data Collection / AI Analysis

**What goes wrong:**
**Verified:** 2 of 25 companies on page 1 have empty `longDescription`. That's ~8% of the dataset. Sending an empty string to GPT-4o-mini as the "company description to analyze" produces:
- Hallucinated business models based only on the company name
- Confidently wrong summaries
- Inconsistent behavior (sometimes returns errors, sometimes invents content)

**Prevention:**
Before calling OpenAI, apply a fallback chain:
```python
description = company.get("longDescription", "").strip()
if not description:
    description = company.get("oneLiner", "").strip()
if not description:
    description = f"Company: {company['name']}"  # Last resort

# Tag the analysis as low-confidence if built on fallback
used_fallback = not company.get("longDescription", "").strip()
```
Store a `confidence` field alongside AI-generated fields.

---

### Pitfall 8: No Retry Logic for OpenAI API Calls

**Phase:** AI Analysis (Batch Job)

**What goes wrong:**
The batch scraper runs all 10–50 API calls sequentially. Any transient error (network timeout, 429 rate limit, 503 service unavailable) aborts the entire batch. Without retry logic, you lose all work done after the last successful write.

**Why it happens:**
The happy path works fine in development. Rate limit errors only appear under load or after sustained usage.

**Prevention:**
Use `tenacity` for exponential backoff:
```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import RateLimitError, APIConnectionError, APITimeoutError

@retry(
    retry=retry_if_exception_type((RateLimitError, APIConnectionError, APITimeoutError)),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(4)
)
def analyze_company(description: str) -> CompanyAnalysis:
    ...
```
Also: commit each company to the database immediately after analysis, before moving to the next. This makes the batch job resumable.

---

### Pitfall 9: Inconsistent AI Field Values (Taxonomy Drift)

**Phase:** AI Analysis

**What goes wrong:**
Even with Structured Outputs enforcing field presence, `industry` values across 50 companies will look like: `"B2B SaaS"`, `"Enterprise Software"`, `"Developer Tools"`, `"SaaS"`, `"Software"`. These are semantically overlapping but syntactically different — grouping by industry returns noise.

**Why it happens:**
LLMs are generative — they produce the most contextually appropriate label, not the most consistent one. Without a closed vocabulary, values drift across calls.

**Prevention:**
Option A — Constrain via prompt (simpler):
```python
system_prompt = """
Classify the company. For 'industry', use ONLY one of:
B2B SaaS, Consumer, Fintech, Healthcare, Infrastructure,
Developer Tools, Marketplace, Hardware, Other
"""
```
Option B — Constrain via Pydantic enum (enforced by Structured Outputs):
```python
from enum import Enum

class Industry(str, Enum):
    b2b_saas = "B2B SaaS"
    consumer = "Consumer"
    fintech = "Fintech"
    # ...

class CompanyAnalysis(BaseModel):
    industry: Industry
```
Option B is more robust but requires you to define your taxonomy upfront.

---

### Pitfall 10: Blocking Sync Code in Async FastAPI Routes

**Phase:** API

**What goes wrong:**
Defining routes as `async def` while calling synchronous blocking code inside them (SQLAlchemy sync ORM, `time.sleep`, `requests.get`) blocks the entire event loop. All other requests queue behind the blocking operation.

**Why it happens:**
`async def` makes a function a coroutine, but `await` is required to yield control. Blocking calls never yield — they freeze the loop.

**Consequences:**
- Single slow DB query blocks all other requests.
- Appears as unexplained latency spikes in load testing.

**Prevention for this project:**
Since this is a simple CRUD API with SQLite (sync), use **sync route handlers** (plain `def`, not `async def`). FastAPI automatically runs them in a thread pool:
```python
# Correct for this project: sync def with sync SQLAlchemy
@app.get("/companies")
def list_companies(db: Session = Depends(get_db)):
    return db.query(Company).all()

# Only use async def if you're doing actual async I/O (aiohttp, async SQLAlchemy)
```

---

### Pitfall 11: SQLite File Path Breaks When Running from Different Directories

**Phase:** Database Layer

**What goes wrong:**
`create_engine("sqlite:///companies.db")` creates the file relative to the **current working directory** at process startup. Running `python scraper.py` from `/project/scripts/` creates `companies.db` in `/project/scripts/`, but `uvicorn app:app` from `/project/` looks for it in `/project/`. Two different database files, zero data sharing.

**Prevention:**
Always resolve the path relative to the module file:
```python
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATABASE_URL = f"sqlite:///{BASE_DIR}/companies.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
```

---

## Minor Pitfalls

Small mistakes that cause confusion but are easy to fix.

---

### Pitfall 12: Missing `.env` Validation at Startup

**Phase:** Configuration / Bootstrap

**What goes wrong:**
If `OPENAI_API_KEY` is missing, the scraper runs through all 50 companies collecting data, only to fail on the first API call. All scraping work is lost (unless you persisted raw data before analysis).

**Prevention:**
Validate required env vars at the very start of the script, before any work begins:
```python
import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set. Add it to .env or environment.")
```
Also: commit a `.env.example` with placeholder values so the setup is self-documenting.

---

### Pitfall 13: Not Rate-Limiting YC API Requests

**Phase:** Data Collection

**What goes wrong:**
Rapid-fire requests to `api.ycombinator.com` without any delay risk triggering rate limiting or temporary IP blocks. While the API is currently permissive (tested: 3 rapid requests succeed), aggressive scraping without courtesy delays is fragile.

**Prevention:**
Add a 0.5–1 second delay between page requests:
```python
import time
for page in range(1, num_pages + 1):
    data = fetch_page(page)
    process(data)
    time.sleep(0.5)  # Be a polite scraper
```
At 0.5s/page, 10 pages (250 companies) takes 5 seconds — negligible.

---

### Pitfall 14: YC API Pagination — `nextPage` URL, Not Page Numbers

**Phase:** Data Collection

**What goes wrong:**
Assuming you can construct page URLs as `?page=1`, `?page=2`... works today, but the API explicitly provides `nextPage` and `prevPage` URLs in the response. Using the provided cursor URLs is more robust against API changes.

**Verified:** Response includes `{"nextPage": "https://api.ycombinator.com/v0.1/companies?page=3", "prevPage": "...", "page": 2, "totalPages": 234}`.

**Prevention:**
Follow the pagination cursor instead of incrementing page numbers:
```python
url = "https://api.ycombinator.com/v0.1/companies?page=1"
while url:
    data = requests.get(url).json()
    process(data["companies"])
    url = data.get("nextPage")  # None on last page
```

---

## Phase-Specific Warnings

| Phase | Topic | Likely Pitfall | Mitigation |
|-------|-------|---------------|------------|
| Data Collection | YC scraping approach | Scraping HTML instead of using JSON API | Use `api.ycombinator.com/v0.1/companies` directly |
| Data Collection | Pagination | Hardcoding page count or using wrong URL pattern | Follow `nextPage` cursor from API response |
| Data Collection | Missing data | Empty `longDescription` (~8% of companies) | Fallback chain: `longDescription` → `oneLiner` → name |
| AI Analysis | Schema reliability | JSON mode returns inconsistent fields | Use Structured Outputs with Pydantic model |
| AI Analysis | Value taxonomy | `industry` values are inconsistent across calls | Closed vocabulary in prompt or Pydantic enum |
| AI Analysis | Batch failure | No retry on transient API errors | `tenacity` with exponential backoff |
| Database | Threading | SQLite `check_same_thread` crash | `connect_args={"check_same_thread": False}` |
| Database | Sessions | Shared global session causes concurrent request errors | `Depends(get_db)` per-request session factory |
| Database | File path | Relative path creates DB in wrong directory | `Path(__file__).parent / "companies.db"` |
| API | Route type | `async def` with sync blocking code | Use `def` (not `async def`) for sync SQLAlchemy routes |
| API | Startup events | `@app.on_event` deprecated in FastAPI 0.135.2 | Use `lifespan` context manager |
| API | Pydantic schema | v1 `orm_mode` and `@validator` emit warnings | Write v2-native: `ConfigDict`, `field_validator` |
| Config | Environment | Missing API key only detected on first API call | Validate env vars at script start, before any work |

---

## Sources

| Claim | Confidence | How Verified |
|-------|------------|--------------|
| YC `/companies` page is JS-rendered with no data | HIGH | Live HTTP request, confirmed `Has company data in first 5k: False` |
| YC API at `api.ycombinator.com/v0.1/companies` returns JSON | HIGH | Live request, 200 OK, parsed JSON with 25 companies |
| YC API has `totalPages: 234`, 25 companies/page | HIGH | Live request, confirmed pagination envelope |
| ~8% of companies have empty `longDescription` | HIGH | 2/25 on page 1, confirmed live |
| SQLite `check_same_thread` causes `ProgrammingError` | HIGH | Live Python threading test, exact error message captured |
| SQLAlchemy shared session causes `InvalidRequestError` | HIGH | Live concurrency test, 3/5 threads failed |
| Pydantic version is 2.12.5, `orm_mode` deprecated | HIGH | `pip show pydantic` + live deprecation warning |
| FastAPI `@app.on_event` deprecated (v0.135.2) | HIGH | Live test, exact deprecation warning captured |
| OpenAI SDK 2.30.0 supports Structured Outputs | HIGH | SDK installed, `beta.chat.completions.parse` available |
| Cost for 50 companies ~$0.007 | MEDIUM | Calculated from published OpenAI pricing (subject to change) |
| gpt-4o-mini Tier 1 rate limit: 500 RPM, 200k TPM | MEDIUM | Training data; verify at platform.openai.com/docs/guides/rate-limits |
