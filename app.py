import streamlit as st
from engine import get_portfolio, evaluate_portfolio

st.set_page_config(page_title="Portfolio Dashboard", page_icon="📈", layout="wide")

st.title("📈 My Portfolio Dashboard")
st.caption("Phase 2 — no login, just your holdings and live numbers.")

raw_portfolio = get_portfolio()

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

st.markdown("**📰 News** — latest headlines for your holdings.")
st.caption("Use the sidebar to navigate between pages.")