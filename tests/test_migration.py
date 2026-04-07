import os

os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")

from sqlalchemy import inspect, text
from sqlmodel import create_engine
from sqlmodel.pool import StaticPool


def _make_engine_without_hash():
    """Return in-memory engine with company table but WITHOUT description_hash."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with eng.connect() as conn:
        conn.execute(text(
            "CREATE TABLE company ("
            "id INTEGER PRIMARY KEY, company_name TEXT, description TEXT, "
            "website TEXT, industry TEXT, business_model TEXT, summary TEXT, use_case TEXT"
            ")"
        ))
        conn.commit()
    return eng


def _make_engine_with_hash():
    """Return in-memory engine with company table WITH description_hash already present."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with eng.connect() as conn:
        conn.execute(text(
            "CREATE TABLE company ("
            "id INTEGER PRIMARY KEY, company_name TEXT, description TEXT, "
            "website TEXT, industry TEXT, business_model TEXT, summary TEXT, "
            "use_case TEXT, description_hash TEXT"
            ")"
        ))
        conn.commit()
    return eng


def test_migration_adds_column():
    """_migrate_engine() adds description_hash to a table that lacks it."""
    from scripts.migrate_add_hash import _migrate_engine

    eng = _make_engine_without_hash()
    _migrate_engine(eng)

    insp = inspect(eng)
    cols = [c["name"] for c in insp.get_columns("company")]
    assert "description_hash" in cols


def test_migration_is_idempotent():
    """Running _migrate_engine() twice does not raise."""
    from scripts.migrate_add_hash import _migrate_engine

    eng = _make_engine_with_hash()
    _migrate_engine(eng)  # column already exists — must not raise
