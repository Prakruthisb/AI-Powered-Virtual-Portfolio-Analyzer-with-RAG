"""
engine.py — pure calculation layer (Phase 1-3 logic, unchanged).
Every function here takes a raw_portfolio dict shaped as:
    {"TCS.NS": {"investment": 30000, "buy_price": 3000}, ...}
Where that dict comes from now (DB, per logged-in user) is handled by
context.py + repository.py, not here — this file doesn't know about
users or auth at all.
"""

import yfinance as yf
import pandas as pd
import streamlit as st


def display_name(ticker: str) -> str:
    return ticker.replace(".NS", "").replace(".BO", "")


# ---------------------------------------------------------------
# STEP 1/2/3 (Phase 1 logic) — shares from investment + buy price
# ---------------------------------------------------------------
def build_portfolio(raw_portfolio: dict) -> dict:
    portfolio = {}
    for ticker, data in raw_portfolio.items():
        shares = data["investment"] / data["buy_price"]
        portfolio[ticker] = {**data, "shares": shares}
    return portfolio


# ---------------------------------------------------------------
# STEP 4 (Phase 1 logic) — live prices, value, profit, return %
# Cached for 60s so navigating between pages doesn't refetch every time.
# ---------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def evaluate_portfolio(raw_portfolio: dict) -> dict:
    portfolio = build_portfolio(raw_portfolio)
    results = {}
    total_investment = 0.0
    total_current_value = 0.0

    for ticker, data in portfolio.items():
        stock = yf.Ticker(ticker)
        try:
            price = stock.fast_info["last_price"]
        except Exception:
            price = stock.info.get("currentPrice", data["buy_price"])

        current_value = price * data["shares"]
        profit = current_value - data["investment"]
        return_pct = (profit / data["investment"]) * 100

        results[ticker] = {
            "investment": data["investment"],
            "buy_price": data["buy_price"],
            "shares": round(data["shares"], 4),
            "current_price": round(price, 2),
            "current_value": round(current_value, 2),
            "profit": round(profit, 2),
            "return_pct": round(return_pct, 2),
        }
        total_investment += data["investment"]
        total_current_value += current_value

    total_profit = total_current_value - total_investment
    total_return_pct = (total_profit / total_investment * 100) if total_investment else 0

    return {
        "holdings": results,
        "total_investment": round(total_investment, 2),
        "total_current_value": round(total_current_value, 2),
        "total_profit": round(total_profit, 2),
        "total_return_pct": round(total_return_pct, 2),
    }


# ---------------------------------------------------------------
# Portfolio Growth Chart — reconstruct historical portfolio value
# as sum(shares_i * price_i(t)) for every day in the period.
# ---------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def get_portfolio_history(raw_portfolio: dict, period: str = "6mo") -> pd.DataFrame:
    portfolio = build_portfolio(raw_portfolio)
    tickers = list(portfolio.keys())

    data = yf.download(tickers, period=period, auto_adjust=True, progress=False)["Close"]
    if isinstance(data, pd.Series):  # single ticker edge case
        data = data.to_frame(tickers[0])

    value = pd.Series(0.0, index=data.index)
    for ticker in tickers:
        value += data[ticker].ffill() * portfolio[ticker]["shares"]

    return value.rename("Portfolio Value").reset_index()


# ---------------------------------------------------------------
# Individual Stock Performance — normalized (rebased to 100) so
# stocks at very different price levels are comparable on one chart.
# ---------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def get_normalized_prices(tickers: list, period: str = "6mo") -> pd.DataFrame:
    data = yf.download(tickers, period=period, auto_adjust=True, progress=False)["Close"]
    if isinstance(data, pd.Series):
        data = data.to_frame(tickers[0])
    normalized = data / data.iloc[0] * 100
    return normalized.reset_index()


# ---------------------------------------------------------------
# News — latest headlines per holding
# ---------------------------------------------------------------
@st.cache_data(ttl=900, show_spinner=False)
def get_news(ticker: str, limit: int = 5) -> list:
    try:
        items = yf.Ticker(ticker).news or []
    except Exception:
        items = []
    return items[:limit]


