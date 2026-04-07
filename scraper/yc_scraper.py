"""YC JSON API scraper. Standalone — imports nothing from app/ or agent/."""

import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional

import requests

_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "companies.db"
_API_BASE = "https://api.ycombinator.com/v0.1/companies"
MAX_PAGES = 2  # 2 pages × 25 companies = 50 records; sufficient for Phase 3 AI demo
_DELAY_SECONDS = 0.5

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS company (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name     TEXT NOT NULL,
    description      TEXT NOT NULL,
    website          TEXT,
    industry         TEXT,
    business_model   TEXT,
    summary          TEXT,
    use_case         TEXT
)
"""


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(_CREATE_TABLE_SQL)
    conn.commit()


def _get_description(company: dict) -> str:
    return (
        company.get("longDescription", "").strip()
        or company.get("oneLiner", "").strip()
        or f"{company['name']} (no description available)"
    )


def _upsert_company(
    conn: sqlite3.Connection,
    name: str,
    description: str,
    website: Optional[str],
) -> None:
    cursor = conn.execute("SELECT id FROM company WHERE company_name = ?", (name,))
    if cursor.fetchone():
        conn.execute(
            "UPDATE company SET description = ?, website = ? WHERE company_name = ?",
            (description, website, name),
        )
    else:
        conn.execute(
            "INSERT INTO company (company_name, description, website) VALUES (?, ?, ?)",
            (name, description, website),
        )
    conn.commit()


def fetch_companies(db_path: Optional[Path] = None) -> list[dict]:
    if db_path is None:
        db_path = _DB_PATH

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        _ensure_table(conn)
        session = requests.Session()
        stored: list[dict] = []
        url: Optional[str] = _API_BASE
        page_num = 0

        while url and page_num < MAX_PAGES:
            page_num += 1
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            for company in data.get("companies", []):
                try:
                    name = company["name"]
                    website = company.get("website") or None
                    description = _get_description(company)
                    _upsert_company(conn, name, description, website)
                    stored.append({"name": name, "description": description, "website": website})
                except Exception:
                    logging.exception("Failed to process company %r — skipping", company.get("name"))

            url = data.get("nextPage")
            if url and page_num < MAX_PAGES:
                time.sleep(_DELAY_SECONDS)
    finally:
        conn.close()

    return stored


def main() -> None:
    stored = fetch_companies()
    logging.info("Done — %d companies upserted into %s", len(stored), _DB_PATH)
    print(f"Stored {len(stored)} companies into {_DB_PATH}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
