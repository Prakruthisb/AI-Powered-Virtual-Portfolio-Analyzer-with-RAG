from datetime import date

import streamlit as st
import pandas as pd
import auth
import context
import repository
import doc_pipeline
from engine import evaluate_portfolio, search_stocks, display_name
import stock_list

st.set_page_config(page_title="Portfolio", page_icon="💼", layout="wide")
user, cookies = auth.require_login()
raw_portfolio, portfolio_id = context.ensure_active_portfolio(user, cookies)

st.title("💼 Portfolio")

if raw_portfolio:
    with st.spinner("Fetching live prices..."):
        report = evaluate_portfolio(raw_portfolio)

    # ---- Full holdings table ----
    doc_status = repository.get_doc_statuses([display_name(t).upper() for t in report["holdings"]])
    DOC_ICON = {"ready": "✅ Ready", "fetching": "⏳ Fetching", "failed": "⚠️ Failed", "unsupported": "➖ N/A"}
    rows = []
    for ticker, h in report["holdings"].items():
        ds = doc_status.get(display_name(ticker).upper())
        rows.append({
            "Stock": display_name(ticker),
            "Ticker": ticker,
            "Investment (₹)": h["investment"],
            "Buy Price (₹)": h["buy_price"],
            "Buy Date": str(raw_portfolio[ticker]["buy_date"]) if raw_portfolio[ticker].get("buy_date") else "—",
            "Shares": h["shares"],
            "Current Price (₹)": h["current_price"],
            "Current Value (₹)": h["current_value"],
            "Profit/Loss (₹)": h["profit"],
            "Return (%)": h["return_pct"],
            "Documents": DOC_ICON.get(ds["status"], "—") if ds else "—",
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
ALL_STOCKS = stock_list.load_stocks()          # full NSE list (or the built-in popular list as a fallback)
NSE_LABELS = {f"{name} ({symbol})": symbol for symbol, name in ALL_STOCKS}

find_mode = st.radio(
    "Find a stock", ["Pick from NSE-listed stocks", "Search by name or ticker"],
    horizontal=True, label_visibility="collapsed",
)

selected_symbol = None
selected_label = None

if find_mode == "Pick from NSE-listed stocks":
    selected_label = st.selectbox(
        "Stock",
        options=list(NSE_LABELS.keys()),
        index=None,
        placeholder="Type to search e.g. 'Tata', 'Infosys', 'HDFC'...",
    )
    if selected_label:
        selected_symbol = NSE_LABELS[selected_label]

    info = stock_list.status()
    cap, btn = st.columns([5, 1])
    if info["source"] == "nse":
        cap.caption(f"{info['count']:,} NSE-listed stocks · list updated {info['updated']:%d %b %Y}. "
                    "Not listed here? Use **Search by name or ticker**.")
    else:
        cap.caption(f"Showing {info['count']} popular stocks — the full NSE list "
                    f"{'is downloading…' if info['refreshing'] else 'has not been downloaded yet.'} "
                    "Use **Search by name or ticker** for any other stock.")
    if btn.button("Update list", help="Download NSE's latest list of listed stocks"):
        with st.spinner("Downloading NSE's stock list..."):
            ok, msg = stock_list.refresh()
        (st.toast if ok else st.error)(msg)
        if ok:
            st.rerun()
    elif info["error"] and info["source"] != "nse":
        st.caption(f"⚠️ {info['error']}")
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
    c1, c2, c3 = st.columns(3)
    investment = c1.number_input("Investment (₹)", min_value=0.0, step=1000.0)
    buy_price = c2.number_input("Buy Price (₹)", min_value=0.0, step=10.0)
    buy_date = c3.date_input("Purchase date (optional)", value=None, max_value=date.today(),
                             help="Lets the assistant measure returns over a period correctly. "
                                  "Without it, a holding is assumed to have been held the whole time.")
    submitted = st.form_submit_button("Add")

    if submitted:
        if not selected_symbol or investment <= 0 or buy_price <= 0:
            st.error("Pick a stock above, and fill in investment and buy price.")
        else:
            repository.add_holding(portfolio_id, selected_symbol, investment, buy_price, buy_date)
            # Fetch + index this company's annual reports in the background (returns instantly).
            doc_pipeline.ensure_documents(selected_symbol)
            st.toast(f"Added {selected_symbol}. Fetching its documents in the background...")
            st.rerun()

# ---- Set / change the purchase date of an existing holding ----
if raw_portfolio:
    with st.expander("Set or change a purchase date"):
        st.caption("The assistant uses purchase dates to measure returns over a period. "
                   "Holdings without one are assumed to have been held the whole time.")
        date_ticker = st.selectbox("Holding", options=list(raw_portfolio.keys()), key="date_ticker")
        current = raw_portfolio[date_ticker].get("buy_date")
        new_date = st.date_input("Purchase date", value=current, max_value=date.today(), key=f"date_for_{date_ticker}")
        if st.button("Save date") and new_date:
            repository.set_buy_date(portfolio_id, date_ticker, new_date)
            st.toast(f"Saved purchase date for {date_ticker}.")
            st.rerun()

# ---- Remove a holding ----
if raw_portfolio:
    remove_ticker = st.selectbox("Remove a holding", options=["—"] + list(raw_portfolio.keys()))
    if remove_ticker != "—" and st.button("Remove"):
        repository.remove_holding(portfolio_id, remove_ticker)
        st.success(f"Removed {remove_ticker}.")
        st.rerun()