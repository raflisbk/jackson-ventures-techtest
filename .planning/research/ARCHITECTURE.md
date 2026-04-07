# Architecture Patterns

**Project:** AI Company Research Agent
**Domain:** AI-powered data pipeline + REST API (Python)
**Researched:** 2025-01-07
**Confidence:** HIGH — standard Python/FastAPI patterns, well-established ecosystem

---

## Recommended Architecture

The system has **two runtime modes** that must be understood upfront:

1. **Pipeline mode** (CLI) — run once to seed the database: scrape → analyze → store
2. **Server mode** (API) — serve already-populated data via REST endpoints

These are **separate entrypoints**. The FastAPI server never triggers scraping. The scraper never starts a web server. This separation is explicit in the project requirements ("one-time batch job").

```
┌─────────────────────────────────────────────────────────────┐
│  PIPELINE MODE  (scripts/run_pipeline.py)                   │
│                                                             │
│  YC Directory ──► Scraper ──► Analyzer ──► SQLite DB       │
│  (HTTP/HTML)      module      (OpenAI)      (companies.db)  │
└─────────────────────────────────────────────────────────────┘
                                    │
                                    │ (DB file shared)
                                    ▼
┌─────────────────────────────────────────────────────────────┐
│  SERVER MODE  (uvicorn app.main:app)                        │
│                                                             │
│  REST Client ──► FastAPI ──► SQLite DB (read-only queries)  │
│  (curl/HTTP)     Routes      (companies.db)                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Folder Structure

```
yc-research-agent/
│
├── app/                          # FastAPI application (server mode)
│   ├── __init__.py
│   ├── main.py                   # App instance, route registration, startup
│   ├── database.py               # Engine, SessionLocal, Base, get_db()
│   ├── models.py                 # SQLAlchemy ORM table definitions
│   ├── schemas.py                # Pydantic response/request models
│   └── routers/
│       └── companies.py          # GET /companies, GET /companies/{id}
│
├── scraper/                      # Data collection (pipeline mode only)
│   ├── __init__.py
│   └── yc_scraper.py             # HTTP fetch + HTML parse → list[dict]
│
├── agent/                        # AI analysis (pipeline mode only)
│   ├── __init__.py
│   └── analyzer.py               # OpenAI calls, prompt, response parsing
│
├── scripts/                      # CLI entrypoints
│   └── run_pipeline.py           # Orchestrates: scrape → analyze → store
│
├── migrations/                   # Alembic migration files
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 001_initial_schema.py
│
├── alembic.ini                   # Alembic config (points to migrations/)
├── .env                          # OPENAI_API_KEY, DATABASE_URL (gitignored)
├── .env.example                  # Template with keys, no values
├── config.py                     # Centralized settings (pydantic-settings)
├── requirements.txt
└── README.md
```

**Rule:** `app/` only imports from `app/`. The scraper and agent modules are **never imported by the FastAPI app**. They are pipeline-only concerns.

---

## Component Boundaries

| Component | Responsibility | Imports From | Never Imports From |
|-----------|---------------|--------------|-------------------|
| `scraper/yc_scraper.py` | HTTP requests, HTML parsing, returns raw company dicts | `requests`, `bs4`, `config` | `app/`, `agent/` |
| `agent/analyzer.py` | OpenAI prompt construction, API calls, response parsing | `openai`, `config` | `app/`, `scraper/` |
| `scripts/run_pipeline.py` | Orchestrate ETL: scrape → analyze → DB write | `scraper/`, `agent/`, `app/models`, `app/database` | — (top-level orchestrator) |
| `app/models.py` | SQLAlchemy `Company` table definition | `app/database` (Base) | `scraper/`, `agent/` |
| `app/database.py` | Engine, SessionLocal, Base, `get_db()` dependency | `config`, `sqlalchemy` | anything else |
| `app/schemas.py` | Pydantic response shapes for API | `pydantic` | `app/models` (no ORM leakage) |
| `app/routers/companies.py` | Route handlers, query DB, return schemas | `app/models`, `app/schemas`, `app/database` | `scraper/`, `agent/` |
| `app/main.py` | App factory, include routers, lifespan events | `app/routers/`, `app/database` | `scraper/`, `agent/` |
| `config.py` | Load `.env`, expose typed settings | `pydantic-settings` | anything |

---

## Data Flow

### Pipeline Execution (run once)

```
1. scripts/run_pipeline.py
       │
       ├─► scraper/yc_scraper.py
       │       │
       │       │  GET https://www.ycombinator.com/companies
       │       │  (HTTP + HTML parsing with BeautifulSoup)
       │       │
       │       └─► yields List[dict]
       │             { name, website, description, yc_batch, ... }
       │
       ├─► for each company dict:
       │       │
       │       └─► agent/analyzer.py.analyze(company_dict)
       │               │
       │               │  POST https://api.openai.com/v1/chat/completions
       │               │  model: gpt-4o-mini
       │               │  prompt: structured analysis request
       │               │
       │               └─► returns dict
       │                     { industry, business_model, summary, use_case }
       │
       └─► merge raw + AI data → write Company row to SQLite
               app/database.py → SessionLocal → session.add(company) → commit
