"""
agent_tools.py — the data sources the agent can pull from (the boxes under
"Question Classifier" in the Phase 8 diagram). Each returns plain dicts/lists,
never prose, so the agent decides what to show the LLM.

  holdings_with_weights  -> Portfolio database
  period_performance     -> Stock API (prices) + contribution analysis
  risk_metrics           -> Volatility / correlation / drawdown (engine.py)
  recent_news            -> News API (news_service + stored sentiment)
  document_context       -> FAISS / RAG (rag.py)
"""

from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

import doc_fetcher
import engine
import news_service
import rag
import repository


def label(ticker: str) -> str:
    return engine.display_name(ticker)


# ---------------------------------------------------------------
# Portfolio database: weights + since-purchase returns
# ---------------------------------------------------------------
def holdings_with_weights(raw_portfolio: dict) -> dict:
    report = engine.evaluate_portfolio(raw_portfolio)
    total = report["total_current_value"] or 1
    holdings = []
    for t, h in report["holdings"].items():
        holdings.append({
            "ticker": t, "name": label(t),
            "invested": h["investment"], "current_value": h["current_value"],
            "weight_pct": round(h["current_value"] / total * 100, 1),
            "profit": h["profit"], "return_pct": h["return_pct"],
        })
    holdings.sort(key=lambda x: x["weight_pct"], reverse=True)
    return {
        "holdings": holdings,
        "total_invested": report["total_investment"],
        "total_value": report["total_current_value"],
        "total_profit": report["total_profit"],
        "total_return_pct": report["total_return_pct"],
    }


# ---------------------------------------------------------------
# Stock API: performance over a period + who contributed what
# ---------------------------------------------------------------
def get_close(tickers: list, days: int) -> pd.DataFrame:
    period = "3mo" if days <= 30 else "1y" if days <= 180 else "2y"
    data = yf.download(tickers, period=period, auto_adjust=True, progress=False)["Close"]
    if isinstance(data, pd.Series):
        data = data.to_frame(tickers[0])
    return data


def _naive(ts) -> pd.Timestamp:
    ts = pd.Timestamp(ts)
    return ts.tz_localize(None) if ts.tzinfo else ts


def period_performance(raw_portfolio: dict, days: int, extra_tickers: list = ()) -> dict:
    """Return of the portfolio and of each stock over the last `days` calendar days,
    using each holding's actual purchase date where the user recorded one.

    - Held before the period started: price return start -> end.
    - Bought DURING the period: measured from the user's own buy price, and the money
      only counts for the part of the period it was invested.
    - No purchase date recorded: assumed held the whole period (and reported in `notes`).

    Portfolio return is Modified Dietz:  gain / (start value + time-weighted money added),
    where gain = end value - start value - money added. Each stock's contribution is its own
    gain / that same denominator, so contributions add up exactly to the portfolio return.
    If every holding was bought inside the window there is no start value, so the return is
    simply gain / money invested."""
    shares = {t: h["investment"] / h["buy_price"] for t, h in raw_portfolio.items()}
    extras = [t for t in extra_tickers if t not in shares]
    all_tickers = list(shares) + extras
    close = get_close(all_tickers, days)

    notes, series = [], {}
    for t in all_tickers:
        s = close[t].dropna() if t in close else pd.Series(dtype=float)
        if len(s) < 2:
            notes.append(f"No price history for {label(t)}.")
            continue
        s = s.copy()
        s.index = pd.DatetimeIndex(s.index)
        if s.index.tz is not None:
            s.index = s.index.tz_localize(None)
        series[t] = s
    if not series:
        return {"days": days, "as_of": None, "portfolio_return_pct": None, "stocks": [],
                "biggest_contributor": None, "others": [], "notes": notes,
                "uses_purchase_dates": False, "undated": []}

    as_of = max(s.index[-1] for s in series.values())
    start_ts = as_of - timedelta(days=days)

    rows, others, undated = [], [], []
    start_total = capital_total = capital_weighted = 0.0
    for t in all_tickers:
        s = series.get(t)
        if s is None:
            continue
        end = float(s.iloc[-1])
        before = s[s.index <= start_ts]
        start = float(before.iloc[-1]) if len(before) else float(s.iloc[0])

        if t not in shares:                                   # asked about, not owned
            others.append({"ticker": t, "name": label(t), "return_pct": round((end / start - 1) * 100, 2)})
            continue

        buy_date = raw_portfolio[t].get("buy_date")
        buy_ts = _naive(buy_date) if buy_date else None
        if buy_ts is None:
            undated.append(label(t))
        elif buy_ts > as_of:
            notes.append(f"{label(t)} has a purchase date ({buy_ts.date()}) after the latest price date, "
                         "so it is left out of this period.")
            continue

        if buy_ts is not None and buy_ts > start_ts:          # bought during the period
            cost = raw_portfolio[t]["investment"]
            weight = (as_of - buy_ts).days / days
            rows.append({"ticker": t, "name": label(t), "bought_in_period": True,
                         "buy_date": buy_ts.date().isoformat(),
                         "return_pct": round((end / raw_portfolio[t]["buy_price"] - 1) * 100, 2),
                         "_start_value": 0.0, "_gain": shares[t] * end - cost})
            capital_total += cost
            capital_weighted += cost * weight
            notes.append(f"{label(t)} was bought on {buy_ts.date()}, so its return is measured from your buy "
                         f"price (₹{raw_portfolio[t]['buy_price']:,.2f}) and it counts for only part of the period.")
        else:                                                 # held at the start of the period
            if before.empty:
                notes.append(f"{label(t)} has less than {days} days of history; used its earliest price.")
            start_value = shares[t] * start
            rows.append({"ticker": t, "name": label(t), "bought_in_period": False,
                         "buy_date": buy_ts.date().isoformat() if buy_ts is not None else None,
                         "return_pct": round((end / start - 1) * 100, 2),
                         "_start_value": start_value, "_gain": shares[t] * (end - start)})
            start_total += start_value

    if undated:
        notes.append("No purchase date is recorded for " + ", ".join(undated)
                     + "; assumed held for the whole period.")

    denominator = start_total + capital_weighted if start_total > 0 else capital_total
    gain_total = sum(r["_gain"] for r in rows)
    portfolio_return = round(gain_total / denominator * 100, 2) if denominator else None
    for r in rows:
        r["weight_start_pct"] = round(r["_start_value"] / start_total * 100, 1) if start_total else 0.0
        r["contribution_pp"] = round(r["_gain"] / denominator * 100, 2) if denominator else 0.0
        del r["_start_value"], r["_gain"]

    biggest = None
    if rows and portfolio_return is not None:
        pick = min if portfolio_return < 0 else max           # who explains the move's direction
        biggest = pick(rows, key=lambda r: r["contribution_pp"])
    return {
        "days": days, "as_of": as_of.date().isoformat(), "portfolio_return_pct": portfolio_return,
        "stocks": rows, "biggest_contributor": biggest, "others": others, "notes": notes,
        "uses_purchase_dates": any(r["buy_date"] for r in rows), "undated": undated,
    }


