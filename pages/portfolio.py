import streamlit as st
import pandas as pd
from engine import get_portfolio, evaluate_portfolio, display_name

st.set_page_config(page_title="Portfolio", page_icon="💼", layout="wide")
st.title("💼 Portfolio")

raw_portfolio = get_portfolio()

with st.spinner("Fetching live prices..."):
    report = evaluate_portfolio(raw_portfolio)

# ---- Full holdings table ----
rows = []
for ticker, h in report["holdings"].items():
    rows.append({
        "Stock": display_name(ticker),
        "Ticker": ticker,
        "Investment (₹)": h["investment"],
        "Buy Price (₹)": h["buy_price"],
        "Shares": h["shares"],
        "Current Price (₹)": h["current_price"],
        "Current Value (₹)": h["current_value"],
        "Profit/Loss (₹)": h["profit"],
        "Return (%)": h["return_pct"],
    })

df = pd.DataFrame(rows)
st.dataframe(
    df,
    width='stretch',
    hide_index=True,
    column_config={
        "Return (%)": st.column_config.NumberColumn(format="%.2f%%"),
    },
)

st.divider()

# ---- Add a holding ----
st.subheader("Add a holding")
with st.form("add_holding", clear_on_submit=True):
    c1, c2, c3 = st.columns(3)
    ticker = c1.text_input("Ticker (e.g. WIPRO.NS)").strip().upper()
    investment = c2.number_input("Investment (₹)", min_value=0.0, step=1000.0)
    buy_price = c3.number_input("Buy Price (₹)", min_value=0.0, step=10.0)
    submitted = st.form_submit_button("Add")

    if submitted:
        if not ticker or investment <= 0 or buy_price <= 0:
            st.error("Fill in a ticker, investment, and buy price.")
        else:
            st.session_state["portfolio_raw"][ticker] = {
                "investment": investment,
                "buy_price": buy_price,
            }
            st.success(f"Added {ticker}. Refresh the page to see it everywhere.")
            st.rerun()

# ---- Remove a holding ----
if raw_portfolio:
    remove_ticker = st.selectbox("Remove a holding", options=["—"] + list(raw_portfolio.keys()))
    if remove_ticker != "—" and st.button("Remove"):
        del st.session_state["portfolio_raw"][remove_ticker]
        st.success(f"Removed {remove_ticker}.")
        st.rerun()