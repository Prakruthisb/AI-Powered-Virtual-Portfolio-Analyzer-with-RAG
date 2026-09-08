import streamlit as st
import pandas as pd
import auth
import context
import repository
from engine import evaluate_portfolio, search_stocks, display_name
from stock_universe import NSE_STOCKS

st.set_page_config(page_title="Portfolio", page_icon="💼", layout="wide")
user, cookies = auth.require_login()
raw_portfolio, portfolio_id = context.ensure_active_portfolio(user, cookies)

st.title("💼 Portfolio")

if raw_portfolio:
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
        use_container_width=True,
        hide_index=True,
        column_config={
            "Return (%)": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )
else:
    st.info("No holdings yet — add your first one below.")

st.divider()

# ---- Add a holding ----
st.subheader("Add a holding")

# Stock picker lives OUTSIDE the form below: Streamlit forms only rerun on
# submit, but the search box needs to react on every keystroke.
NSE_LABELS = {f"{name} ({symbol})": symbol for symbol, name in NSE_STOCKS}

find_mode = st.radio(
    "Find a stock", ["Pick from common NSE stocks", "Search by name or ticker"],
    horizontal=True, label_visibility="collapsed",
)

selected_symbol = None
selected_label = None

if find_mode == "Pick from common NSE stocks":
    selected_label = st.selectbox(
        "Stock",
        options=list(NSE_LABELS.keys()),
        index=None,
        placeholder="Type to search e.g. 'Tata', 'Infosys', 'HDFC'...",
    )
    if selected_label:
        selected_symbol = NSE_LABELS[selected_label]
else:
    query = st.text_input(
        "Search by company name or ticker",
        placeholder="e.g. Zomato, Nykaa, Apple, TSLA...",
    )
    if query and len(query.strip()) >= 2:
        with st.spinner("Searching..."):
            results = search_stocks(query)
        if results:
            result_options = {
                f"{r['name']} ({r['symbol']}) · {r['exchange']}": r["symbol"]
                for r in results
            }
            selected_label = st.selectbox("Matches", options=list(result_options.keys()))
            if selected_label:
                selected_symbol = result_options[selected_label]
        else:
            st.caption("No matches yet — keep typing, or check the spelling.")

if selected_symbol:
    st.caption(f"Selected: **{selected_symbol}**")

with st.form("add_holding", clear_on_submit=True):
    c1, c2 = st.columns(2)
    investment = c1.number_input("Investment (₹)", min_value=0.0, step=1000.0)
    buy_price = c2.number_input("Buy Price (₹)", min_value=0.0, step=10.0)
    submitted = st.form_submit_button("Add")

    if submitted:
        if not selected_symbol or investment <= 0 or buy_price <= 0:
            st.error("Pick a stock above, and fill in investment and buy price.")
        else:
            repository.add_holding(portfolio_id, selected_symbol, investment, buy_price)
            st.success(f"Added {selected_symbol}.")
            st.rerun()

# ---- Remove a holding ----
if raw_portfolio:
    remove_ticker = st.selectbox("Remove a holding", options=["—"] + list(raw_portfolio.keys()))
    if remove_ticker != "—" and st.button("Remove"):
        repository.remove_holding(portfolio_id, remove_ticker)
        st.success(f"Removed {remove_ticker}.")
        st.rerun()