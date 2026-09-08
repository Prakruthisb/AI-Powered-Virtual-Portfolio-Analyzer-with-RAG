import streamlit as st
import plotly.express as px
import auth
import context
from engine import evaluate_portfolio, get_portfolio_history, display_name

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
user, cookies = auth.require_login()
raw_portfolio, portfolio_id = context.ensure_active_portfolio(user, cookies)

st.title("📊 Dashboard")

if not raw_portfolio:
    st.info("This portfolio has no holdings yet. Add some on the **Portfolio** page.")
    st.stop()

with st.spinner("Fetching live prices..."):
    report = evaluate_portfolio(raw_portfolio)

# ---- Top metrics (matches the mock: Value / Invested / P&L / Return) ----
col1, col2, col3, col4 = st.columns(4)
col1.metric("Portfolio Value", f"₹{report['total_current_value']:,.0f}")
col2.metric("Total Invested", f"₹{report['total_investment']:,.0f}")
sign = "+" if report["total_profit"] >= 0 else ""
col3.metric("Profit/Loss", f"{sign}₹{report['total_profit']:,.0f}")
col4.metric("Total Return", f"{sign}{report['total_return_pct']}%")

st.divider()

# ---- Portfolio Performance Chart ----
st.subheader("Portfolio Performance")
period = st.select_slider(
    "Period", options=["1mo", "3mo", "6mo", "1y", "2y"], value="6mo"
)
with st.spinner("Building growth chart..."):
    history = get_portfolio_history(raw_portfolio, period)

if history.empty:
    st.info("Not enough overlapping price history for this period yet — try a longer period.")
else:
    fig = px.line(history, x=history.columns[0], y="Portfolio Value")
    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=350)
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---- Holdings quick list ----
st.subheader("Holdings")
for ticker, h in report["holdings"].items():
    sign = "+" if h["profit"] >= 0 else ""
    st.write(
        f"**{display_name(ticker)}** — ₹{h['current_value']:,.0f} "
        f"({sign}₹{h['profit']:,.0f}, {sign}{h['return_pct']}%)"
    )