# ---------------------------------------------------------------
# Risk: volatility, drawdown, concentration, correlation, score
# ---------------------------------------------------------------
def risk_metrics(raw_portfolio: dict, period: str = "1y") -> dict:
    history = engine.get_portfolio_history(raw_portfolio, period)
    if history.empty:
        return {"error": "Not enough overlapping price history to compute risk metrics."}
    value = history.set_index(history.columns[0])["Portfolio Value"]
    vol = engine.compute_volatility(value.pct_change().dropna())
    dd = engine.compute_max_drawdown(value)
    conc = engine.compute_concentration(engine.evaluate_portfolio(raw_portfolio))
    score = engine.compute_risk_score(vol, dd["max_drawdown_pct"], conc)

    out = {"period": period, "annual_volatility_pct": vol,
           "max_drawdown_pct": None if dd.get("insufficient_data") else dd["max_drawdown_pct"],
           "concentration_score": conc, "risk_score": score["score"], "risk_label": score["label"],
           "most_correlated": None, "avg_correlation": None}
    tickers = list(raw_portfolio)
    if len(tickers) >= 2:
        corr = engine.compute_correlation_matrix(engine.get_daily_returns(tickers, period))
        pairs = [(corr.index[i], corr.columns[j], float(corr.iloc[i, j]))
                 for i in range(len(corr)) for j in range(i + 1, len(corr))]
        if pairs:
            a, b, v = max(pairs, key=lambda p: p[2])
            out["most_correlated"] = {"a": label(a), "b": label(b), "corr": round(v, 2)}
            out["avg_correlation"] = round(sum(p[2] for p in pairs) / len(pairs), 2)
    return out


# ---------------------------------------------------------------
# News API: refresh + stored headlines with sentiment
# ---------------------------------------------------------------
def recent_news(tickers: list, per_stock: int = 4, lookback_days: int = 14, refresh: bool = True) -> list:
    if refresh:
        try:
            news_service.refresh_news(tickers)
        except Exception:
            pass                                   # stored headlines are still usable
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)
    items = [n for n in repository.list_news(tickers, per_symbol=per_stock * 2)
             if n["published_at"] is None or n["published_at"] >= cutoff]
    out, count = [], {}
    for n in sorted(items, key=lambda n: n["published_at"] or datetime.min, reverse=True):
        count[n["symbol"]] = count.get(n["symbol"], 0) + 1
        if count[n["symbol"]] <= per_stock:
            out.append({**n, "name": label(n["symbol"])})
    return out


# ---------------------------------------------------------------
# FAISS / RAG: passages from indexed annual reports
# ---------------------------------------------------------------
def document_context(question: str, tickers: list, per_company: int = 2) -> dict:
    companies = list(dict.fromkeys(doc_fetcher.company_folder(t) for t in tickers))
    indexed = rag.index_status()
    covered = [c for c in companies if c in indexed]
    chunks = rag.retrieve(question, covered, k_per_company=per_company) if covered else []
    return {"chunks": chunks, "missing": [c for c in companies if c not in indexed]}