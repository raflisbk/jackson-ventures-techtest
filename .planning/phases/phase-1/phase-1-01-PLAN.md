---
phase: phase-1
plan: "01"
type: execute
wave: 1
depends_on: []
files_modified:
  - requirements.txt
  - .env.example
  - .gitignore
  - README.md
  - app/__init__.py
  - app/config.py
  - app/models.py
  - app/database.py
  - scraper/__init__.py
  - agent/__init__.py
  - scripts/__init__.py
  - data/.gitkeep
autonomous: true
requirements: [CFG-01, CFG-02, DB-01, DB-02, DB-03, DB-04]

must_haves:
  truths:
    - "Importing app.database triggers automatic creation of data/companies.db and the company table — no manual migration step"
    - "Instantiating Settings without OPENAI_API_KEY in environment raises a ValidationError immediately with a clear message"
    - "DB file path is absolute (resolved via Path(__file__).resolve()) — same file regardless of which directory the process starts from"
    - "SQLite engine is created with check_same_thread=False and get_db() yields a per-call Session so multi-threaded access cannot raise ProgrammingError"
  artifacts:
    - path: "app/config.py"
      provides: "pydantic-settings Settings class — OPENAI_API_KEY (required, no default) + DATABASE_URL (default sqlite:///./data/companies.db)"
      exports: ["Settings", "settings"]
    - path: "app/models.py"
      provides: "SQLModel Company table class (unified ORM + Pydantic)"
      exports: ["Company"]
    - path: "app/database.py"
      provides: "SQLite engine with threading fix, get_db() session factory, create_db_and_tables()"
      exports: ["engine", "get_db", "create_db_and_tables"]
    - path: "requirements.txt"
      provides: "Pinned dependency list"
      contains: "sqlmodel==0.0.38, fastapi[standard]==0.135.3, pydantic-settings"
  key_links:
    - from: "app/database.py"
      to: "data/companies.db"
      via: "Path(__file__).resolve().parent.parent / 'data' / 'companies.db'"
      pattern: "Path\\(__file__\\)\\.resolve\\(\\)"
    - from: "app/database.py"
      to: "SQLite engine"
      via: "create_engine(..., connect_args={'check_same_thread': False})"
      pattern: "check_same_thread.*False"
    - from: "app/models.py"
      to: "app/database.py"
      via: "SQLModel.metadata.create_all(engine) called in create_db_and_tables()"
      pattern: "metadata\\.create_all"
---

<objective>
Build the complete project skeleton and all shared foundation modules that every downstream phase will import from.

Purpose: Phase 2 (scraper), Phase 3 (AI pipeline), and Phase 4 (API) all import from `app.config`, `app.models`, and `app.database`. These three files must be correct before any other work begins. Getting threading, path resolution, and fail-fast config right now prevents hard-to-debug failures in later phases.

Output:
- Project directory structure with all placeholder packages
- `requirements.txt` with pinned versions (live-verified 2026-04-07)
- `app/config.py` — pydantic-settings Settings with OPENAI_API_KEY fail-fast
- `app/models.py` — SQLModel Company table class
- `app/database.py` — engine (threading fix) + get_db() + create_db_and_tables()
- `.env.example`, `.gitignore`, `README.md`
</objective>

<execution_context>
@~/.copilot/get-shit-done/workflows/execute-plan.md
@~/.copilot/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/research/SUMMARY.md
@.planning/research/STACK.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Project Scaffold</name>
  <files>
    requirements.txt,
    .env.example,
    .gitignore,
    README.md,
    app/__init__.py,
    scraper/__init__.py,
    agent/__init__.py,
    scripts/__init__.py,
    data/.gitkeep
  </files>
  <action>
Create the following project structure from scratch. All directories and files are new.

**`requirements.txt`** — pin all versions exactly as live-verified 2026-04-07:
```
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

# HTTP (scraper, Phase 2)
requests==2.32.3

# Testing
pytest==9.0.2
httpx==0.28.1
```

Do NOT include playwright, beautifulsoup4, or lxml — the YC JSON API (api.ycombinator.com/v0.1/companies) requires only `requests`. See SUMMARY.md correction.

**`app/__init__.py`** — empty file (makes app/ a Python package)

**`scraper/__init__.py`** — one-line docstring: `"""YC JSON API scraper — implemented in Phase 2."""`

**`agent/__init__.py`** — one-line docstring: `"""OpenAI analysis pipeline — implemented in Phase 3."""`

**`scripts/__init__.py`** — one-line docstring: `"""CLI entrypoints — implemented in Phase 3."""`

**`data/.gitkeep`** — empty file (ensures data/ directory is tracked by git while keeping .db files gitignored)

