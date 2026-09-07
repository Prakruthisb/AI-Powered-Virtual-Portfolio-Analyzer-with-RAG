import streamlit as st
import plotly.express as px
import auth
import context
from engine import (
    evaluate_portfolio, get_portfolio_history,
    get_normalized_prices, display_name,
)

st.set_page_config(page_title="Analytics", page_icon="📈", layout="wide")
user, cookies = auth.require_login()
raw_portfolio, portfolio_id = context.ensure_active_portfolio(user, cookies)

st.title("📈 Analytics")

if not raw_portfolio:
    st.info("This portfolio has no holdings yet. Add some on the **Portfolio** page.")
    st.stop()

tickers = list(raw_portfolio.keys())

with st.spinner("Fetching live prices..."):
    report = evaluate_portfolio(raw_portfolio)

period = st.select_slider(
    "Period", options=["1mo", "3mo", "6mo", "1y", "2y"], value="6mo", key="analytics_period"
)

# ---- 1. Portfolio Growth Chart ----
st.subheader("1. Portfolio Growth Chart")
with st.spinner("Building growth chart..."):
    history = get_portfolio_history(raw_portfolio, period)
fig1 = px.line(history, x=history.columns[0], y="Portfolio Value")
fig1.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=350)
st.plotly_chart(fig1, use_container_width=True)

st.divider()

# ---- 2. Asset Allocation Pie Chart ----
st.subheader("2. Asset Allocation")
basis = st.radio("Weight by", ["Current Value", "Investment"], horizontal=True)
key = "current_value" if basis == "Current Value" else "investment"
pie_df = [
    {"Stock": display_name(t), "Value": h[key]}
    for t, h in report["holdings"].items()
]
fig2 = px.pie(pie_df, names="Stock", values="Value", hole=0.35)
fig2.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=400)
st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ---- 3. Individual Stock Performance ----
st.subheader("3. Individual Stock Performance")
st.caption("Rebased to 100 at the start of the period, so stocks are comparable regardless of price.")
with st.spinner("Fetching historical prices..."):
    norm = get_normalized_prices(tickers, period)

date_col = norm.columns[0]
melted = norm.melt(id_vars=date_col, var_name="Stock", value_name="Normalized Price")
melted["Stock"] = melted["Stock"].apply(display_name)

fig3 = px.line(melted, x=date_col, y="Normalized Price", color="Stock")
fig3.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=400)
st.plotly_chart(fig3, use_container_width=True)