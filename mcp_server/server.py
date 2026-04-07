# MCP-1: ALL logging must go to stderr BEFORE any other imports.
# Any print() or logging to stdout corrupts the JSON-RPC stdio stream.
import sys
import logging

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

# ---------------------------------------------------------------------------
# Std-lib and third-party imports
# ---------------------------------------------------------------------------
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP
from sqlalchemy import text
from sqlmodel import Session, create_engine, func, or_, select

# ---------------------------------------------------------------------------
# DB setup — separate engine from app/database.py (MCP runs as a standalone
# process; importing app/ would trigger Settings() → needs OPENAI_API_KEY).
# MCP-2 (WAL mode): prevents SQLITE_BUSY when FastAPI reads concurrently.
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = _PROJECT_ROOT / "data" / "companies.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_engine = create_engine(
    f"sqlite:///{_DB_PATH}",
    connect_args={"check_same_thread": False},
)

with _engine.connect() as _conn:
    _conn.execute(text("PRAGMA journal_mode=WAL"))
    _conn.commit()

# ---------------------------------------------------------------------------
# FastMCP app
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="AI Company Research",
    instructions=(
        "Tools for querying the YC startup research database. "
        "Use list_industries to discover available categories, "
        "search_companies to filter by industry or keyword, "
        "and get_company to retrieve full details by ID."
    ),
)


# ---------------------------------------------------------------------------
# Tool: list_industries
# ---------------------------------------------------------------------------


@mcp.tool()
def list_industries() -> list[str]:
    """Return a sorted list of distinct industry values present in the database.

    Returns an empty list if no companies have been analyzed yet.
    """
    with Session(_engine) as session:
        from app.models import Company  # local import — avoids Settings() at module load
        rows = session.exec(
            select(func.distinct(Company.industry)).where(Company.industry.isnot(None))
        ).all()
        return sorted(str(r) for r in rows)


# ---------------------------------------------------------------------------
# Tool: search_companies
# ---------------------------------------------------------------------------


@mcp.tool()
def search_companies(
    industry: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    """Search YC companies by industry and/or keyword.

    Args:
        industry: Case-insensitive exact match on the industry field
                  (e.g. "FinTech", "HealthTech"). Omit to skip this filter.
        q:        Case-insensitive substring search across company_name
                  and description. Omit to skip.
        limit:    Maximum number of results to return (default 20, max 100).

    Returns:
        List of company dicts with all fields (id, company_name, description,
        website, industry, business_model, summary, use_case).
    """
    from app.models import Company  # local import

    limit = min(max(1, limit), 100)

    with Session(_engine) as session:
        stmt = select(Company)

        if industry:
            stmt = stmt.where(func.lower(Company.industry) == industry.lower())

        if q:
            safe_q = q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
            pattern = f"%{safe_q}%"
            stmt = stmt.where(
                or_(
                    Company.company_name.ilike(pattern),
                    Company.description.ilike(pattern),
                )
            )

        stmt = stmt.limit(limit)
        companies = session.exec(stmt).all()
        return [c.model_dump() for c in companies]


# ---------------------------------------------------------------------------
# Tool: get_company
# ---------------------------------------------------------------------------


@mcp.tool()
def get_company(company_id: int) -> Optional[dict]:
    """Retrieve full details for a single company by its integer ID.

    Args:
        company_id: The primary key of the company record.

    Returns:
        Company dict if found, or None if the ID does not exist.
    """
    from app.models import Company  # local import

    with Session(_engine) as session:
        company = session.get(Company, company_id)
        if company is None:
            return None
        return company.model_dump()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