```

### API Request (read-only)

```
HTTP Client
    │
    │  GET /companies
    │
    ▼
app/main.py (FastAPI router dispatch)
    │
    ▼
app/routers/companies.py
    │
    │  db.query(Company).all()
    │
    ▼
app/database.py (SessionLocal via get_db() dependency)
    │
    ▼
SQLite companies.db (read)
    │
    ▼
app/schemas.py (CompanyResponse Pydantic model)
    │
    ▼
JSON response → HTTP Client
```

---

## Database Schema

### SQLAlchemy Model (`app/models.py`)

```python
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.sql import func
from app.database import Base

class Company(Base):
    __tablename__ = "companies"

    id          = Column(Integer, primary_key=True, index=True)
    
    # Raw scraped fields
    name        = Column(String(255), nullable=False)
    website     = Column(String(500))
    description = Column(Text)
    yc_batch    = Column(String(20))           # e.g. "W24", "S23"
    yc_url      = Column(String(500))          # YC profile URL
    
    # AI-generated fields (nullable until analyzed)
    industry        = Column(String(255))
    business_model  = Column(String(255))
    summary         = Column(Text)             # 1-sentence
    use_case        = Column(Text)             # potential use case
    
    # Metadata
    scraped_at   = Column(DateTime, server_default=func.now())
    analyzed_at  = Column(DateTime)
    raw_yc_data  = Column(JSON)               # preserve original scrape
```

### Pydantic Schema (`app/schemas.py`)

```python
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class CompanyResponse(BaseModel):
    id: int
    name: str
    website: Optional[str]
    description: Optional[str]
    yc_batch: Optional[str]
    industry: Optional[str]
    business_model: Optional[str]
    summary: Optional[str]
    use_case: Optional[str]
    scraped_at: datetime
    analyzed_at: Optional[datetime]

    model_config = {"from_attributes": True}   # replaces orm_mode in Pydantic v2
```

### Alembic Decision

**Use Alembic.** Even for ~50 rows, `Base.metadata.create_all()` in startup is fine for initial dev, but Alembic enables safe schema iteration (adding columns like `tags`, `founded_year` later) without dropping the table.

```bash
# One-time setup
alembic init migrations
alembic revision --autogenerate -m "initial_schema"
alembic upgrade head

# Adding a column later
alembic revision --autogenerate -m "add_founded_year"
alembic upgrade head
```

**Alembic `env.py` must import your models** for autogenerate to detect the schema:
```python
# migrations/env.py
from app.models import Base        # ← critical
target_metadata = Base.metadata
```

---

## Database Session Management

### `app/database.py`

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from config import settings

# check_same_thread=False required for SQLite + FastAPI threading
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

# FastAPI dependency — yields session, ensures close on exception
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

**Why `check_same_thread=False`:** SQLite's default is single-thread only. FastAPI can dispatch requests across threads; without this flag, SQLite raises errors.

---

## FastAPI: Startup, Not Scraper

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import engine, Base
from app.routers import companies

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables if they don't exist (safe no-op if already there)
    Base.metadata.create_all(bind=engine)
    yield
    # shutdown logic here if needed

app = FastAPI(title="YC Research Agent", lifespan=lifespan)
app.include_router(companies.router, prefix="/companies", tags=["companies"])
```

**The scraper is NOT called here.** Startup only ensures the schema exists. The pipeline is a separate CLI:

```bash
# Seed the database (run once, re-run to refresh)
python scripts/run_pipeline.py

# Start the API server (serves from already-seeded DB)
uvicorn app.main:app --reload
```

---

## Async in FastAPI with OpenAI

The OpenAI Python SDK (v1.x) ships both **sync** (`openai.OpenAI`) and **async** (`openai.AsyncOpenAI`) clients.

### Option A: AsyncOpenAI (Recommended for API routes)

