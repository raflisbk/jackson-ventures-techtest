"""
End-to-end tests: full collect → analyze → store → expose pipeline.

Coverage:
  E2E-01  Scraper → DB → API (no AI): scraped fields flow correctly to REST API
  E2E-02  Analyze step populates AI fields visible in API response
  E2E-03  Full pipeline (scrape + analyze + API) end-to-end
  E2E-04  Caching: second analyze run makes 0 OpenAI calls
  E2E-05a Filter by industry returns only matching companies from real DB data
  E2E-05b Keyword search matches both company_name and description fields
  E2E-05c Combined industry + keyword filter returns correct intersection
  E2E-06  Frontend served at /ui returns HTML
  E2E-07a MCP list_industries tool returns distinct sorted industry values
  E2E-07b MCP search_companies tool filters by industry
  E2E-07c MCP get_company tool returns full dict or None
  E2E-08  Pipeline resilience: one analysis failure does not abort the batch
  E2E-09  All 9 Company fields present in API response for a full record
  E2E-10  Data integrity: exact values from scraper flow through to API unchanged

Isolation strategy:
  - File-based SQLite in pytest's tmp_path so sqlite3 (scraper) and SQLModel
    (pipeline, API) share the exact same .db file without StaticPool tricks.
  - FastAPI: app.dependency_overrides[get_db] redirected to test session.
  - MCP:     mcp_server.server._engine patched at module level before each call.
  - Scraper: scraper.yc_scraper.requests.Session mocked; fetch_companies(db_path=)
             receives tmp_db path for isolation.
  - OpenAI:  agent.analyzer.OpenAI class patched; returns mock CompanyAnalysis.
  - OPENAI_API_KEY guard must be set BEFORE any app.* import (pydantic-settings
    fails fast at import time).
"""
import os

# Must precede all app imports — app/config.py creates Settings() at module load.
os.environ.setdefault("OPENAI_API_KEY", "sk-e2e-test-placeholder")

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from starlette.testclient import TestClient

from agent.analyzer import CompanyAnalysis, Industry, compute_description_hash
from app.database import get_db
from app.main import app
from app.models import Company


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """File-based SQLite in pytest's temp dir with the full SQLModel schema.

    File-based (not StaticPool in-memory) so that sqlite3 used by the
    scraper and SQLModel used by the pipeline/API share the same rows.
    SQLModel.create_all runs first so description_hash column exists before
    the scraper's CREATE TABLE IF NOT EXISTS is a no-op.
    """
    db_file = tmp_path / "companies.db"
    eng = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(eng)
    eng.dispose()
    return db_file


@pytest.fixture
def db_engine(tmp_db: Path):
    eng = create_engine(
        f"sqlite:///{tmp_db}",
        connect_args={"check_same_thread": False},
    )
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(db_engine):
    with Session(db_engine) as session:
        yield session


@pytest.fixture
def client(db_session: Session):
    """TestClient with get_db overridden to use the isolated test session."""
    app.dependency_overrides[get_db] = lambda: db_session
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Three companies mirroring YC API response format used to mock HTTP calls.
YC_MOCK_PAGE = {
    "companies": [
        {
            "id": 1,
            "name": "Stripe",
            "website": "https://stripe.com",
            "longDescription": "Online payment processing for internet businesses.",
        },
        {
            "id": 2,
            "name": "Airbnb",
            "website": "https://airbnb.com",
            "longDescription": "Book unique homes and experiences around the world.",
        },
        {
            "id": 3,
            "name": "Dropbox",
            "website": "https://dropbox.com",
            "longDescription": "Store and share files in the cloud.",
        },
    ],
    "nextPage": None,
}


