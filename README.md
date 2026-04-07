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