```python
# agent/analyzer.py
from openai import AsyncOpenAI
from config import settings

client = AsyncOpenAI(api_key=settings.openai_api_key)

async def analyze_company(description: str) -> dict:
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": build_prompt(description)}],
        response_format={"type": "json_object"}
    )
    return parse_response(response.choices[0].message.content)
```

**However:** the pipeline script runs synchronously. If you use `AsyncOpenAI` everywhere, you'll need `asyncio.run()` in the pipeline script, which is messy.

### Option B: Sync Client in Pipeline, Sync Routes (Recommended for this project)

Since scraping is **never triggered from the API**, and API routes are **read-only DB queries** (fast, no blocking IO), there's no async advantage in the routes. Use sync throughout:

```python
# agent/analyzer.py — sync, used by pipeline only
from openai import OpenAI

client = OpenAI(api_key=settings.openai_api_key)

def analyze_company(description: str) -> dict:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": build_prompt(description)}],
        response_format={"type": "json_object"}
    )
    return parse_response(response.choices[0].message.content)
```

```python
# app/routers/companies.py — sync route handlers are fine for DB reads
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

router = APIRouter()

@router.get("/", response_model=list[CompanyResponse])
def get_companies(db: Session = Depends(get_db)):
    return db.query(Company).all()

@router.get("/{company_id}", response_model=CompanyResponse)
def get_company(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company
```

**FastAPI handles sync route functions correctly** — it runs them in a thread pool automatically. No `async def` needed when there's no actual async IO in the handler.

### Option C: run_in_executor (If forced to mix)

```python
import asyncio
from fastapi import APIRouter

router = APIRouter()

@router.post("/analyze/{id}")
async def trigger_analysis(id: int):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, sync_openai_call, id)
    return result
```

**Use only if you must call sync code from an `async def` route.** Not needed here.

---

## Environment Variable Management

### `config.py` — Centralized Settings (Recommended)

```python
# config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    openai_api_key: str                                    # required, no default
    database_url: str = "sqlite:///./companies.db"         # optional with default
    openai_model: str = "gpt-4o-mini"                     # easy to override
    scrape_limit: int = 50                                 # max companies to scrape

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

settings = Settings()   # singleton — import this everywhere
```

### `.env`
```
OPENAI_API_KEY=sk-...
DATABASE_URL=sqlite:///./companies.db
OPENAI_MODEL=gpt-4o-mini
SCRAPE_LIMIT=20
```

### `.env.example` (committed to git)
```
OPENAI_API_KEY=your_openai_api_key_here
DATABASE_URL=sqlite:///./companies.db
OPENAI_MODEL=gpt-4o-mini
SCRAPE_LIMIT=20
```

**Why `pydantic-settings` over plain `python-dotenv`:**
- Type validation at startup (fail fast if `OPENAI_API_KEY` is missing)
- IDE autocomplete on `settings.openai_api_key`
- Override via environment variables OR `.env` file seamlessly

---

## AI Agent: Prompt Pattern

```python
# agent/analyzer.py

SYSTEM_PROMPT = """You are a startup analyst. Analyze the company and return a JSON object with:
- industry: primary industry (e.g. "SaaS", "Fintech", "Healthcare AI")  
- business_model: how they make money (e.g. "B2B subscription", "marketplace fee")
- summary: one sentence describing what the company does
- use_case: one specific potential use case for an enterprise customer

Return ONLY valid JSON. If information is insufficient, use "Unknown" for that field."""

def build_prompt(company: dict) -> str:
    return f"""Company: {company.get('name', 'Unknown')}
Website: {company.get('website', 'N/A')}
Description: {company.get('description', 'No description available')}"""

def analyze_company(company: dict) -> dict:
    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_prompt(company)}
            ],
            response_format={"type": "json_object"},  # enforces JSON output
            temperature=0.3   # lower = more consistent structured output
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        # Never crash the pipeline for one company
        return {"industry": "Unknown", "business_model": "Unknown",
                "summary": "Analysis failed", "use_case": "Unknown"}
```

**Key decisions:**
- `response_format={"type": "json_object"}` — prevents markdown-wrapped JSON responses
- `temperature=0.3` — structural tasks benefit from lower temperature
- Exception swallowing — pipeline should process all companies, not stop on one failure
- `"Unknown"` fallback — matches schema (nullable fields still get a value)

---

## Suggested Build Order

Dependencies determine order. Each phase unlocks the next.