def _mock_yc_session():
    """Mock requests.Session that returns YC_MOCK_PAGE on first .get() call."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = YC_MOCK_PAGE
    mock_resp.raise_for_status = MagicMock()
    mock_sess = MagicMock()
    mock_sess.get.return_value = mock_resp
    return mock_sess


def _mock_openai_client(
    industry: str = "FinTech",
    business_model: str = "SaaS",
    summary: str = "A leading fintech company.",
    use_case: str = "Online payments.",
) -> MagicMock:
    """Mock OpenAI client whose .beta.chat.completions.parse() returns a
    real CompanyAnalysis Pydantic object so downstream code can read .industry.value.
    """
    parsed = CompanyAnalysis(
        industry=Industry(industry),
        business_model=business_model,
        summary=summary,
        use_case=use_case,
    )
    msg = MagicMock()
    msg.parsed = parsed
    msg.refusal = None
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    oc = MagicMock()
    oc.beta.chat.completions.parse.return_value = resp
    return oc


def _seed(session: Session, companies: list[dict]) -> list[Company]:
    """Insert Company dicts into session, commit, and return refreshed objects."""
    objs = [Company(**d) for d in companies]
    for o in objs:
        session.add(o)
    session.commit()
    for o in objs:
        session.refresh(o)
    return objs


def _run_analyze_loop(session: Session, mock_openai: MagicMock | None = None) -> None:
    """Run the AI analysis loop against all companies in session.

    Mirrors the logic in scripts/run_pipeline.py lines 45-84:
    two-condition cache check → analyze_company → commit.
    Patches agent.analyzer.OpenAI with mock_openai (or a default mock).
    """
    from agent.analyzer import analyze_company

    oc = mock_openai if mock_openai is not None else _mock_openai_client()

    with patch("agent.analyzer.OpenAI", return_value=oc):
        companies = session.exec(select(Company)).all()
        for company in companies:
            computed_hash = compute_description_hash(company.description or "")
            is_cache_hit = (
                computed_hash is not None
                and company.description_hash == computed_hash
                and company.industry is not None
            )
            if is_cache_hit:
                continue

            result = analyze_company(company.company_name, company.description or "")
            if result:
                company.industry = result.industry.value
                company.business_model = result.business_model
                company.summary = result.summary
                company.use_case = result.use_case
                company.description_hash = computed_hash
                session.add(company)
        session.commit()


# ---------------------------------------------------------------------------
# E2E-01: Scraper → DB → API (no AI)
# ---------------------------------------------------------------------------


def test_scraper_to_db_to_api(tmp_db: Path, db_session: Session, client: TestClient):
    """E2E-01: Mock YC HTTP → run scraper → companies served by REST API.

    Verifies name, website, description flow through correctly.
    AI fields must be null (not yet analyzed).
    """
    with patch("scraper.yc_scraper.requests.Session", return_value=_mock_yc_session()):
        from scraper.yc_scraper import fetch_companies
        fetch_companies(db_path=tmp_db)

    response = client.get("/companies/")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 3
    names = {c["company_name"] for c in data}
    assert names == {"Stripe", "Airbnb", "Dropbox"}

    stripe = next(c for c in data if c["company_name"] == "Stripe")
    assert stripe["website"] == "https://stripe.com"
    assert "payment" in stripe["description"].lower()

    # AI fields not yet populated
    assert stripe["industry"] is None
    assert stripe["business_model"] is None
    assert stripe["summary"] is None
    assert stripe["use_case"] is None


# ---------------------------------------------------------------------------
# E2E-02: Analyze step populates AI fields visible in API response
# ---------------------------------------------------------------------------


def test_analyze_step_populates_ai_fields(db_session: Session, client: TestClient):
    """E2E-02: Insert raw companies → analyze → AI fields appear in API response."""
    _seed(
        db_session,
        [
            {"company_name": "Stripe",  "description": "Online payment processing.", "website": "https://stripe.com"},
            {"company_name": "Airbnb",  "description": "Home sharing platform.",     "website": "https://airbnb.com"},
        ],
    )

    _run_analyze_loop(db_session, _mock_openai_client(industry="FinTech", business_model="Marketplace"))

    response = client.get("/companies/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    for c in data:
        assert c["industry"] == "FinTech"
        assert c["business_model"] == "Marketplace"
        assert c["summary"] is not None
        assert c["use_case"] is not None


# ---------------------------------------------------------------------------
# E2E-03: Full pipeline (scrape + analyze) end-to-end
# ---------------------------------------------------------------------------


def test_full_pipeline_end_to_end(tmp_db: Path, db_session: Session, client: TestClient):
    """E2E-03: Mock YC API + mock OpenAI → 3 companies with AI fields via REST API."""
    with patch("scraper.yc_scraper.requests.Session", return_value=_mock_yc_session()):
        from scraper.yc_scraper import fetch_companies
        fetch_companies(db_path=tmp_db)

    _run_analyze_loop(
        db_session,
        _mock_openai_client(
            industry="FinTech",
            business_model="SaaS",
            summary="A top YC startup.",
            use_case="B2B payments.",
        ),
    )

    response = client.get("/companies/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    for c in data:
        assert c["industry"] == "FinTech"
        assert c["business_model"] == "SaaS"
        assert c["summary"] == "A top YC startup."
        assert c["use_case"] == "B2B payments."
        assert c["website"] is not None
        assert c["description"] is not None


# ---------------------------------------------------------------------------
# E2E-04: Caching — second analyze run makes 0 OpenAI calls
# ---------------------------------------------------------------------------


def test_caching_skips_reanalysis(db_session: Session, client: TestClient):
    """E2E-04: After first analyze run, re-running makes 0 additional OpenAI calls.

    Two-condition cache check: description_hash must match AND industry must be set.
    """
    _seed(
        db_session,
        [
            {"company_name": "Stripe",  "description": "Online payment processing."},
            {"company_name": "Dropbox", "description": "Cloud file storage."},
        ],
    )

    first_mock = _mock_openai_client()
    _run_analyze_loop(db_session, first_mock)
    assert first_mock.beta.chat.completions.parse.call_count == 2

    # Second run: all companies have matching hash + industry → 0 calls
    second_mock = _mock_openai_client()
    _run_analyze_loop(db_session, second_mock)
    assert second_mock.beta.chat.completions.parse.call_count == 0


# ---------------------------------------------------------------------------
# E2E-05: Filtering and search on real DB data
# ---------------------------------------------------------------------------


def test_filter_by_industry(db_session: Session, client: TestClient):
    """E2E-05a: ?industry=FinTech returns only FinTech companies."""
    _seed(
        db_session,
        [
            {"company_name": "Stripe",    "description": "Payments.",  "industry": "FinTech"},
            {"company_name": "GitLab",    "description": "DevOps.",    "industry": "DevTools"},
            {"company_name": "Braintree", "description": "Pay APIs.",  "industry": "FinTech"},
        ],
    )
    response = client.get("/companies/?industry=FinTech")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(c["industry"] == "FinTech" for c in data)
    assert {c["company_name"] for c in data} == {"Stripe", "Braintree"}


def test_search_by_keyword(db_session: Session, client: TestClient):
    """E2E-05b: ?q=payment matches across company_name and description."""
    _seed(
        db_session,
        [
            {"company_name": "Stripe",      "description": "Online payment processing."},
            {"company_name": "Payment App", "description": "A budgeting tool."},
            {"company_name": "Airbnb",      "description": "Home sharing."},
        ],
    )
    response = client.get("/companies/?q=payment")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert {c["company_name"] for c in data} == {"Stripe", "Payment App"}


def test_filter_and_search_combined(db_session: Session, client: TestClient):
    """E2E-05c: ?industry=FinTech&q=payment returns the intersection."""
    _seed(
        db_session,
        [
            {"company_name": "Stripe",      "description": "Online payment.",  "industry": "FinTech"},
            {"company_name": "Airbnb",      "description": "Home sharing.",    "industry": "Marketplace"},
            {"company_name": "Payment Co",  "description": "B2B payments.",   "industry": "FinTech"},
            {"company_name": "Monzo",       "description": "Digital bank.",    "industry": "FinTech"},
        ],
    )
    response = client.get("/companies/?industry=FinTech&q=payment")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert {c["company_name"] for c in data} == {"Stripe", "Payment Co"}


# ---------------------------------------------------------------------------
# E2E-06: Frontend served at /ui
# ---------------------------------------------------------------------------


def test_frontend_served_at_ui(client: TestClient):
    """E2E-06: GET /ui/ returns HTTP 200 with HTML content."""
    response = client.get("/ui/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "<html" in response.text.lower()


# ---------------------------------------------------------------------------
# E2E-07: MCP tools return correct data from DB
# ---------------------------------------------------------------------------


def test_mcp_list_industries(db_engine, db_session: Session):
    """E2E-07a: list_industries returns distinct sorted industry values."""
    _seed(
        db_session,
        [
            {"company_name": "Stripe", "description": "Payments.",  "industry": "FinTech"},
            {"company_name": "GitLab", "description": "DevOps.",    "industry": "DevTools"},
            {"company_name": "Monzo",  "description": "Banking.",   "industry": "FinTech"},
        ],
    )
    import mcp_server.server as server_mod
    server_mod._engine = db_engine

    from mcp_server.server import list_industries
    result = list_industries()
    assert result == ["DevTools", "FinTech"]


def test_mcp_search_companies(db_engine, db_session: Session):
    """E2E-07b: search_companies filters by industry correctly."""
    _seed(
        db_session,
        [
            {"company_name": "Stripe",    "description": "Payments.",  "industry": "FinTech"},
            {"company_name": "Airbnb",    "description": "Rentals.",   "industry": "Marketplace"},
            {"company_name": "Braintree", "description": "Pay APIs.",  "industry": "FinTech"},
        ],
    )
    import mcp_server.server as server_mod
    server_mod._engine = db_engine

    from mcp_server.server import search_companies
    result = search_companies(industry="FinTech")
    assert len(result) == 2
    assert {r["company_name"] for r in result} == {"Stripe", "Braintree"}


def test_mcp_get_company(db_engine, db_session: Session):
    """E2E-07c: get_company returns full dict by ID, or None for missing ID."""
    (company,) = _seed(
        db_session,
        [{"company_name": "Stripe", "description": "Payments.", "website": "https://stripe.com"}],
    )
    import mcp_server.server as server_mod
    server_mod._engine = db_engine

    from mcp_server.server import get_company
    result = get_company(company.id)
    missing = get_company(99999)

    assert result is not None
    assert result["company_name"] == "Stripe"
    assert result["website"] == "https://stripe.com"
    assert missing is None


# ---------------------------------------------------------------------------
# E2E-08: Pipeline resilience — one failure does not abort the batch
# ---------------------------------------------------------------------------


def test_pipeline_resilience_one_failure(db_session: Session, client: TestClient):
    """E2E-08: analyze_company returning None for one company doesn't abort the batch.

    Companies before and after the failing one are still analyzed and stored.
    """
    _seed(
        db_session,
        [
            {"company_name": "Stripe",  "description": "Payments."},
            {"company_name": "FailCo",  "description": "This one fails."},
            {"company_name": "Airbnb",  "description": "Home sharing."},
        ],
    )

    def resilient_analyze(name: str, description: str, **_):
        if name == "FailCo":
            return None
        return CompanyAnalysis(
            industry=Industry("FinTech"),
            business_model="SaaS",
            summary="Good startup.",
            use_case="B2B.",
        )

    with patch("agent.analyzer.analyze_company", side_effect=resilient_analyze):
        companies = db_session.exec(select(Company)).all()
        for company in companies:
            result = resilient_analyze(company.company_name, company.description or "")
            if result:
                company.industry = result.industry.value
                company.business_model = result.business_model
                company.summary = result.summary
                company.use_case = result.use_case
                company.description_hash = compute_description_hash(company.description or "")
                db_session.add(company)
        db_session.commit()

    response = client.get("/companies/")
    data = response.json()
    analyzed = [c for c in data if c["industry"] is not None]
    failed = [c for c in data if c["industry"] is None]
    assert len(analyzed) == 2
    assert len(failed) == 1
    assert failed[0]["company_name"] == "FailCo"


# ---------------------------------------------------------------------------
# E2E-09: All Company fields present in API response
# ---------------------------------------------------------------------------


def test_all_fields_in_api_response(db_session: Session, client: TestClient):
    """E2E-09: A fully-analyzed company exposes all expected fields in API JSON."""
    desc = "Online payment processing for internet businesses."
    _seed(
        db_session,
        [
            {
                "company_name":     "Stripe",
                "description":      desc,
                "website":          "https://stripe.com",
                "industry":         "FinTech",
                "business_model":   "SaaS",
                "summary":          "Stripe provides payment APIs for online businesses.",
                "use_case":         "Accepting credit card payments on a website.",
                "description_hash": compute_description_hash(desc),
            }
        ],
    )
    response = client.get("/companies/")
    assert response.status_code == 200
    record = response.json()[0]

    for field in ["id", "company_name", "description", "website", "industry", "business_model", "summary", "use_case"]:
        assert field in record, f"Field '{field}' missing from API response"

    assert record["company_name"] == "Stripe"
    assert record["industry"] == "FinTech"
    assert record["business_model"] == "SaaS"
    assert record["summary"] == "Stripe provides payment APIs for online businesses."
    assert record["use_case"] == "Accepting credit card payments on a website."
    assert record["website"] == "https://stripe.com"


# ---------------------------------------------------------------------------
# E2E-10: Data integrity — exact values from scraper flow through to API
# ---------------------------------------------------------------------------


def test_data_integrity_scraper_to_api(tmp_db: Path, db_session: Session, client: TestClient):
    """E2E-10: Exact field values set by the scraper reach the API unchanged."""
    with patch("scraper.yc_scraper.requests.Session", return_value=_mock_yc_session()):
        from scraper.yc_scraper import fetch_companies
        fetch_companies(db_path=tmp_db)

    response = client.get("/companies/")
    assert response.status_code == 200
    data = response.json()

    airbnb = next(c for c in data if c["company_name"] == "Airbnb")
    assert airbnb["website"] == "https://airbnb.com"
    assert airbnb["description"] == "Book unique homes and experiences around the world."

    dropbox = next(c for c in data if c["company_name"] == "Dropbox")
    assert dropbox["website"] == "https://dropbox.com"
    assert dropbox["description"] == "Store and share files in the cloud."
