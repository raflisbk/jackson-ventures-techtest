"""
SQLite database engine and session management.

Threading fix: SQLite's Python binding raises ProgrammingError when a
connection is used from a thread other than the one that created it.
Two fixes are required together:
  1. connect_args={"check_same_thread": False} — allows cross-thread use
  2. get_db() yields a NEW Session per call — no shared session state

Absolute path fix: "sqlite:///./data/companies.db" resolves relative to
CWD at process start — different paths when running from project root vs
scripts/ subdirectory. We build the absolute path from __file__ instead.
"""
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

# Absolute path: app/database.py lives at <project_root>/app/database.py
# so parent.parent is the project root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = _PROJECT_ROOT / "data" / "companies.db"

# Ensure data/ directory exists (created on first import, before engine init)
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{_DB_PATH}"

# check_same_thread=False is required for FastAPI's threadpool (per DB-02)
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

# WAL mode: allows concurrent reads from MCP server without SQLITE_BUSY
with engine.connect() as _conn:
    _conn.execute(text("PRAGMA journal_mode=WAL"))
    _conn.commit()


def create_db_and_tables() -> None:
    """
    Create all SQLModel tables if they don't exist.
    Called at FastAPI startup (lifespan) and at the top of run_pipeline.py.
    No-op if tables already exist — safe to call multiple times (per DB-04).
    """
    SQLModel.metadata.create_all(engine)


def get_db():
    """
    FastAPI dependency that yields a fresh Session per request.
    Use with: db: Session = Depends(get_db)
    The with-block ensures the session is closed after the request
    even if an exception is raised (per DB-02).
    """
    with Session(engine) as session:
        yield session
