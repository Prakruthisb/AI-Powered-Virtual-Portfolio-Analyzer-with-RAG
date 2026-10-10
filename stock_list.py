"""
stock_list.py — the full list of NSE-listed stocks for the "add a holding" dropdown.

Source: NSE's list of equity securities (EQUITY_L.csv: SYMBOL, NAME OF COMPANY, SERIES, ...).
  * Cached in .nse_cache/equity_list.csv and refreshed in the background when older than a week.
  * If the cache doesn't exist yet (or NSE can't be reached) the built-in list of ~125 popular
    stocks from stock_universe.py is used, so the dropdown is never empty.
  * Popular stocks (the built-in list) are shown first, with their friendlier names; the rest
    follow alphabetically.
  * If NSE blocks the automatic download, download EQUITY_L.csv in your browser and run:
        python update_stock_list.py path/to/EQUITY_L.csv

Only regular equity series are kept (EQ, BE). SME-board stocks are skipped (thin Yahoo data).
"""

import csv
import io
import os
import re
import threading
import time
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import requests

from stock_universe import NSE_STOCKS

BASE = Path(__file__).parent
CACHE_FILE = BASE / ".nse_cache" / "equity_list.csv"
URLS = [u for u in (
    os.getenv("NSE_EQUITY_LIST_URL"),
    "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
    "https://archives.nseindia.com/content/equities/EQUITY_L.csv",
) if u]
MAX_AGE_DAYS = 7
RETRY_AFTER_SECONDS = 600      # after a failed background refresh, wait before trying again
MIN_ROWS = 300                 # the real list has ~2,000; anything far smaller is an error page
KEEP_SERIES = {"EQ", "BE"}
AUTO_REFRESH = os.getenv("STOCK_LIST_AUTO_REFRESH", "1") != "0"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
           "Accept": "text/csv,*/*;q=0.8", "Referer": "https://www.nseindia.com/"}

_lock = threading.Lock()
_thread = None
_last_attempt = 0.0
_last_error = None


class StockListError(Exception):
    """Something we can explain to the user in one sentence."""


# ---------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------
def clean_name(name: str, symbol: str) -> str:
    name = re.sub(r"\s+", " ", (name or "")).strip()          # NSE has stray double spaces
    name = re.sub(r"\s+(limited|ltd\.?)$", "", name, flags=re.I).strip()
    return name or symbol                                      # a few rows have no name


def parse_equity_csv(text: str) -> list:
    """NSE's CSV -> [(symbol, clean name)]. Headers have stray spaces (' SERIES'), so
    they're normalised. Raises StockListError if this doesn't look like the real list."""
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if not reader.fieldnames:
        raise StockListError("The file is empty.")
    cols = {(f or "").strip().upper(): f for f in reader.fieldnames}
    if "SYMBOL" not in cols or not any(c.startswith("NAME") for c in cols):
        raise StockListError("That doesn't look like NSE's equity list (no SYMBOL / NAME columns).")
    name_col = cols[next(c for c in cols if c.startswith("NAME"))]
    series_col = cols.get("SERIES")

    rows, seen = [], set()
    for r in reader:
        symbol = (r.get(cols["SYMBOL"]) or "").strip().upper()
        series = (r.get(series_col) or "").strip().upper() if series_col else "EQ"
        if not symbol or symbol in seen or (series_col and series not in KEEP_SERIES):
            continue
        seen.add(symbol)
        rows.append((symbol, clean_name(r.get(name_col), symbol)))
    if len(rows) < MIN_ROWS:
        raise StockListError(f"Only {len(rows)} stocks found; expected about 2,000. The download may be an error page.")
    return rows


# ---------------------------------------------------------------
# Cache file
# ---------------------------------------------------------------
def _write_cache(rows: list):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_FILE.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "name"])
        w.writerows(rows)
    os.replace(tmp, CACHE_FILE)                                # readers never see a half-written file


@lru_cache(maxsize=1)
def _read_cache(stamp: float):
    """`stamp` is the file's mtime, so a refreshed file is picked up automatically."""
    with open(CACHE_FILE, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        next(r, None)
        return [(row[0], row[1]) for row in r if len(row) >= 2]


def _cache_mtime():
    try:
        return CACHE_FILE.stat().st_mtime
    except OSError:
        return None


def _is_stale() -> bool:
    m = _cache_mtime()
    return m is None or (time.time() - m) > MAX_AGE_DAYS * 86400


# ---------------------------------------------------------------
# Refresh: download, or import a file the user downloaded
# ---------------------------------------------------------------
def refresh() -> tuple:
    """Download the list now. Returns (ok, message). A failure keeps the old cache."""
    global _last_error
    problems = []
    for url in URLS:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            rows = parse_equity_csv(resp.content.decode("utf-8-sig", errors="replace"))
            _write_cache(rows)
            _last_error = None
            return True, f"Loaded {len(rows):,} NSE stocks."
        except StockListError as e:
            problems.append(str(e))
        except requests.RequestException as e:
            problems.append(f"{type(e).__name__}")
    _last_error = ("Couldn't download NSE's stock list (" + "; ".join(dict.fromkeys(problems)) + "). "
                   "Download EQUITY_L.csv from NSE in your browser and run: python update_stock_list.py <file>")
    return False, _last_error


def import_csv(path) -> tuple:
    """Use a CSV you downloaded yourself (same format as NSE's EQUITY_L.csv)."""
    global _last_error
    try:
        rows = parse_equity_csv(Path(path).read_text(encoding="utf-8-sig", errors="replace"))
    except (OSError, StockListError) as e:
        return False, str(e)
    _write_cache(rows)
    _last_error = None
    return True, f"Imported {len(rows):,} NSE stocks."


def _refresh_in_background():
    global _thread, _last_attempt
    with _lock:
        if (_thread and _thread.is_alive()) or time.time() - _last_attempt < RETRY_AFTER_SECONDS:
            return
        _last_attempt = time.time()
        _thread = threading.Thread(target=refresh, daemon=True)
        _thread.start()


# ---------------------------------------------------------------
# Public API
# ---------------------------------------------------------------
def load_stocks() -> list:
    """[(ticker like 'TCS.NS', display name)] — popular stocks first, then the rest A-Z.
    Never blocks on the network and never returns an empty list."""
    if AUTO_REFRESH and _is_stale():
        _refresh_in_background()
    mtime = _cache_mtime()
    rows = _read_cache(mtime) if mtime else None
    if not rows:
        return list(NSE_STOCKS)

    full = {f"{sym}.NS": name for sym, name in rows}
    popular = [(t, n) for t, n in NSE_STOCKS if t in full]    # popular first, with friendly names
    popular_set = {t for t, _ in popular}
    rest = sorted(((t, n) for t, n in full.items() if t not in popular_set), key=lambda x: x[1].lower())
    return popular + rest


def status() -> dict:
    mtime = _cache_mtime()
    return {
        "source": "nse" if mtime else "built-in",
        "count": len(load_stocks()),
        "updated": datetime.fromtimestamp(mtime) if mtime else None,
        "refreshing": bool(_thread and _thread.is_alive()),
        "error": _last_error,
    }