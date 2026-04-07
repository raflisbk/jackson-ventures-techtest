import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scraper.yc_scraper import _get_description, fetch_companies

# Shared fixture matching exact YC API response shape
FIXTURE_PAGE_1 = {
    "companies": [
        {
            "id": 1,
            "name": "Acme Corp",
            "website": "https://acme.com",
            "longDescription": "We build rockets for everyone.",
            "oneLiner": "Rockets for everyone",
            "batch": "S23",
            "slug": "acme-corp",
            "smallLogoUrl": "",
            "teamSize": 10,
            "url": "https://ycombinator.com/companies/acme-corp",
            "tags": [],
            "status": "Active",
            "industries": [],
            "regions": [],
            "locations": [],
            "badges": [],
        },
        {
            "id": 2,
            "name": "EmptyDesc Co",
            "website": None,
            "longDescription": "",
            "oneLiner": "A lean startup",
            "batch": "W24",
            "slug": "emptydesc-co",
            "smallLogoUrl": "",
            "teamSize": 3,
            "url": "https://ycombinator.com/companies/emptydesc-co",
            "tags": [],
            "status": "Active",
            "industries": [],
            "regions": [],
            "locations": [],
            "badges": [],
        },
        {
            "id": 3,
            "name": "NoDesc Inc",
            "website": "https://nodesc.io",
            "longDescription": "",
            "oneLiner": "",
            "batch": "S24",
            "slug": "nodesc-inc",
            "smallLogoUrl": "",
            "teamSize": 2,
            "url": "https://ycombinator.com/companies/nodesc-inc",
            "tags": [],
            "status": "Active",
            "industries": [],
            "regions": [],
            "locations": [],
            "badges": [],
        },
    ],
    "nextPage": None,
    "page": 1,
    "totalPages": 1,
}


def _make_mock_response(fixture: dict) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = fixture
    mock.raise_for_status.return_value = None
    return mock


def _patch_session(fixture: dict):
    """Patches requests.Session so session.get() returns a mock response (no network calls)."""
    mock_session = MagicMock()
    mock_session.get.return_value = _make_mock_response(fixture)
    return patch("scraper.yc_scraper.requests.Session", return_value=mock_session)


# --- Unit tests for _get_description (pure function, no mocking needed) ---

def test_fallback_long_description():
    """longDescription used when non-empty (COLL-03)."""
    company = {"longDescription": "We build rockets.", "oneLiner": "Rockets", "name": "Acme"}
    assert _get_description(company) == "We build rockets."


def test_fallback_one_liner():
    """oneLiner used when longDescription is empty string (COLL-03)."""
    company = {"longDescription": "", "oneLiner": "A lean startup", "name": "EmptyDesc"}
    assert _get_description(company) == "A lean startup"


def test_fallback_whitespace_only():
    """Whitespace-only longDescription is treated as missing — oneLiner used (COLL-03).
    Verifies .strip() is applied before the falsy check.
    """
    company = {"longDescription": "   ", "oneLiner": "One liner here", "name": "SpaceDesc"}
    assert _get_description(company) == "One liner here"


def test_fallback_name_placeholder():
    """Name-only placeholder used when both longDescription and oneLiner are empty (COLL-03)."""
    company = {"longDescription": "", "oneLiner": "", "name": "NoDesc Corp"}
    assert _get_description(company) == "NoDesc Corp (no description available)"


# --- Integration tests using tmp_path and patch("requests.get") ---

def test_scraper_inserts_records(tmp_path):
    """Mock API → scraper inserts correct records into tmp DB (COLL-01, COLL-02)."""
    db_path = tmp_path / "test.db"

    with _patch_session(FIXTURE_PAGE_1):
        result = fetch_companies(db_path=db_path)

    assert len(result) == 3  # all 3 companies from fixture stored

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT company_name, description, website FROM company ORDER BY company_name"
    ).fetchall()
    conn.close()

    names = [r[0] for r in rows]
    assert "Acme Corp" in names
    assert "EmptyDesc Co" in names
    assert "NoDesc Inc" in names

    acme = next(r for r in rows if r[0] == "Acme Corp")
    assert acme[1] == "We build rockets for everyone."
    assert acme[2] == "https://acme.com"

    empty = next(r for r in rows if r[0] == "EmptyDesc Co")
    assert empty[1] == "A lean startup"  # oneLiner fallback
    assert empty[2] is None  # website None (was None in fixture)

    nodesc = next(r for r in rows if r[0] == "NoDesc Inc")
    assert nodesc[1] == "NoDesc Inc (no description available)"
    assert nodesc[2] == "https://nodesc.io"


def test_scraper_idempotent(tmp_path):
    """Running scraper twice does NOT create duplicate rows (COLL-04)."""
    db_path = tmp_path / "test.db"

    with _patch_session(FIXTURE_PAGE_1):
        fetch_companies(db_path=db_path)

    with _patch_session(FIXTURE_PAGE_1):
        fetch_companies(db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM company").fetchone()[0]
    conn.close()
    assert count == 3, f"Expected 3 rows after two runs, got {count} (upsert failed)"


def test_upsert_preserves_ai_fields(tmp_path):
    """Re-running scraper does NOT wipe AI-generated fields (COLL-04 edge case).
    Simulates Phase 3 having already populated industry; re-scraping must not clear it.
    """
    db_path = tmp_path / "test.db"

    with _patch_session(FIXTURE_PAGE_1):
        fetch_companies(db_path=db_path)

    # Simulate Phase 3: manually set AI fields on Acme Corp
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE company SET industry = 'FinTech', business_model = 'SaaS' WHERE company_name = 'Acme Corp'"
    )
    conn.commit()
    conn.close()

    # Second run: re-scrape — AI fields must survive
    with _patch_session(FIXTURE_PAGE_1):
        fetch_companies(db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT industry, business_model FROM company WHERE company_name = 'Acme Corp'"
    ).fetchone()
    conn.close()

    assert row is not None, "Acme Corp row missing after second run"
    assert row[0] == "FinTech", f"industry was wiped — got {row[0]!r}"
    assert row[1] == "SaaS", f"business_model was wiped — got {row[1]!r}"
