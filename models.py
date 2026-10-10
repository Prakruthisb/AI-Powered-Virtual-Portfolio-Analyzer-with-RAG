"""
models.py — the three tables from the Phase 4 spec:
  users      : id, name, email, password_hash, created_at
  portfolios : id, user_id, name, created_at
  holdings   : id, portfolio_id, symbol, shares, buy_price, investment, created_at

Relationship: one User -> many Portfolios -> many Holdings.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    portfolios = relationship("Portfolio", back_populates="owner", cascade="all, delete-orphan")


class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(120), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="portfolios")
    holdings = relationship("Holding", back_populates="portfolio", cascade="all, delete-orphan")


class Holding(Base):
    __tablename__ = "holdings"
    __table_args__ = (UniqueConstraint("portfolio_id", "symbol", name="uq_portfolio_symbol"),)

    id = Column(Integer, primary_key=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)
    symbol = Column(String(20), nullable=False)       # e.g. "TCS.NS"
    shares = Column(Float, nullable=False)
    buy_price = Column(Float, nullable=False)
    investment = Column(Float, nullable=False)
    buy_date = Column(Date, nullable=True)             # when the user actually bought it (optional)
    created_at = Column(DateTime, default=datetime.utcnow)

    portfolio = relationship("Portfolio", back_populates="holdings")


class NewsItem(Base):
    """Shared across users (news is per stock, not per portfolio)."""
    __tablename__ = "news_items"
    __table_args__ = (UniqueConstraint("symbol", "url", name="uq_news_symbol_url"),)

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)   # e.g. "TCS.NS"
    title = Column(String(500), nullable=False)
    source = Column(String(120))
    url = Column(String(1000), nullable=False)
    published_at = Column(DateTime)
    sentiment = Column(String(10), nullable=False)            # Positive / Neutral / Negative
    score = Column(Float, nullable=False)                     # -1 .. 1
    engine = Column(String(20))                               # rule / finbert
    created_at = Column(DateTime, default=datetime.utcnow)


class DocumentStatus(Base):
    """Per-company document fetch state. Shared across users (documents are per company)."""
    __tablename__ = "document_status"

    symbol = Column(String(20), primary_key=True)             # folder/ticker name, e.g. "TCS"
    status = Column(String(20), nullable=False)               # fetching / ready / failed / unsupported
    message = Column(String(500))
    reports = Column(Integer, default=0)                      # annual reports available
    updated_at = Column(DateTime, default=datetime.utcnow)