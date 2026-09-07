"""
db.py — database connection + session management.

Set DATABASE_URL in your environment (see .env.example):
    postgresql://user:password@localhost:5432/portfolio_db

Falls back to a local SQLite file if DATABASE_URL isn't set, so you
can run and test the app before Postgres is wired up.
"""

import os
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///local_dev.db")

# check_same_thread only matters for sqlite; harmless to set unconditionally guarded.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db():
    """Create all tables if they don't exist yet. Call once on app startup."""
    from models import Base
    Base.metadata.create_all(engine)


@contextmanager
def get_session():
    """Usage: with get_session() as session: ..."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()