---
phase: phase-1
plan: "02"
type: execute
wave: 2
depends_on: [phase-1-01]
files_modified:
  - tests/__init__.py
  - tests/test_foundation.py
autonomous: true
requirements: [CFG-01, CFG-02, DB-01, DB-02, DB-03, DB-04]

must_haves:
  truths:
    - "pytest tests/test_foundation.py passes with 4 tests — one for each Phase 1 success criterion"
    - "SC-1 test: Company table auto-creates in data/companies.db on first import with no manual migration step"
    - "SC-2 test: Settings() raises ValidationError immediately when OPENAI_API_KEY is absent from environment"
    - "SC-3 test: DATABASE_URL in database.py resolves to an absolute path regardless of working directory"
    - "SC-4 test: Concurrent threads importing app.database and querying via get_db() do not raise ProgrammingError"
  artifacts:
    - path: "tests/test_foundation.py"
      provides: "4 tests covering the Phase 1 success criteria"
      exports: ["test_company_table_auto_creates", "test_startup_fails_without_openai_key", "test_db_path_is_absolute", "test_multithreaded_db_access_no_crash"]
    - path: "tests/__init__.py"
      provides: "Makes tests/ a package (required for pytest module resolution)"
  key_links:
    - from: "tests/test_foundation.py"
      to: "app/database.py"
      via: "from app.database import create_db_and_tables, get_db, DATABASE_URL"
      pattern: "from app\\.database import"
    - from: "tests/test_foundation.py"
      to: "app/config.py"
      via: "Settings() instantiated with patched environment to test fail-fast behaviour"
      pattern: "Settings\\(\\)"
    - from: "tests/test_foundation.py"
      to: "app/models.py"
      via: "from app.models import Company (triggers table registration)"
      pattern: "from app\\.models import Company"
---

<objective>
Write the test suite that proves the four Phase 1 success criteria are met. These tests act as the living specification for the foundation — they will be run again in later phases to confirm nothing regressed.

Purpose: Makes success criteria machine-verifiable. The 4 tests map 1:1 to the 4 success criteria in ROADMAP.md Phase 1, so "pytest passes" = "phase complete".

Output:
- `tests/__init__.py` (empty — makes tests/ a package)
- `tests/test_foundation.py` — 4 tests, one per success criterion
</objective>

<execution_context>
@~/.copilot/get-shit-done/workflows/execute-plan.md
@~/.copilot/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/ROADMAP.md
@.planning/phases/phase-1/phase-1-01-SUMMARY.md
@app/config.py
@app/models.py
@app/database.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Test Suite for All 4 Success Criteria</name>
  <files>
    tests/__init__.py,
    tests/test_foundation.py
  </files>
  <action>
Create `tests/__init__.py` as an empty file.

Create `tests/test_foundation.py` with exactly 4 tests. Each test is named after and maps directly to one Phase 1 success criterion from ROADMAP.md.

