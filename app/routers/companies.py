"""
REST routes for company data.

GET /companies        — returns all companies as a JSON array (API-01)
GET /companies/{id}   — returns one company by integer primary key (API-02)

Route functions are plain `def` (not async) because get_db() is a sync
generator. FastAPI runs sync routes in its default threadpool — no manual
executor wiring needed.

Prefix "/companies" is set on the router, NOT on include_router() in main.py,
to avoid the "/companies/companies" duplication pitfall documented in research.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.database import get_db
from app.models import Company

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("/", response_model=list[Company])
def get_companies(db: Session = Depends(get_db)):
    """Return all companies. Returns an empty JSON array when the DB has no rows."""
    return db.exec(select(Company)).all()


@router.get("/{company_id}", response_model=Company)
def get_company(company_id: int, db: Session = Depends(get_db)):
    """
    Return a single company by its integer primary key.

    FastAPI validates that company_id is a valid int before calling this
    function — non-integer path segments (e.g. /companies/abc) automatically
    return HTTP 422 with no custom code required.

    Returns HTTP 404 with {"detail": "Company not found"} when the ID does
    not exist in the database.
    """
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company
