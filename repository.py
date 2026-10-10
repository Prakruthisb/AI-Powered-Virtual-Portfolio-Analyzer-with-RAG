"""
repository.py — DB reads/writes for portfolios and holdings.
Keeps engine.py (pure calculation, unchanged since Phase 1-3) separate
from database access.
"""

from db import get_session
from models import Portfolio, Holding


def list_portfolios(user_id: int) -> list:
    with get_session() as session:
        rows = session.query(Portfolio).filter_by(user_id=user_id).order_by(Portfolio.id).all()
        return [{"id": p.id, "name": p.name} for p in rows]


def create_portfolio(user_id: int, name: str) -> int:
    with get_session() as session:
        portfolio = Portfolio(user_id=user_id, name=name.strip())
        session.add(portfolio)
        session.flush()
        return portfolio.id


def rename_portfolio(portfolio_id: int, name: str):
    with get_session() as session:
        portfolio = session.query(Portfolio).filter_by(id=portfolio_id).first()
        if portfolio:
            portfolio.name = name.strip()


def delete_portfolio(portfolio_id: int):
    with get_session() as session:
        portfolio = session.query(Portfolio).filter_by(id=portfolio_id).first()
        if portfolio:
            session.delete(portfolio)


def get_holdings_dict(portfolio_id: int) -> dict:
    """Shape matches engine.py's RAW_PORTFOLIO:
    {ticker: {investment, buy_price, buy_date (datetime.date or None)}}."""
    with get_session() as session:
        rows = session.query(Holding).filter_by(portfolio_id=portfolio_id).all()
        return {
            h.symbol: {"investment": h.investment, "buy_price": h.buy_price, "buy_date": h.buy_date}
            for h in rows
        }


def add_holding(portfolio_id: int, symbol: str, investment: float, buy_price: float, buy_date=None):
    """Insert or update. On update, an omitted buy_date keeps the existing one."""
    shares = investment / buy_price
    with get_session() as session:
        existing = session.query(Holding).filter_by(
            portfolio_id=portfolio_id, symbol=symbol
        ).first()
        if existing:
            existing.investment = investment
            existing.buy_price = buy_price
            existing.shares = shares
            if buy_date is not None:
                existing.buy_date = buy_date
        else:
            session.add(Holding(
                portfolio_id=portfolio_id, symbol=symbol, buy_date=buy_date,
                investment=investment, buy_price=buy_price, shares=shares,
            ))


def set_buy_date(portfolio_id: int, symbol: str, buy_date):
    """Set (or clear, with None) the purchase date of an existing holding."""
    with get_session() as session:
        holding = session.query(Holding).filter_by(portfolio_id=portfolio_id, symbol=symbol).first()
        if holding:
            holding.buy_date = buy_date


def remove_holding(portfolio_id: int, symbol: str):
    with get_session() as session:
        holding = session.query(Holding).filter_by(
            portfolio_id=portfolio_id, symbol=symbol
        ).first()
        if holding:
            session.delete(holding)


# ---------------------------------------------------------------
# News (shared per symbol)
# ---------------------------------------------------------------
def get_existing_news_urls(symbol: str) -> set:
    from models import NewsItem
    with get_session() as session:
        rows = session.query(NewsItem.url).filter_by(symbol=symbol).all()
        return {r[0] for r in rows}


def save_news_items(items: list):
    from models import NewsItem
    with get_session() as session:
        for item in items:
            session.add(NewsItem(**item))


def list_news(symbols: list, per_symbol: int = 10) -> list:
    from models import NewsItem
    out = []
    with get_session() as session:
        for sym in symbols:
            rows = (session.query(NewsItem).filter_by(symbol=sym)
                    .order_by(NewsItem.published_at.desc()).limit(per_symbol).all())
            for n in rows:
                out.append({
                    "symbol": n.symbol, "title": n.title, "source": n.source,
                    "url": n.url, "published_at": n.published_at,
                    "sentiment": n.sentiment, "score": n.score, "engine": n.engine,
                })
    return out


# ---------------------------------------------------------------
# Document fetch status (shared per company)
# ---------------------------------------------------------------
def get_doc_statuses(symbols: list) -> dict:
    from models import DocumentStatus
    with get_session() as session:
        rows = session.query(DocumentStatus).filter(DocumentStatus.symbol.in_(symbols)).all()
        return {x.symbol: {"status": x.status, "message": x.message,
                           "reports": x.reports, "updated_at": x.updated_at} for x in rows}


def set_doc_status(symbol: str, status: str, message: str = "", reports: int = 0):
    from datetime import datetime
    from models import DocumentStatus
    with get_session() as session:
        row = session.query(DocumentStatus).filter_by(symbol=symbol).first()
        if row is None:
            row = DocumentStatus(symbol=symbol)
            session.add(row)
        row.status, row.message, row.reports = status, message[:500], reports
        row.updated_at = datetime.utcnow()


def claim_doc_fetch(symbol: str, stale_minutes: int = 20) -> bool:
    """Atomically mark `symbol` as fetching. Returns False if it is already
    ready/fetching (or unsupported), so two users adding the same stock
    don't trigger two downloads. Failed or stale-fetching entries can be re-claimed."""
    from datetime import datetime, timedelta
    from models import DocumentStatus
    with get_session() as session:
        row = session.query(DocumentStatus).filter_by(symbol=symbol).first()
        if row is not None:
            stale = row.updated_at and row.updated_at < datetime.utcnow() - timedelta(minutes=stale_minutes)
            if row.status in ("ready", "unsupported") or (row.status == "fetching" and not stale):
                return False
        else:
            row = DocumentStatus(symbol=symbol)
            session.add(row)
        row.status, row.message, row.reports = "fetching", "Queued...", 0
        row.updated_at = datetime.utcnow()
        return True