# =================================================================
# PHASE 3 — Financial Metrics
# =================================================================

# ---------------------------------------------------------------
# Metric 1: Daily Returns — pct_change() on each stock's close price
# ---------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def get_daily_returns(tickers: list, period: str = "6mo") -> pd.DataFrame:
    data = yf.download(tickers, period=period, auto_adjust=True, progress=False)["Close"]
    if isinstance(data, pd.Series):
        data = data.to_frame(tickers[0])
    return data.pct_change().dropna()


def get_portfolio_daily_returns(raw_portfolio: dict, period: str = "6mo") -> pd.Series:
    """Weighted daily return of the whole portfolio, from reconstructed value history."""
    history = get_portfolio_history(raw_portfolio, period)
    value = history.set_index(history.columns[0])["Portfolio Value"]
    return value.pct_change().dropna()


# ---------------------------------------------------------------
# Metric 2: Volatility — std dev of returns, annualized with sqrt(252)
# ---------------------------------------------------------------
def compute_volatility(returns: pd.Series, annualize: bool = True) -> float:
    vol = returns.std()
    if annualize:
        vol *= 252 ** 0.5
    return round(vol * 100, 2)  # as a %


# ---------------------------------------------------------------
# Metric 3: Correlation Matrix — how holdings move together
# ---------------------------------------------------------------
def compute_correlation_matrix(returns_df: pd.DataFrame) -> pd.DataFrame:
    return returns_df.corr().round(2)


# ---------------------------------------------------------------
# Metric 4: Maximum Drawdown — biggest fall from a prior peak
# ---------------------------------------------------------------
def compute_max_drawdown(value_series: pd.Series) -> dict:
    running_peak = value_series.cummax()
    drawdown = (value_series - running_peak) / running_peak

    trough_idx = drawdown.idxmin()
    max_dd_pct = drawdown.loc[trough_idx] * 100
    peak_idx = value_series.loc[:trough_idx].idxmax()

    return {
        "max_drawdown_pct": round(max_dd_pct, 2),
        "peak_value": round(value_series.loc[peak_idx], 2),
        "peak_date": peak_idx,
        "trough_value": round(value_series.loc[trough_idx], 2),
        "trough_date": trough_idx,
    }


# ---------------------------------------------------------------
# Metric 5: Portfolio Risk Score — your own simple composite score
#   Risk Score = Volatility Score x 40% + Drawdown Score x 30%
#              + Concentration Score x 30%
#   Low: 0-30   Medium: 31-60   High: 61-100
# ---------------------------------------------------------------
def compute_concentration(report: dict) -> float:
    """Herfindahl-Hirschman Index on current value weights, scaled to 0-100.
    All-in-one-stock -> 100. Evenly split across many stocks -> low."""
    total = report["total_current_value"]
    if not total:
        return 0.0
    weights = [h["current_value"] / total for h in report["holdings"].values()]
    hhi = sum(w ** 2 for w in weights)
    return round(hhi * 100, 2)


def _clamp(x, low=0, high=100):
    return max(low, min(high, x))


def compute_risk_score(annual_volatility_pct: float, max_drawdown_pct: float, concentration: float) -> dict:
    # Scale raw metrics to 0-100 "risk points" before weighting.
    # 50% annualized volatility or 50% drawdown is treated as maximally risky (100).
    vol_score = _clamp(abs(annual_volatility_pct) / 50 * 100)
    drawdown_score = _clamp(abs(max_drawdown_pct) / 50 * 100)
    concentration_score = _clamp(concentration)  # already 0-100 (HHI x 100)

    score = vol_score * 0.40 + drawdown_score * 0.30 + concentration_score * 0.30
    score = round(score, 1)

    if score <= 30:
        label = "Low Risk"
    elif score <= 60:
        label = "Medium Risk"
    else:
        label = "High Risk"

    return {
        "score": score,
        "label": label,
        "vol_score": round(vol_score, 1),
        "drawdown_score": round(drawdown_score, 1),
        "concentration_score": round(concentration_score, 1),
    }