import os

os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.main import app
from app.database import get_db
from app.models import Company


@pytest.fixture(name="client")
def client_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    # Seed: 3 companies across 2 industries
    with Session(engine) as session:
        session.add(Company(
            company_name="PayFlow",
            description="A real-time payments platform for banks.",
            industry="FinTech",
            business_model="B2B SaaS",
            summary="PayFlow enables instant settlement.",
            use_case="Banks use it to process transfers.",
        ))
        session.add(Company(
            company_name="HealthBot",
            description="AI-powered symptom checker for patients.",
            industry="HealthTech",
            business_model="B2C App",
            summary="HealthBot triages patient symptoms.",
            use_case="Patients check symptoms before a doctor visit.",
        ))
        session.add(Company(
            company_name="DevShip",
            description="Developer tooling for CI/CD pipeline automation.",
            industry="DevTools",
            business_model="API/Platform",
            summary="DevShip automates deployment pipelines.",
            use_case="Engineers trigger automated deploys.",
        ))
        session.commit()

    def get_session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = get_session_override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


# --- Industry filter (FILTER-01) ---

def test_filter_by_industry_exact(client):
    resp = client.get("/companies/?industry=FinTech")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["company_name"] == "PayFlow"


def test_filter_by_industry_case_insensitive(client):
    """fintech, FinTech, FINTECH should all match."""
    for variant in ["fintech", "FinTech", "FINTECH"]:
        resp = client.get(f"/companies/?industry={variant}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1, f"Expected 1 result for industry={variant}"
        assert data[0]["industry"] == "FinTech"


def test_filter_empty_industry_returns_all(client):
    """?industry= (empty) must return all companies — FILTER-1 guard."""
    resp = client.get("/companies/?industry=")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_filter_nonexistent_industry_returns_empty(client):
    resp = client.get("/companies/?industry=SpaceTech")
    assert resp.status_code == 200
    assert resp.json() == []


# --- Text search (FILTER-02) ---

def test_search_matches_description(client):
    """?q= should search in description."""
    resp = client.get("/companies/?q=payments")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["company_name"] == "PayFlow"


def test_search_matches_company_name(client):
    resp = client.get("/companies/?q=DevShip")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["company_name"] == "DevShip"


def test_search_case_insensitive(client):
    resp = client.get("/companies/?q=PAYMENTS")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_search_no_match_returns_empty(client):
    resp = client.get("/companies/?q=blockchain")
    assert resp.status_code == 200
    assert resp.json() == []


# --- Combined filter + search (FILTER-03) ---

def test_filter_and_search_combined(client):
    """?industry=FinTech&q=payments should narrow to 1 result."""
    resp = client.get("/companies/?industry=FinTech&q=payments")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# --- Wildcard injection safety (FILTER-04) ---

def test_search_with_percent_wildcard_no_error(client):
    """?q=100% must not cause a SQL error."""
    resp = client.get("/companies/?q=100%25")
    assert resp.status_code == 200


def test_search_with_underscore_no_error(client):
    """?q=a_b must not match 'ab' due to unescaped underscore."""
    resp = client.get("/companies/?q=a_b")
    assert resp.status_code == 200
    # "a_b" (escaped) should not match anything in our seed data
    assert resp.json() == []
