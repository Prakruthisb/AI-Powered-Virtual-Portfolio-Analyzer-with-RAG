import streamlit as st
import pandas as pd
import plotly.express as px
import auth
import context
import news_service
import sentiment
import repository
from engine import display_name

st.set_page_config(page_title="News", page_icon="📰", layout="wide")
user, cookies = auth.require_login()
raw_portfolio, portfolio_id = context.ensure_active_portfolio(user, cookies)

st.title("📰 News & Sentiment")

if not raw_portfolio:
    st.info("This portfolio has no holdings yet. Add some on the **Portfolio** page.")
    st.stop()

symbols = list(raw_portfolio.keys())
EMOJI = {"Positive": "🟢", "Neutral": "🟡", "Negative": "🔴"}

# ---- Refresh: automatically once per portfolio per session, or on button ----
auto_key = f"news_refreshed_{portfolio_id}_{len(symbols)}"
col_a, col_b = st.columns([1, 5])
force = col_a.button("🔄 Refresh news")
if force or auto_key not in st.session_state:
    with st.spinner("Fetching headlines and scoring sentiment..."):
        result = news_service.refresh_news(symbols)
    st.session_state[auto_key] = True
    st.session_state["news_last_refresh"] = result      # kept so the details survive reruns
    if force:
        st.toast(f"{result['new']} new headline(s) added.")
col_b.caption(f"Sentiment engine: **{sentiment.get_engine()}** (change via SENTIMENT_ENGINE in .env)")

last = st.session_state.get("news_last_refresh")
if last:
    if last["failed"]:
        st.warning("Couldn't fetch news for: " + ", ".join(display_name(s_) for s_ in last["failed"]))
    with st.expander("Fetch details (where headlines came from)", expanded=bool(last["failed"])):
        for sym, d in last["details"].items():
            errors = f" · ⚠️ {'; '.join(d['errors'])}" if d["errors"] else ""
            st.write(f"**{display_name(sym)}** — Yahoo {d['yahoo']}, Google News {d['google']}, "
                     f"new {d['new']}{errors}")

items = repository.list_news(symbols, per_symbol=10)
if not items:
    st.info("No news found for these holdings yet. Check **Fetch details** above, then try Refresh.")
    st.stop()

# ---- Portfolio-wide sentiment ----
overall = news_service.summarize(items)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Headlines", overall["total"])
c2.metric("🟢 Positive", overall["counts"]["Positive"])
c3.metric("🟡 Neutral", overall["counts"]["Neutral"])
c4.metric("🔴 Negative", overall["counts"]["Negative"])

# ---- Sentiment by stock ----
chart_rows = []
for s in symbols:
    summary = news_service.summarize([i for i in items if i["symbol"] == s])
    for label, n in summary["counts"].items():
        chart_rows.append({"Stock": display_name(s), "Sentiment": label, "Headlines": n})
fig = px.bar(
    pd.DataFrame(chart_rows), x="Stock", y="Headlines", color="Sentiment", barmode="stack",
    color_discrete_map={"Positive": "#2e9e5b", "Neutral": "#d9a521", "Negative": "#d1453b"},
)
fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=300)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---- Headlines per stock ----
only = st.multiselect("Filter sentiment", ["Positive", "Neutral", "Negative"],
                      default=["Positive", "Neutral", "Negative"])

for s in symbols:
    stock_items = [i for i in items if i["symbol"] == s]
    summary = news_service.summarize(stock_items)
    st.subheader(f"{display_name(s)}  ·  avg sentiment {summary['avg_score']:+.2f}")
    shown = [i for i in stock_items if i["sentiment"] in only]
    if not shown:
        st.caption("No headlines match.")
    for i in shown:
        date = i["published_at"].strftime("%d %b %Y") if i["published_at"] else ""
        st.markdown(
            f"{EMOJI[i['sentiment']]} [{i['title']}]({i['url']})  \n"
            f"<sub>{i['source']} · {date} · {i['sentiment']} ({i['score']:+.2f})</sub>",
            unsafe_allow_html=True,
        )
    st.divider()