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
    """Shape matches engine.py's RAW_PORTFOLIO: {ticker: {investment, buy_price}}."""
    with get_session() as session:
        rows = session.query(Holding).filter_by(portfolio_id=portfolio_id).all()
        return {
            h.symbol: {"investment": h.investment, "buy_price": h.buy_price}
            for h in rows
        }


def add_holding(portfolio_id: int, symbol: str, investment: float, buy_price: float):
    shares = investment / buy_price
    with get_session() as session:
        existing = session.query(Holding).filter_by(
            portfolio_id=portfolio_id, symbol=symbol
        ).first()
        if existing:
            existing.investment = investment
            existing.buy_price = buy_price
            existing.shares = shares
        else:
            session.add(Holding(
                portfolio_id=portfolio_id, symbol=symbol,
                investment=investment, buy_price=buy_price, shares=shares,
            ))


def remove_holding(portfolio_id: int, symbol: str):
    with get_session() as session:
        holding = session.query(Holding).filter_by(
            portfolio_id=portfolio_id, symbol=symbol
        ).first()
        if holding:
            session.delete(holding)