"""
SQLModel Company table — single class serves as both the SQLAlchemy ORM table
and the Pydantic schema. Imported by database.py, scripts/run_pipeline.py,
and app/routers/companies.py.
"""
from typing import Optional

from sqlmodel import Field, SQLModel


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

    # Caching field (populated in Phase 5)
    description_hash: Optional[str] = None
