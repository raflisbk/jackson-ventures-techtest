"""
FastAPI application entry point.

Startup behaviour (API-03):
  - Uses @asynccontextmanager lifespan (NOT deprecated @app.on_event)
  - Calls create_db_and_tables() at startup — no-op if tables already exist

Response models (API-04):
  - Company (SQLModel table class) is used directly as response_model=
  - SQLModel 0.0.38 is Pydantic v2-based and already has the equivalent of
    model_config = ConfigDict(from_attributes=True) built in
  - No separate CompanyRead schema is needed

Router prefix strategy:
  - Prefix "/companies" is declared inside app/routers/companies.py
  - include_router() here uses NO prefix argument to avoid duplication

Run with:
  .venv\\Scripts\\uvicorn app.main:app --reload
  Then visit http://127.0.0.1:8000/docs for auto-generated Swagger UI.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import create_db_and_tables
from app.routers.companies import router as companies_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager (replaces deprecated @app.on_event).
    Code before `yield` runs at startup; code after runs at shutdown.
    """
    create_db_and_tables()
    yield


app = FastAPI(
    title="AI Company Research API",
    description="YC company data enriched with AI-generated insights",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(companies_router)