```python
"""
Foundation test suite — validates all 4 Phase 1 success criteria.

SC-1: Company SQLModel table auto-creates in data/companies.db on first import
SC-2: Startup fails immediately with clear error if OPENAI_API_KEY is missing
SC-3: DB file path resolves consistently regardless of working directory
SC-4: Multi-threaded SQLite access does not raise ProgrammingError
"""
import os
import threading
import pytest
from pathlib import Path
from unittest.mock import patch


# ---------------------------------------------------------------------------
# SC-1: Company table auto-creates on first import — no manual migration step
# ---------------------------------------------------------------------------

def test_company_table_auto_creates(tmp_path):
    """
    Importing app.database and calling create_db_and_tables() must create
    data/companies.db containing the 'company' table — with no manual SQL,
    no alembic, and no pre-existing DB file (per DB-04, DB-03).
    """
    # We use the real database module (it already ran create_db_and_tables
    # when imported in this session), so we verify the DB file and table exist.
    from app.database import create_db_and_tables, _DB_PATH
    from app.models import Company  # registers Company in SQLModel.metadata

    # Ensure DB is created
    create_db_and_tables()

    # Verify the DB file exists at the resolved absolute path
    assert _DB_PATH.exists(), (
        f"data/companies.db was not created at {_DB_PATH}. "
        "create_db_and_tables() must call SQLModel.metadata.create_all(engine)."
    )

    # Verify the 'company' table exists in the DB
    import sqlite3
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
    raise pydantic_settings ValidationError immediately (per CFG-01).
    The error must be raised at Settings() construction — not later.
    """
    from pydantic import ValidationError

    # Patch env to remove OPENAI_API_KEY entirely (even if set in real env)
    env_without_key = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}

    with patch.dict(os.environ, env_without_key, clear=True):
        # Also ensure no .env file is found by pointing to a dir with no .env
        with pytest.raises(ValidationError) as exc_info:
            # Import Settings fresh — the module-level `settings` singleton
            # is already constructed, so we instantiate directly to test.
            from app.config import Settings
            Settings(_env_file=None)  # disable .env file fallback for test isolation

    # Verify the error message mentions the missing field
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

    # The path component of the URL must be absolute
    # DATABASE_URL format: "sqlite:////absolute/path/to/companies.db"
    db_file_path = Path(DATABASE_URL.replace("sqlite:///", ""))

    assert db_file_path.is_absolute(), (
        f"DATABASE_URL contains a relative path: {DATABASE_URL}\n"
        "Fix: use Path(__file__).resolve().parent.parent / 'data' / 'companies.db' "
        "in database.py instead of a relative string."
    )

    # The resolved _DB_PATH must also be absolute
    assert _DB_PATH.is_absolute(), (
        f"_DB_PATH is not absolute: {_DB_PATH}"
    )

    # Bonus: verify the path ends with data/companies.db (not some temp location)
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
    SQLite's Python binding raises ProgrammingError when a connection object
    is shared across threads. The fix requires BOTH:
      1. check_same_thread=False on the engine
      2. Per-call Session via get_db() (not a shared global session)

    This test spawns 5 threads that each call get_db() and run a SELECT.
    If check_same_thread is missing OR sessions are shared, at least one
    thread will raise ProgrammingError (per DB-02).
    """
    from sqlmodel import Session, select
    from app.database import get_db, create_db_and_tables
    from app.models import Company

    create_db_and_tables()  # ensure table exists

    errors = []
    results = []

    def query_in_thread():
        """Each thread gets its own session via get_db()."""
        try:
            db_gen = get_db()
            session: Session = next(db_gen)
            # Run a real SELECT — exercises the connection from this thread
            companies = session.exec(select(Company)).all()
            results.append(len(companies))
            # Clean up generator
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
```

**Implementation notes:**
- `_DB_PATH` must be exported from `app/database.py` for SC-1 and SC-3 tests to reference. If the current `database.py` does not export `_DB_PATH`, add it (it's already defined as a module-level variable — just ensure it's accessible via `from app.database import _DB_PATH`).
- SC-2 uses `Settings(_env_file=None)` to disable `.env` file loading during the test, so the test is not affected by a real `.env` file on the developer's machine. `pydantic-settings` accepts `_env_file` as a constructor override.
- SC-4 calls `get_db()` as a generator directly (not via FastAPI Depends) so it runs in a plain thread without needing a full FastAPI app.
  </action>
  <verify>
    <automated>python -m pytest tests/test_foundation.py -v 2>&1</automated>
  </verify>
  <done>
    `pytest tests/test_foundation.py -v` exits 0 with output showing:
    ```
    tests/test_foundation.py::test_company_table_auto_creates PASSED
    tests/test_foundation.py::test_startup_fails_without_openai_key PASSED
    tests/test_foundation.py::test_db_path_is_absolute PASSED
    tests/test_foundation.py::test_multithreaded_db_access_no_crash PASSED
    4 passed in ...
    ```
    All 4 Phase 1 success criteria are machine-verified.
  </done>
</task>

</tasks>

<verification>
Run from project root with OPENAI_API_KEY set in environment (or .env):

```bash
python -m pytest tests/test_foundation.py -v
```

All 4 tests must pass:
- `test_company_table_auto_creates` — verifies SC-1 (auto-create table)
- `test_startup_fails_without_openai_key` — verifies SC-2 (fail-fast config)
- `test_db_path_is_absolute` — verifies SC-3 (absolute path resolution)
- `test_multithreaded_db_access_no_crash` — verifies SC-4 (threading fix)

If any test fails, the error message in the assertion will point directly to the fix needed in the relevant foundation file.
</verification>

<success_criteria>
Phase 1 — Plan 02 complete when:
- [ ] `tests/__init__.py` and `tests/test_foundation.py` exist
- [ ] `python -m pytest tests/test_foundation.py -v` exits with code 0
- [ ] All 4 tests PASS (no FAIL, no ERROR, no SKIP)
- [ ] Each test maps to exactly one of the 4 ROADMAP Phase 1 success criteria
</success_criteria>

<output>
After completion, create `.planning/phases/phase-1/phase-1-02-SUMMARY.md` documenting:
- pytest output (paste the 4-line PASSED summary)
- Any test that required a code fix in a foundation file (note what was fixed)
- Confirmation that Phase 1 is complete and Phase 2 can begin
</output>
