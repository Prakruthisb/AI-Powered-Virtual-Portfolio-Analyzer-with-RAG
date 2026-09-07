import streamlit as st
from datetime import datetime
import auth
import context
from engine import get_news, display_name

st.set_page_config(page_title="News", page_icon="📰", layout="wide")
user, cookies = auth.require_login()
raw_portfolio, portfolio_id = context.ensure_active_portfolio(user, cookies)

st.title("📰 News")
st.caption("Latest headlines for each stock in your portfolio.")

if not raw_portfolio:
    st.info("This portfolio has no holdings yet. Add some on the **Portfolio** page.")
    st.stop()

for ticker in raw_portfolio:
    st.subheader(display_name(ticker))
    with st.spinner(f"Fetching news for {display_name(ticker)}..."):
        items = get_news(ticker)

    if not items:
        st.write("No recent news found.")
        st.divider()
        continue

    for item in items:
        content = item.get("content", item)  # yfinance news schema varies by version
        title = content.get("title") or item.get("title", "Untitled")
        link = (content.get("canonicalUrl", {}) or {}).get("url") or item.get("link", "#")
        publisher = (content.get("provider", {}) or {}).get("displayName") or item.get("publisher", "")
        pub_date = content.get("pubDate") or item.get("providerPublishTime")

        date_str = ""
        if isinstance(pub_date, (int, float)):
            date_str = datetime.fromtimestamp(pub_date).strftime("%d %b %Y")
        elif isinstance(pub_date, str):
            date_str = pub_date[:10]

        st.markdown(f"- [{title}]({link})  \n  <sub>{publisher} · {date_str}</sub>", unsafe_allow_html=True)

    st.divider()