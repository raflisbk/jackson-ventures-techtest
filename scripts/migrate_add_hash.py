"""
Idempotent migration: add description_hash column to existing company table.

Usage:
    python scripts/migrate_add_hash.py

Safe to run multiple times — wraps ALTER TABLE in try/except OperationalError.
This migration is required because SQLModel.metadata.create_all() silently
skips new columns on already-created tables.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError

from app.database import engine


def _migrate_engine(target_engine: Engine) -> None:
    """Apply description_hash migration to an arbitrary engine (testable).

    Args:
        target_engine: SQLAlchemy engine pointing at the target database.
    """
    with target_engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE company ADD COLUMN description_hash TEXT"))
            conn.commit()
            print("Migration applied: description_hash column added.")
        except OperationalError:
            # "duplicate column name" — column already exists, nothing to do
            print("Migration already applied: description_hash column already exists.")


def migrate() -> None:
    """Run migration against the production database (data/companies.db)."""
    _migrate_engine(engine)


if __name__ == "__main__":
    migrate()