**`.gitignore`**:
```
# Python
__pycache__/
*.py[cod]
*.pyo
.venv/
venv/
*.egg-info/
dist/
build/

# Environment
.env

# Database (generated at runtime — do not commit)
data/*.db

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db
```

**`.env.example`**:
```
# Copy this file to .env and fill in your values
# REQUIRED: Get from platform.openai.com/api-keys
OPENAI_API_KEY=your-openai-api-key-here

# OPTIONAL: Default shown below — change only if you want a different path
DATABASE_URL=sqlite:///./data/companies.db
```

**`README.md`**:
```markdown
# AI Company Research Agent

Automated pipeline: scrape YC startup data → AI analysis via OpenAI → SQLite storage → FastAPI REST API.

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate  |  Unix: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

## Usage

```bash
# Phase 2: Collect company data from YC JSON API
python scraper/yc_scraper.py

# Phase 3: Run AI analysis pipeline
python scripts/run_pipeline.py

# Phase 4: Start REST API
uvicorn app.main:app --reload
# Docs: http://localhost:8000/docs
```

## Stack

- `sqlmodel` — SQLite ORM + Pydantic schema (single Company class)
- `pydantic-settings` — typed config with fail-fast OPENAI_API_KEY validation
- `openai==2.30.0` — Structured Outputs via `beta.chat.completions.parse`
- `fastapi[standard]` — REST API with auto-generated docs
- `requests` — YC JSON API (`api.ycombinator.com/v0.1/companies`)
- `tenacity` — exponential backoff retry for OpenAI rate limits
```
  </action>
  <verify>
    <automated>python -c "import os; files = ['requirements.txt', '.env.example', '.gitignore', 'README.md', 'app/__init__.py', 'scraper/__init__.py', 'agent/__init__.py', 'scripts/__init__.py', 'data/.gitkeep']; missing = [f for f in files if not os.path.exists(f)]; print('MISSING:', missing) if missing else print('All scaffold files present')"</automated>
  </verify>
  <done>All 9 scaffold files exist. requirements.txt contains sqlmodel, fastapi[standard], pydantic-settings, openai, tenacity, requests, pytest. .gitignore excludes .env and data/*.db. No playwright/beautifulsoup4/lxml present in requirements.txt.</done>
</task>

<task type="auto">
  <name>Task 2: Core App Modules — config.py, models.py, database.py</name>
  <files>
    app/config.py,
    app/models.py,
    app/database.py
  </files>
  <action>
Create the three shared foundation modules. These files are imported by every downstream phase — implement them exactly as specified.

---

**`app/config.py`** — pydantic-settings with fail-fast OPENAI_API_KEY (per CFG-01, CFG-02):

```python
"""
Centralized application settings loaded from environment variables.
Uses pydantic-settings for typed config with automatic .env file support.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # REQUIRED — no default means pydantic-settings raises ValidationError
    # immediately if this key is absent from environment or .env file (per CFG-01)
    OPENAI_API_KEY: str

    # OPTIONAL — sensible default; absolute path resolution happens in database.py
    DATABASE_URL: str = "sqlite:///./data/companies.db"


# Module-level singleton — imported by database.py and agent/analyzer.py
settings = Settings()
```

**CRITICAL:** `OPENAI_API_KEY` has NO default. Pydantic-settings raises `pydantic_core.InitErrorDetails` (surfaced as `ValidationError`) at import time if the key is missing. This is the fail-fast behaviour required by CFG-01.

---

**`app/models.py`** — SQLModel Company table class (per DB-01, DB-03):

```python
"""
SQLModel Company table — single class serves as both the SQLAlchemy ORM table
and the Pydantic schema. Imported by database.py, scripts/run_pipeline.py,
and app/routers/companies.py.
"""
from typing import Optional
from sqlmodel import SQLModel, Field


class Company(SQLModel, table=True):
    """
    Stores one YC company record with both scraped fields (Phase 2)
    and AI-generated insight fields (Phase 3).
    """
    id: Optional[int] = Field(default=None, primary_key=True)

    # Scraped fields (populated in Phase 2)
    company_name: str
    description: str
    website: Optional[str] = None

    # AI-generated fields (populated in Phase 3)
    industry: Optional[str] = None
    business_model: Optional[str] = None
    summary: Optional[str] = None
    use_case: Optional[str] = None
```

Do NOT set `table=False` — that would make it a data-transfer object, not a DB table.
`id` must default to `None` so SQLite auto-assigns the primary key on insert.

---

**`app/database.py`** — engine with threading fix + session factory (per DB-02, DB-04):

```python
"""
SQLite database engine and session management.

Threading fix: SQLite's Python binding raises ProgrammingError when a
connection is used from a thread other than the one that created it.
Two fixes are required together:
  1. connect_args={"check_same_thread": False} — allows cross-thread use
  2. get_db() yields a NEW Session per call — no shared session state

Absolute path fix: "sqlite:///./data/companies.db" resolves relative to
CWD at process start — different paths when running from project root vs
scripts/ subdirectory. We build the absolute path from __file__ instead.
"""
from pathlib import Path
from sqlmodel import SQLModel, Session, create_engine

# Absolute path: app/database.py lives at <project_root>/app/database.py
# so parent.parent is the project root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = _PROJECT_ROOT / "data" / "companies.db"

# Ensure data/ directory exists (created on first import, before engine init)
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{_DB_PATH}"

# check_same_thread=False is required for FastAPI's threadpool (per DB-02)
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


def create_db_and_tables() -> None:
    """
    Create all SQLModel tables if they don't exist.
    Called at FastAPI startup (lifespan) and at the top of run_pipeline.py.
    No-op if tables already exist — safe to call multiple times (per DB-04).
    """
    SQLModel.metadata.create_all(engine)


def get_db():
    """
    FastAPI dependency that yields a fresh Session per request.
    Use with: db: Session = Depends(get_db)
    The with-block ensures the session is closed after the request
    even if an exception is raised (per DB-02).
    """
    with Session(engine) as session:
        yield session
```

**Do NOT** import `settings` from `app.config` in this file — the URL is computed from `__file__` directly to guarantee absolute path resolution regardless of what DATABASE_URL env var says. The env var default is a convenience for tooling; database.py always uses the absolute path.
  </action>
  <verify>
    <automated>python -c "
import sys, os
# Ensure OPENAI_API_KEY is set so Settings() doesn't fail during import check
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-placeholder')

from app.config import Settings, settings
from app.models import Company
from app.database import engine, get_db, create_db_and_tables, DATABASE_URL
from pathlib import Path

# Verify DATABASE_URL is absolute
assert Path(DATABASE_URL.replace('sqlite:///', '')).is_absolute(), f'DATABASE_URL not absolute: {DATABASE_URL}'

# Verify create_db_and_tables() works and creates the DB file
create_db_and_tables()
assert Path('data/companies.db').exists(), 'data/companies.db not created'

# Verify get_db() yields a session
db_gen = get_db()
session = next(db_gen)
print('Session type:', type(session).__name__)

print('All core module checks PASSED')
print('  - Settings imports OK')
print('  - Company model imports OK')  
print('  - DATABASE_URL is absolute:', DATABASE_URL)
print('  - data/companies.db created automatically')
print('  - get_db() yields Session successfully')
"
    </automated>
  </verify>
  <done>
    - app/config.py: Settings class with OPENAI_API_KEY (no default) and DATABASE_URL (default provided). Module-level `settings` singleton exported.
    - app/models.py: Company SQLModel table with id (PK), company_name, description, website, industry, business_model, summary, use_case.
    - app/database.py: engine created with check_same_thread=False, absolute DB path via Path(__file__).resolve(), create_db_and_tables() idempotent, get_db() generator yields Session.
    - Running the verify command with OPENAI_API_KEY set prints "All core module checks PASSED".
  </done>
</task>

</tasks>

<verification>
With OPENAI_API_KEY set in environment (or .env):

```bash
# Install dependencies first
pip install -r requirements.txt

# Run all module checks
python -c "
import os
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-placeholder')
from app.database import create_db_and_tables, DATABASE_URL
create_db_and_tables()
from pathlib import Path
print('DB path absolute:', Path(DATABASE_URL.replace('sqlite:///', '')).is_absolute())
print('DB file exists:', Path('data/companies.db').exists())
print('Foundation modules: OK')
"
```

Expected output confirms:
- DB path is absolute (not relative to CWD)
- `data/companies.db` file auto-created
- All imports succeed without errors
</verification>

<success_criteria>
Phase 1 — Plan 01 complete when:
- [ ] `pip install -r requirements.txt` completes without errors
- [ ] `app/config.py`, `app/models.py`, `app/database.py` all exist and import cleanly (with OPENAI_API_KEY set)
- [ ] `from app.database import create_db_and_tables; create_db_and_tables()` creates `data/companies.db`
- [ ] `DATABASE_URL` in database.py contains an absolute path
- [ ] `requirements.txt` contains pinned versions for sqlmodel, fastapi[standard], pydantic-settings, openai, tenacity, requests, pytest
- [ ] `.gitignore` excludes `.env` and `data/*.db`
- [ ] No playwright, beautifulsoup4, or lxml in requirements.txt
</success_criteria>

<output>
After completion, create `.planning/phases/phase-1/phase-1-01-SUMMARY.md` documenting:
- Files created and their key implementation choices
- The DATABASE_URL absolute path value (for downstream plans to reference)
- Any deviations from plan (e.g., if package versions differed at install time)
</output>
