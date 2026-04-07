"""
Foundation test suite — validates all 4 Phase 1 success criteria.

SC-1: Company SQLModel table auto-creates in data/companies.db on first import
SC-2: Startup fails immediately with clear error if OPENAI_API_KEY is missing
SC-3: DB file path resolves consistently regardless of working directory
SC-4: Multi-threaded SQLite access does not raise ProgrammingError
"""
import os
import threading
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# SC-1: Company table auto-creates on first import — no manual migration step
# ---------------------------------------------------------------------------


def test_company_table_auto_creates():
    """
    Importing app.database and calling create_db_and_tables() must create
    data/companies.db containing the 'company' table — with no manual SQL,
    no alembic, and no pre-existing DB file (per DB-04, DB-03).
    """
    import sqlite3

    from app.database import _DB_PATH, create_db_and_tables
    from app.models import Company  # registers Company in SQLModel.metadata  # noqa: F401

    create_db_and_tables()

    assert _DB_PATH.exists(), (
        f"data/companies.db was not created at {_DB_PATH}. "
        "create_db_and_tables() must call SQLModel.metadata.create_all(engine)."
    )

    conn = sqlite3.connect(str(_DB_PATH))
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='company'"
    )
    tables = cursor.fetchall()
    conn.close()

    assert len(tables) == 1, (
        "Table 'company' not found in companies.db. "
        "Ensure Company class has table=True in SQLModel definition."
    )


# ---------------------------------------------------------------------------
# SC-2: Startup fails immediately with clear error if OPENAI_API_KEY missing
# ---------------------------------------------------------------------------


def test_startup_fails_without_openai_key():
    """
    Instantiating Settings() without OPENAI_API_KEY in the environment must
    raise pydantic ValidationError immediately (per CFG-01).
    """
    from pydantic import ValidationError

    env_without_key = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}

    with patch.dict(os.environ, env_without_key, clear=True):
        with pytest.raises(ValidationError) as exc_info:
            from app.config import Settings

            Settings(_env_file=None)  # disable .env file fallback for test isolation

    error_str = str(exc_info.value)
    assert "OPENAI_API_KEY" in error_str, (
        f"ValidationError raised but OPENAI_API_KEY not mentioned. "
        f"Error was: {error_str}"
    )


# ---------------------------------------------------------------------------
# SC-3: DB path resolves consistently regardless of working directory
# ---------------------------------------------------------------------------


def test_db_path_is_absolute():
    """
    DATABASE_URL in app/database.py must use an absolute path so the same
    DB file is opened whether the process starts from the project root,
    from scripts/, or from any other subdirectory (per CFG-02, ROADMAP SC-3).
    """
    from app.database import DATABASE_URL, _DB_PATH

    db_file_path = Path(DATABASE_URL.replace("sqlite:///", ""))

    assert db_file_path.is_absolute(), (
        f"DATABASE_URL contains a relative path: {DATABASE_URL}\n"
        "Fix: use Path(__file__).resolve().parent.parent / 'data' / 'companies.db' "
        "in database.py instead of a relative string."
    )

    assert _DB_PATH.is_absolute(), f"_DB_PATH is not absolute: {_DB_PATH}"

    assert _DB_PATH.name == "companies.db", (
        f"Expected DB file named 'companies.db', got: {_DB_PATH.name}"
    )
    assert _DB_PATH.parent.name == "data", (
        f"Expected DB in 'data/' directory, got parent: {_DB_PATH.parent.name}"
    )


# ---------------------------------------------------------------------------
# SC-4: Multi-threaded SQLite access does not raise ProgrammingError
# ---------------------------------------------------------------------------


def test_multithreaded_db_access_no_crash():
    """
    Spawns 5 threads that each call get_db() and run a SELECT.
    If check_same_thread is missing OR sessions are shared, at least one
    thread will raise ProgrammingError (per DB-02).
    """
    from sqlmodel import Session, select

    from app.database import create_db_and_tables, get_db
    from app.models import Company  # noqa: F401

    create_db_and_tables()

    errors = []
    results = []

    def query_in_thread():
        try:
            db_gen = get_db()
            session: Session = next(db_gen)
            companies = session.exec(select(Company)).all()
            results.append(len(companies))
            try:
                next(db_gen)
            except StopIteration:
                pass
        except Exception as e:
            errors.append(f"{type(e).__name__}: {e}")

    threads = [threading.Thread(target=query_in_thread) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, (
        f"Multi-threaded DB access raised errors in {len(errors)} thread(s):\n"
        + "\n".join(errors)
        + "\n\nFix: ensure database.py has check_same_thread=False AND "
        "get_db() creates a new Session on each call."
    )
    assert len(results) == 5, (
        f"Expected 5 threads to complete successfully, got {len(results)}"
    )
