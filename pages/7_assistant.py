import streamlit as st
import auth
import context
import agent
import llm
from engine import display_name

st.set_page_config(page_title="Assistant", page_icon="🤖", layout="wide")
user, cookies = auth.require_login()
raw_portfolio, portfolio_id = context.ensure_active_portfolio(user, cookies)

st.title("🤖 Portfolio Assistant")
st.caption("Ask about returns, risk, why your portfolio moved, or what your companies' reports say. "
           "Answers use only your own data, and you can see exactly what was used. "
           "I remember the last few questions in this chat, so follow-ups like \u201cand Infosys?\u201d or "
           "\u201cwhat about last month?\u201d work.")

if not raw_portfolio:
    st.info("This portfolio has no holdings yet. Add some on the **Portfolio** page.")
    st.stop()

if llm.is_configured():
    st.caption(f"Model: {llm.describe()}")
else:
    st.warning("No LLM is configured, so I can gather your data but can't write answers. "
               "Set `LLM_PROVIDER`, `LLM_API_KEY` and `LLM_MODEL` in `.env`, then restart the app.")

SUGGESTIONS = [
    "What is my portfolio return?",
    "How risky is my portfolio?",
    "Why did my portfolio fall this week?",
    "What are the major risks for "
    + display_name(max(raw_portfolio, key=lambda t: raw_portfolio[t]["investment"])) + "?",
]
SENT_ICON = {"Positive": "🟢", "Neutral": "🟡", "Negative": "🔴"}

history = st.session_state.setdefault(f"chat_{portfolio_id}", [])


def render_result(res: dict):
    if res["answer"]:
        st.markdown(res["answer"])
    else:
        st.warning(f"{res['error']}  Here is the data I gathered instead:")
        st.code(res["context"] or "(nothing gathered)", language=None)

    if not res["trace"]:
        return
    with st.expander("How I answered"):
        st.caption("Question type: " + ", ".join(res["routes"]))
        for i, s in enumerate(res["trace"], 1):
            st.write(f"{'✅' if s['ok'] else '⚠️'} **Step {i}: {s['step']}** — {s['detail']}")
        if res["news"]:
            st.markdown("**News used**")
            for i, n in enumerate(res["news"], 1):
                st.markdown(f"[N{i}] {SENT_ICON.get(n['sentiment'], '')} [{n['title']}]({n['url']}) "
                            f"· {n['source']} · {n['name']}")
        if res["docs"]:
            st.markdown("**Documents used**")
            for i, d in enumerate(res["docs"], 1):
                m = d["metadata"]
                st.markdown(f"[D{i}] {m['company']} · {m['document']} {m['year'] or ''} · "
                            f"{m['section']} · p.{m['page']}")
        st.caption("Exact data given to the model:")
        st.code(res["context"], language=None)


if history and st.button("Clear chat"):
    history.clear()
    st.rerun()

if not history:
    st.write("Try one of these:")
    cols = st.columns(len(SUGGESTIONS))
    for col, q in zip(cols, SUGGESTIONS):
        if col.button(q, key=f"sugg_{q}"):
            st.session_state["pending_question"] = q
            st.rerun()

for msg in history:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.write(msg["content"])
        else:
            render_result(msg["result"])

question = st.chat_input("Ask about your portfolio...") or st.session_state.pop("pending_question", None)
if question:
    history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        with st.spinner("Gathering your data and thinking..."):
            earlier = [m["result"] for m in history if m["role"] == "assistant"]
            result = agent.answer(question, raw_portfolio, history=earlier)
        render_result(result)
    history.append({"role": "assistant", "result": result})