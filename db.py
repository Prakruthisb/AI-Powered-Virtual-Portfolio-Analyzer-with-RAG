"""
db.py — database connection + session management.

Set DATABASE_URL in your environment (see .env.example):
    postgresql://user:password@localhost:5432/portfolio_db

Falls back to a local SQLite file if DATABASE_URL isn't set, so you
can run and test the app before Postgres is wired up.
"""

import os
import threading
from contextlib import contextmanager
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///local_dev.db")

# check_same_thread only matters for sqlite; harmless to set unconditionally guarded.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# (table, column, SQL type) — columns added after the first release. create_all() only
# creates MISSING TABLES, so existing databases need these ALTERs.
MIGRATIONS = [("holdings", "buy_date", "DATE")]
_schema_lock = threading.Lock()
_schema_ready = False


def init_db():
    """Create missing tables and add missing columns. Safe to call repeatedly."""
    from models import Base
    Base.metadata.create_all(engine)
    insp = inspect(engine)
    for table, column, sql_type in MIGRATIONS:
        if column not in {c["name"] for c in insp.get_columns(table)}:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))


def _ensure_schema_once():
    """Streamlit pages run independently (opening /portfolio directly never runs
    app.py), so every page's first DB access makes sure the schema is current."""
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if not _schema_ready:
            init_db()
            _schema_ready = True


@contextmanager
def get_session():
    """Usage: with get_session() as session: ..."""
    _ensure_schema_once()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()