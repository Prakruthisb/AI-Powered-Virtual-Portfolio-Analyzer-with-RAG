"""
doc_fetcher.py — download a company's annual reports from NSE into data/<TICKER>/.

Uses the unofficial `nse` package (pip install nse), which handles NSE's cookie
session, throttling and retries. Source: NSE's corporate-filings annual-reports
listing. This is an unofficial interface, so NSE can change or block it; every
failure is reported back (never raised into the UI) and the manual route
(drop PDFs into data/<TICKER>/, run `python ingest.py`) always still works.

Files are saved as annual_report_<year>.pdf so rag.py reads document type and
year straight from the file name.
"""

import os
import re
import shutil
import tempfile
from pathlib import Path

import rag

BASE = Path(__file__).parent
NSE_CACHE = BASE / ".nse_cache"                       # cookie file lives here
MAX_REPORTS = int(os.getenv("DOC_MAX_REPORTS", "3"))  # latest N annual reports per company


class FetchError(Exception):
    """A problem we can explain to the user in one sentence."""


def company_folder(ticker: str) -> str:
    """TCS.NS -> TCS (same naming engine.display_name uses, so folders match holdings)."""
    return ticker.strip().upper().replace(".NS", "").replace(".BO", "")


def to_nse_symbol(ticker: str):
    """NSE symbol for a yfinance ticker, or None if it isn't an NSE-listed stock."""
    t = ticker.strip().upper()
    return t[:-3] if t.endswith(".NS") and len(t) > 3 else None


def report_year(entry: dict):
    """Financial-year-end year of an annual-report entry, parsed defensively
    (NSE file names look like AR_ULTRACEMCO_2010_2011_08082011052526.zip)."""
    for key in ("toYr", "to_yr", "toYear"):
        if str(entry.get(key, "")).isdigit():
            return int(entry[key])
    name = os.path.basename(str(entry.get("fileName", "")))
    years = [int(y) for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", name)]
    return max(years) if years else None


def select_entries(listing: dict, limit: int) -> list:
    """Newest `limit` reports, one per year -> [(year, url)]."""
    seen, picked = set(), []
    entries = [e for e in (listing or {}).get("data", []) if e.get("fileName")]
    entries.sort(key=lambda e: report_year(e) or 0, reverse=True)
    for e in entries:
        year = report_year(e)
        if year is not None and year in seen:
            continue
        seen.add(year)
        picked.append((year, e["fileName"]))
        if len(picked) >= limit:
            break
    return picked


def _is_pdf(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(5) == b"%PDF-"
    except OSError:
        return False


def _default_client():
    try:
        from nse import NSE
    except ImportError:
        raise FetchError("The 'nse' package isn't installed (pip install nse).")
    NSE_CACHE.mkdir(exist_ok=True)
    return NSE(download_folder=NSE_CACHE)


def fetch_documents(ticker: str, max_reports: int = None, client_factory=None) -> dict:
    """Download the latest annual reports for `ticker`. Returns
    {"downloaded": [...], "existing": [...], "failed": [...]}; raises FetchError
    when nothing usable could be obtained."""
    symbol = to_nse_symbol(ticker)
    if symbol is None:
        raise FetchError("Only NSE-listed stocks (tickers ending in .NS) are supported.")
    limit = max_reports or MAX_REPORTS
    folder = rag.DATA_DIR / company_folder(ticker)
    result = {"downloaded": [], "existing": [], "failed": []}

    try:
        with (client_factory or _default_client)() as nse:
            entries = select_entries(nse.annual_reports(symbol=symbol), limit)
            if not entries:
                raise FetchError(f"NSE lists no annual reports for {symbol} (recently listed?).")

            work = Path(tempfile.mkdtemp(prefix="ar_"))
            try:
                for i, (year, url) in enumerate(entries):
                    filename = f"annual_report_{year}.pdf" if year else f"annual_report_unknown{i}.pdf"
                    dest = folder / filename
                    if dest.exists():
                        result["existing"].append(filename)
                        continue
                    try:
                        got = Path(nse.download_document(url, folder=work))
                        if not _is_pdf(got):
                            raise ValueError(f"download wasn't a PDF ({got.suffix or 'unknown type'})")
                        folder.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(got), dest)
                        result["downloaded"].append(filename)
                    except Exception as e:
                        result["failed"].append(f"{year}: {e}")
            finally:
                shutil.rmtree(work, ignore_errors=True)
    except FetchError:
        raise
    except Exception as e:  # network down, NSE blocked us, endpoint changed...
        raise FetchError(f"Couldn't reach NSE ({type(e).__name__}). Try again later, or add PDFs manually.")

    if not result["downloaded"] and not result["existing"]:
        raise FetchError("All annual-report downloads failed: " + "; ".join(result["failed"][:2]))
    return result