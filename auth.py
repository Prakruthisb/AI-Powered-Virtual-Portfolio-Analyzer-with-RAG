"""
auth.py — password hashing, JWT issuing/verification, and the
register/login UI gate that every page calls before showing data.

User Flow: visit app -> Register -> Login -> JWT Token -> access
personal portfolio.
"""

import os
import bcrypt
import jwt
import streamlit as st
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

from db import get_session
from models import User
from cookies import get_cookie_manager, get_token, set_token, clear_token

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24


# ---------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


# ---------------------------------------------------------------
# JWT
# ---------------------------------------------------------------
def create_jwt(user_id: int) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str):
    """Returns the user_id if the token is valid and unexpired, else None."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload["user_id"]
    except jwt.PyJWTError:
        return None


# ---------------------------------------------------------------
# Register / authenticate
# ---------------------------------------------------------------
class AuthError(Exception):
    pass


def register_user(name: str, email: str, password: str) -> str:
    """Creates a user, returns a JWT. Raises AuthError if the email is taken."""
    email = email.strip().lower()
    with get_session() as session:
        if session.query(User).filter_by(email=email).first():
            raise AuthError("An account with that email already exists.")

        user = User(name=name.strip(), email=email, password_hash=hash_password(password))
        session.add(user)
        session.flush()  # populates user.id before commit
        return create_jwt(user.id)


def login_user(email: str, password: str) -> str:
    """Verifies credentials, returns a JWT. Raises AuthError on failure."""
    email = email.strip().lower()
    with get_session() as session:
        user = session.query(User).filter_by(email=email).first()
        if not user or not verify_password(password, user.password_hash):
            raise AuthError("Invalid email or password.")
        return create_jwt(user.id)


def get_current_user(cookies):
    """Returns the logged-in User row, or None. Reads the JWT from the
    encrypted cookie (falls back to session_state within the same run,
    since a cookie write needs one rerun to become readable)."""
    token = get_token(cookies) or st.session_state.get("jwt")
    if not token:
        return None
    user_id = decode_jwt(token)
    if user_id is None:
        return None
    with get_session() as session:
        user = session.query(User).filter_by(id=user_id).first()
        if user:
            session.expunge(user)  # detach so it's usable after the session closes
        return user


# ---------------------------------------------------------------
# Streamlit gate — call require_login() at the top of every page.
#
# IMPORTANT: the cookie manager can only be constructed ONCE per
# script run (its underlying component uses a fixed key, so a second
# instance in the same run raises StreamlitDuplicateElementKey). So
# require_login() builds it once and hands it back — pass that same
# `cookies` object to logout() and anywhere else that needs it, rather
# than calling get_cookie_manager() again.
# ---------------------------------------------------------------
def require_login():
    """Returns (user, cookies). `cookies` is the one cookie-manager
    instance for this run — reuse it, don't create another."""
    cookies = get_cookie_manager()
    user = get_current_user(cookies)
    if user:
        return user, cookies

    st.title("📈 Portfolio Dashboard")
    tab_login, tab_register = st.tabs(["Login", "Register"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Log in")
            if submitted:
                try:
                    token = login_user(email, password)
                    st.session_state["jwt"] = token
                    set_token(cookies, token)
                    st.rerun()
                except AuthError as e:
                    st.error(str(e))

    with tab_register:
        with st.form("register_form"):
            name = st.text_input("Name")
            email_r = st.text_input("Email", key="register_email")
            password_r = st.text_input("Password", type="password", key="register_password")
            confirm = st.text_input("Confirm password", type="password")
            submitted_r = st.form_submit_button("Create account")
            if submitted_r:
                if password_r != confirm:
                    st.error("Passwords don't match.")
                elif len(password_r) < 8:
                    st.error("Password must be at least 8 characters.")
                elif not name or not email_r:
                    st.error("Fill in your name and email.")
                else:
                    try:
                        token = register_user(name, email_r, password_r)
                        st.session_state["jwt"] = token
                        set_token(cookies, token)
                        st.rerun()
                    except AuthError as e:
                        st.error(str(e))

    st.stop()  # nothing below this renders until the user is logged in


def logout(cookies):
    """Pass the same `cookies` instance you got from require_login()."""
    clear_token(cookies)
    for key in ("jwt", "active_portfolio_id"):
        st.session_state.pop(key, None)
    st.rerun()