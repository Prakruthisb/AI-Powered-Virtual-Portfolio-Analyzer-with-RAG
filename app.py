import streamlit as st
from db import init_db
import auth
import context
from engine import evaluate_portfolio

st.set_page_config(page_title="Portfolio Dashboard", page_icon="📈", layout="wide")
init_db()

# ---- User Flow: visit -> Register/Login -> JWT -> personal portfolio ----
user, cookies = auth.require_login()
raw_portfolio, portfolio_id = context.ensure_active_portfolio(user, cookies)

st.title("📈 My Portfolio Dashboard")
st.caption(f"Welcome back, {user.name}.")

if not raw_portfolio:
    st.info("This portfolio has no holdings yet. Add some on the **Portfolio** page.")
else:
    with st.spinner("Fetching live prices..."):
        report = evaluate_portfolio(raw_portfolio)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Portfolio Value", f"₹{report['total_current_value']:,.0f}")
    col2.metric("Total Invested", f"₹{report['total_investment']:,.0f}")
    col3.metric(
        "Profit / Loss",
        f"₹{report['total_profit']:,.0f}",
        delta=f"{report['total_return_pct']}%",
    )
    col4.metric("Holdings", f"{len(report['holdings'])}")

st.divider()
st.subheader("Where to go next")

c1, c2, c3 = st.columns(3)
with c1:
    st.markdown("**📊 Dashboard**")
    st.write("Growth chart + top-line summary.")
with c2:
    st.markdown("**💼 Portfolio**")
    st.write("Full holdings table, add/edit stocks.")
with c3:
    st.markdown("**📈 Analytics**")
    st.write("Allocation pie chart + stock comparison.")

st.markdown("**🧮 Metrics** — volatility, correlation, drawdown, risk score.")
st.markdown("**📰 News** — latest headlines for your holdings.")
st.caption("Use the sidebar to navigate between pages, or switch portfolios.")