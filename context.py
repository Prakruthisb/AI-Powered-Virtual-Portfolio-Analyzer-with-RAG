"""
context.py — the one thing every page calls (after auth.require_login())
to get "which portfolio is active" and its holdings as a dict, plus a
sidebar switcher so a user with multiple portfolios (Portfolio 1, Portfolio 2...)
can pick one.
"""

import streamlit as st
import repository


def ensure_active_portfolio(user, cookies) -> tuple:
    """Returns (raw_portfolio_dict, portfolio_id) for the currently selected portfolio.
    Creates a first portfolio automatically for brand-new users.
    `cookies` must be the same instance returned by auth.require_login() —
    see the note in auth.py about why a second instance isn't safe to create."""
    portfolios = repository.list_portfolios(user.id)

    if not portfolios:
        new_id = repository.create_portfolio(user.id, "My Portfolio")
        portfolios = repository.list_portfolios(user.id)

    options = {p["name"]: p["id"] for p in portfolios}

    # Keep the previously selected portfolio if it still exists, else default to the first.
    current_id = st.session_state.get("active_portfolio_id")
    current_name = next((n for n, i in options.items() if i == current_id), None)
    default_name = current_name or list(options.keys())[0]

    with st.sidebar:
        st.caption(f"Logged in as **{user.name}**")
        selected_name = st.selectbox("Portfolio", options=list(options.keys()), index=list(options.keys()).index(default_name))

        with st.expander("+ New portfolio"):
            new_name = st.text_input("Name", key="new_portfolio_name")
            if st.button("Create") and new_name.strip():
                repository.create_portfolio(user.id, new_name)
                st.rerun()

        if st.button("Log out"):
            import auth
            auth.logout(cookies)

    portfolio_id = options[selected_name]
    st.session_state["active_portfolio_id"] = portfolio_id

    raw_portfolio = repository.get_holdings_dict(portfolio_id)
    return raw_portfolio, portfolio_id