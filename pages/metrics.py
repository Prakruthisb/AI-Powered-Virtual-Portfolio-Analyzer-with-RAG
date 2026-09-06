import streamlit as st
import plotly.express as px
from engine import (
    get_portfolio, evaluate_portfolio, get_portfolio_history,
    get_daily_returns, get_portfolio_daily_returns,
    compute_volatility, compute_correlation_matrix,
    compute_max_drawdown, compute_concentration, compute_risk_score,
    display_name,
)

st.set_page_config(page_title="Metrics", page_icon="🧮", layout="wide")
st.title("🧮 Financial Metrics")

raw_portfolio = get_portfolio()
tickers = list(raw_portfolio.keys())

period = st.select_slider(
    "Period", options=["1mo", "3mo", "6mo", "1y", "2y"], value="6mo", key="metrics_period"
)

with st.spinner("Fetching live prices..."):
    report = evaluate_portfolio(raw_portfolio)

with st.spinner("Crunching returns..."):
    stock_returns = get_daily_returns(tickers, period)
    portfolio_returns = get_portfolio_daily_returns(raw_portfolio, period)
    history = get_portfolio_history(raw_portfolio, period)

# ---- Metric 1: Daily Returns ----
st.subheader("1. Daily Returns")
st.caption("Portfolio's day-over-day % change.")
fig1 = px.line(portfolio_returns.reset_index(), x=portfolio_returns.index.name or "index",
               y=portfolio_returns.name or 0)
fig1.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=280, yaxis_tickformat=".2%")
st.plotly_chart(fig1, use_container_width=True)

st.divider()

# ---- Metric 2: Volatility ----
st.subheader("2. Volatility")
st.caption("How much the portfolio moves up and down (annualized).")
annual_vol = compute_volatility(portfolio_returns, annualize=True)
daily_vol = compute_volatility(portfolio_returns, annualize=False)

c1, c2 = st.columns(2)
c1.metric("Annualized Volatility", f"{annual_vol}%")
c2.metric("Daily Volatility", f"{daily_vol}%")

st.divider()

# ---- Metric 3: Correlation Matrix ----
st.subheader("3. Correlation Matrix")
st.caption("How closely your holdings move together. 1 = perfectly in sync, 0 = unrelated.")
corr = compute_correlation_matrix(stock_returns)
corr.columns = [display_name(c) for c in corr.columns]
corr.index = [display_name(i) for i in corr.index]

fig3 = px.imshow(corr, text_auto=True, color_continuous_scale="RdYlGn_r", zmin=-1, zmax=1)
fig3.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=400)
st.plotly_chart(fig3, use_container_width=True)

st.divider()

# ---- Metric 4: Maximum Drawdown ----
st.subheader("4. Maximum Drawdown")
st.caption("The biggest fall from a previous high point.")
value_series = history.set_index(history.columns[0])["Portfolio Value"]
dd = compute_max_drawdown(value_series)

c1, c2, c3 = st.columns(3)
c1.metric("Max Drawdown", f"{dd['max_drawdown_pct']}%")
c2.metric("Peak Value", f"₹{dd['peak_value']:,.0f}", help=str(dd["peak_date"].date()))
c3.metric("Lowest After Peak", f"₹{dd['trough_value']:,.0f}", help=str(dd["trough_date"].date()))

st.divider()

# ---- Metric 5: Portfolio Risk Score ----
st.subheader("5. Portfolio Risk Score")
concentration = compute_concentration(report)
risk = compute_risk_score(annual_vol, dd["max_drawdown_pct"], concentration)

c1, c2 = st.columns([1, 2])
with c1:
    st.metric("Risk Score", f"{risk['score']} / 100", delta=risk["label"], delta_color="off")
with c2:
    st.write("**Breakdown**")
    st.write(f"- Volatility score: {risk['vol_score']} (weight 40%)")
    st.write(f"- Drawdown score: {risk['drawdown_score']} (weight 30%)")
    st.write(f"- Concentration score: {risk['concentration_score']} (weight 30%)")

st.progress(min(int(risk["score"]), 100) / 100)
st.caption("Low Risk: 0-30 · Medium Risk: 31-60 · High Risk: 61-100")