import streamlit as st
import auth
import context
import rag
import repository
import doc_pipeline
from engine import display_name

st.set_page_config(page_title="Documents", page_icon="📚", layout="wide")
user, cookies = auth.require_login()
raw_portfolio, portfolio_id = context.ensure_active_portfolio(user, cookies)

st.title("📚 Financial Documents")
st.caption("Annual reports are fetched automatically when you add a stock, then searched here.")

if not raw_portfolio:
    st.info("This portfolio has no holdings yet. Add some on the **Portfolio** page.")
    st.stop()

ticker_of = {display_name(t).upper(): t for t in raw_portfolio}   # TCS -> TCS.NS
portfolio_companies = list(ticker_of)

# Holdings added before this feature existed (or never attempted): start them now.
known = repository.get_doc_statuses(portfolio_companies)
for company, ticker in ticker_of.items():
    if company not in known:
        doc_pipeline.ensure_documents(ticker)

ICON = {"ready": "✅", "fetching": "⏳", "failed": "⚠️", "unsupported": "➖"}
any_fetching = any(s["status"] == "fetching"
                   for s in repository.get_doc_statuses(portfolio_companies).values())


# Only this panel refreshes itself (every 4s) while something is downloading.
@st.fragment(run_every=4 if any_fetching else None)
def status_panel():
    statuses = repository.get_doc_statuses(portfolio_companies)
    fetching_now = any(s["status"] == "fetching" for s in statuses.values())

    # When the last job finishes, rerun the whole page so search unlocks.
    if st.session_state.get("_docs_were_fetching") and not fetching_now:
        st.session_state["_docs_were_fetching"] = False
        st.rerun()
    st.session_state["_docs_were_fetching"] = fetching_now

    st.subheader("Document status")
    for company in portfolio_companies:
        s = statuses.get(company)
        if s is None:
            st.write(f"⏳ **{company}** — starting...")
            continue
        c1, c2 = st.columns([6, 1])
        c1.write(f"{ICON.get(s['status'], '•')} **{company}** — {s['message']}")
        if s["status"] == "failed" and c2.button("Retry", key=f"retry_{company}"):
            doc_pipeline.ensure_documents(ticker_of[company])
            st.rerun()  # full rerun so the auto-refresh starts


status_panel()
st.caption("Failed? You can also drop PDFs into `data/<TICKER>/` and run `python ingest.py`.")
st.divider()

# ---- Search ----
status = rag.index_status()
covered = [c for c in portfolio_companies if c in status]

if not status:
    st.info("Nothing to search yet — documents are still being prepared.")
    st.stop()

scope = st.radio("Search in", ["My portfolio companies", "All indexed companies"], horizontal=True)
companies = covered if scope == "My portfolio companies" else sorted(status)
st.caption("Searching: " + (", ".join(f"{c} ({status[c]} chunks)" for c in companies) or "—"))

with st.form("ask"):
    question = st.text_input(
        "Your question", placeholder="What are the major risks of my portfolio?"
    )
    k = st.slider("Chunks per company", 1, 8, 3)
    submitted = st.form_submit_button("Search")

if submitted:
    if not question.strip():
        st.error("Type a question first.")
    elif not companies:
        st.error("None of your holdings have indexed documents yet.")
    else:
        with st.spinner("Searching documents..."):
            results = rag.retrieve(question, companies, k_per_company=k)
        if not results:
            st.info("No matching passages found.")
        for r in results:
            m = r["metadata"]
            year = f" {m['year']}" if m["year"] else ""
            title = (f"{m['company']} · {m['document']}{year} · {m['section']} "
                     f"· p.{m['page']}  —  relevance {r['similarity']:.2f}")
            with st.expander(title):
                st.write(r["text"])
                st.caption(f"Source file: {m['source']}")