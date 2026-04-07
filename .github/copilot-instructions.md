# AI Company Research Agent — Copilot Instructions

## Commands

```bash
# Activate virtualenv (Windows)
.venv\Scripts\activate

# Run all tests
python -m pytest tests/ -v

# Run a single test
python -m pytest tests/test_foundation.py::test_company_table_auto_creates -v

# Collect company data (requires internet)
python scraper/yc_scraper.py

# Run full AI analysis pipeline (requires OPENAI_API_KEY)
python scripts/run_pipeline.py

# Apply DB schema migration (v1.1 — adds description_hash column)
python scripts/migrate_add_hash.py

# Start API server
uvicorn app.main:app --reload
# API docs: http://localhost:8000/docs
# Frontend: http://localhost:8000/ui

# Start MCP server (v1.1 — stdio transport for Claude Desktop / Cursor)
python mcp_server/server.py
```

Set `OPENAI_API_KEY` in `.env` before running the pipeline. Copy `.env.example` as a starting point. Tests run with a placeholder key (`sk-test-placeholder`) — they don't call OpenAI.

## Architecture

Three completely separate entrypoints share a single SQLite file. No entrypoint starts another; they communicate only through the DB.

```
Pipeline CLI:   YC JSON API → scraper/yc_scraper.py → agent/analyzer.py → data/companies.db
API Server:     HTTP client → app/main.py → app/routers/ → data/companies.db (read-only)
MCP Server:     AI agent client → mcp_server/server.py → data/companies.db (read-only)
```

**Import boundary rule** — enforced, not just convention:
- `scraper/` imports nothing from `app/` or `agent/`
- `agent/` imports nothing from `app/` or `scraper/`
- `mcp_server/` imports from `app/database` and `app/models` only
- `scripts/run_pipeline.py` is the *only* file that imports from all three domains

**Key files:**
- `app/models.py` — single `Company(SQLModel, table=True)` class; serves as DB table, Pydantic schema, and FastAPI response model
- `app/database.py` — engine with `check_same_thread=False`, absolute `_DB_PATH` via `Path(__file__).resolve()`, `get_db()` session factory
- `app/config.py` — `pydantic-settings` `Settings`; fails fast at import if `OPENAI_API_KEY` is missing
- `scripts/migrate_add_hash.py` — `ALTER TABLE` migration for `description_hash`; `create_db_and_tables()` will NOT add new columns to existing tables

## Key Conventions

### SQLite threading — two fixes required together
Both must be present or FastAPI's thread pool raises `ProgrammingError`:
```python
engine = create_engine(url, connect_args={"check_same_thread": False})

def get_db():
    with Session(engine) as session:
        yield session  # new Session per call — never a shared global
```
Use `Depends(get_db)` in every route signature.

### SQLite WAL mode — required when MCP server runs alongside FastAPI
Default SQLite journal mode causes `SQLITE_BUSY` when two processes open the same `.db` file concurrently. Enable WAL on every engine that touches `companies.db`:
```python
with engine.connect() as conn:
    conn.execute(text("PRAGMA journal_mode=WAL"))
```
Set this immediately after `create_engine()` in both `app/database.py` and `mcp_server/server.py`.

### `create_db_and_tables()` does NOT migrate existing tables
`SQLModel.metadata.create_all(engine)` silently skips columns that don't exist on an already-created table. New columns (e.g. `description_hash`) must be added via `scripts/migrate_add_hash.py` using `ALTER TABLE`. The migration wraps the statement in `try/except OperationalError` to be idempotent.

### OpenAI Structured Outputs — not `json_object` mode
`response_format={"type": "json_object"}` only guarantees valid JSON syntax — field names and values drift across calls. Always use:
```python
result = client.beta.chat.completions.parse(
    model="gpt-4o-mini",
    messages=[...],
    response_format=CompanyAnalysis,  # Pydantic model with Industry(str, Enum)
)
```
`class Industry(str, Enum)` in `CompanyAnalysis` prevents free-text taxonomy drift.

### AI caching — two-condition check
Cache hit requires BOTH conditions:
```python
computed_hash = hashlib.sha256(description.strip().encode()).hexdigest()
is_cache_hit = (company.description_hash == computed_hash) and (company.industry is not None)
```
Hash match alone is insufficient — a partial write (hash stored, analysis failed) must be re-analyzed.

### FastAPI query param filtering — empty string is not None
FastAPI passes `?industry=` (empty) as `""`, not `None`. Use truthy checks and escape LIKE wildcards:
```python
def get_companies(industry: Optional[str] = None, q: Optional[str] = None, db = Depends(get_db)):
    if industry:  # not `if industry is not None`
        stmt = stmt.where(func.lower(Company.industry) == industry.lower())
    if q:
        safe_q = q.replace("%", r"\%").replace("_", r"\_")
        stmt = stmt.where(...contains(safe_q)...add ESCAPE '\\')
```

### MCP server — stdout must be clean
Any `print()` in `mcp_server/server.py` or any module it imports corrupts the JSON-RPC stdio stream silently (client disconnects with no error). First two lines of the MCP server file must be:
```python
import sys, logging
logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
```
Never use `print()` anywhere in the MCP process.

### FastAPI patterns — Pydantic v2, lifespan, sync routes
- `FastAPI(lifespan=lifespan)` — `@app.on_event("startup")` is deprecated in 0.135.x
- `model_config = ConfigDict(from_attributes=True)` — not `orm_mode = True`
- `.model_dump()` — not `.dict()`
- Route handlers are `def` not `async def` — DB calls are sync; FastAPI runs them in a thread pool

### StaticFiles mount — order and path matter
```python
app.include_router(companies_router)   # routes first
app.mount("/ui", StaticFiles(directory="frontend", html=True))  # mount last, at /ui not /
```
Mounting at `/` catches all routes and returns 404 on `GET /companies`. Must come after all `include_router()` calls.

### Pipeline is idempotent
Scraper upserts by company name. Analyzer skips records where `description_hash` matches AND `industry` is populated. Each company's OpenAI call is wrapped in its own `try/except` — one failure logs and continues, never aborts the batch.

## Data Source

`api.ycombinator.com/v0.1/companies` — public JSON API, no auth required, 25 companies/page, `nextPage` cursor pagination. Do **not** scrape `ycombinator.com/companies` HTML — that page is a JS-rendered shell with zero data.