```
Phase 1: Foundation
  config.py + .env
  app/database.py (engine, Base, get_db)
  app/models.py (Company table)
  → alembic init + first migration
  → verify: alembic upgrade head creates companies.db

Phase 2: Scraper
  scraper/yc_scraper.py
  → verify: python -c "from scraper.yc_scraper import scrape; print(scrape(limit=3))"
  → output: list of dicts with name, website, description

Phase 3: AI Analyzer
  agent/analyzer.py (prompt, OpenAI call, JSON parse)
  → verify: python -c "from agent.analyzer import analyze_company; print(analyze_company({...}))"
  → output: dict with industry, business_model, summary, use_case

Phase 4: Pipeline Script
  scripts/run_pipeline.py (scrape → analyze → DB write loop)
  → verify: python scripts/run_pipeline.py --limit 5
  → output: 5 rows in companies.db

Phase 5: FastAPI App
  app/schemas.py
  app/routers/companies.py (GET /companies, GET /companies/{id})
  app/main.py
  → verify: uvicorn app.main:app --reload
  → curl http://localhost:8000/companies → JSON list
  → curl http://localhost:8000/docs → Swagger UI

Phase 6: Polish
  Error handling (404, empty descriptions, OpenAI failures)
  README with run instructions
  .env.example
```

**Why this order:**
- DB schema before scraper (scraper output shape informs schema)
- Scraper before analyzer (need real data to test prompts against)
- Analyzer before pipeline (verify AI output before wiring up full loop)
- Pipeline before API (API needs data to be meaningful to test)

---

## Scalability Considerations

| Concern | At 10–50 records (current) | At 500+ records | At 10K+ records |
|---------|---------------------------|-----------------|-----------------|
| Database | SQLite, file-based, no setup | SQLite fine, add indexes | Migrate to PostgreSQL |
| Scraper | Sequential, no rate limiting needed | Add `time.sleep(1)` between requests | Async scraping with aiohttp |
| AI Analysis | Sequential per-company is fine | Batch API or async calls | OpenAI Batch API (50% cheaper) |
| API | Sync routes, no pagination needed | Add pagination (`skip`/`limit`) | Add Redis cache layer |
| Migrations | Alembic handles schema changes | Same | Same |

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Scraper in FastAPI Startup
**What goes wrong:** `@app.on_event("startup")` calls the scraper, so every server restart re-scrapes YC and re-analyzes all companies. Costs money, slow startup, race conditions.
**Instead:** Keep scraping as an explicit CLI: `python scripts/run_pipeline.py`

### Anti-Pattern 2: Raw SQL Strings
**What goes wrong:** `cursor.execute("SELECT * FROM companies WHERE id = " + str(id))` — SQL injection risk, no type safety.
**Instead:** SQLAlchemy ORM: `db.query(Company).filter(Company.id == company_id).first()`

### Anti-Pattern 3: ORM Models in API Responses
**What goes wrong:** Returning SQLAlchemy model instances directly from routes exposes all columns, including internal fields, and causes serialization errors.
**Instead:** Always use Pydantic schemas (`response_model=CompanyResponse`) to control shape.

### Anti-Pattern 4: Hardcoded API Keys
**What goes wrong:** `client = OpenAI(api_key="sk-abc123...")` committed to git.
**Instead:** Always `settings.openai_api_key` from `config.py` which reads from `.env`.

### Anti-Pattern 5: No Error Isolation in Pipeline
**What goes wrong:** If `analyze_company()` raises on company #7, companies #8–50 never get processed.
**Instead:** Wrap each company's analysis in `try/except`, log the error, continue loop.

### Anti-Pattern 6: Calling `asyncio.run()` Inside FastAPI Routes
**What goes wrong:** Creates a new event loop inside an already-running event loop → `RuntimeError`.
**Instead:** Use `async def` route + `await`, or use a sync route function (FastAPI threads it automatically).

---

## Sources

- FastAPI official docs: https://fastapi.tiangolo.com/tutorial/sql-databases/ — SQLAlchemy integration patterns (HIGH confidence)
- SQLAlchemy docs: https://docs.sqlalchemy.org/en/20/ — ORM session patterns (HIGH confidence)
- Alembic docs: https://alembic.sqlalchemy.org/en/latest/ — migration setup (HIGH confidence)
- OpenAI Python SDK v1.x: https://github.com/openai/openai-python — AsyncOpenAI + response_format (HIGH confidence)
- pydantic-settings: https://docs.pydantic.dev/latest/concepts/pydantic_settings/ — BaseSettings env loading (HIGH confidence)
- FastAPI sync vs async routes: https://fastapi.tiangolo.com/async/ — threadpool behavior (HIGH confidence)
