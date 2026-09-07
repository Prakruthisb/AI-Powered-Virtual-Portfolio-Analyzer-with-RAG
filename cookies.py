"""
cookies.py — persists the JWT in an encrypted browser cookie so a page
refresh (or closing/reopening the tab) doesn't log the user out.
st.session_state alone doesn't survive a refresh; a cookie does.

Note: streamlit-cookies-manager still calls the old `st.cache` API,
which modern Streamlit removed in favor of st.cache_data/cache_resource.
The two-line shim below restores it before importing the package —
that's the only thing making this compatible with current Streamlit.
"""

import os
import streamlit as st

if not hasattr(st, "cache"):
    st.cache = st.cache_resource  # compat shim, see module docstring

from streamlit_cookies_manager import EncryptedCookieManager  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

COOKIE_PASSWORD = os.getenv("COOKIE_PASSWORD", "dev-cookie-password-change-me")
JWT_COOKIE_KEY = "jwt"


def get_cookie_manager() -> EncryptedCookieManager:
    """Create fresh each run (cheap) — this is the library's intended pattern,
    not something to cache in session_state."""
    cookies = EncryptedCookieManager(prefix="portfolio_app/", password=COOKIE_PASSWORD)
    if not cookies.ready():
        st.stop()  # the underlying component needs one extra run to sync from the browser
    return cookies


def get_token(cookies: EncryptedCookieManager) -> str | None:
    return cookies.get(JWT_COOKIE_KEY) or None


def set_token(cookies: EncryptedCookieManager, token: str):
    cookies[JWT_COOKIE_KEY] = token
    cookies.save()


def clear_token(cookies: EncryptedCookieManager):
    # NOTE: cookies.__delitem__ (del cookies[key]) is broken in this library —
    # it checks `key in self._cookies` against the RAW browser cookie dict,
    # whose keys are prefixed (e.g. "portfolio_app/jwt"), against an
    # unprefixed `key` ("jwt"). That condition is always False, so a real
    # delete silently no-ops and the cookie never clears. Overwriting with
    # an empty string uses __setitem__ instead, which prefixes correctly
    # and does work — get_token() below already treats "" as "no token".
    cookies[JWT_COOKIE_KEY] = ""
    cookies.save()