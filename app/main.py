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

Static frontend (UI-01):
  - Mounted at /ui AFTER all routers — mounting at / would shadow API routes
  - Served from frontend/ directory as static HTML/JS (no build step)
  - Visit /ui in a browser to browse company cards

Run with:
  .venv\\Scripts\\uvicorn app.main:app --reload
  API docs: http://127.0.0.1:8000/docs
  Frontend: http://127.0.0.1:8000/ui
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.database import create_db_and_tables
from app.routers.companies import router as companies_router

_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


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

# Routes first — StaticFiles mount must come AFTER all include_router() calls
# (STATIC-1: mounting at / would shadow all API routes and return 404)
app.include_router(companies_router)


@app.get("/", include_in_schema=False)
def root_redirect():
    """Redirect bare root URL to the frontend UI."""
    return RedirectResponse(url="/ui/")

# Mount frontend at /ui — html=True enables directory index serving index.html
if _FRONTEND_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")
