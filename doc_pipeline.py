"""
doc_pipeline.py — "user adds a stock -> its documents get fetched and indexed".

ensure_documents(ticker) returns immediately and does the work in a background
thread, so the UI never freezes while reports download and get embedded
(a few minutes per company). Progress is stored in the document_status table
(shared per company), which the Documents page reads.

No Streamlit imports here on purpose: background threads must not touch st.*.
"""

import logging
import threading

import rag
import repository
import doc_fetcher

log = logging.getLogger(__name__)

# One download+index job at a time: NSE rate-limits, and the embedding model is RAM-heavy.
_lock = threading.Lock()


def _worker(ticker: str, company: str):
    with _lock:
        try:
            repository.set_doc_status(company, "fetching", "Downloading annual reports from NSE...")
            doc_fetcher.fetch_documents(ticker)

            repository.set_doc_status(company, "fetching", "Indexing documents (a few minutes)...")
            rag.ingest(companies=[company])

            n = len(rag.indexed_documents(company))
            if n == 0:
                raise doc_fetcher.FetchError(
                    "Downloaded, but no text could be extracted (scanned PDFs need OCR).")
            repository.set_doc_status(company, "ready", f"{n} document(s) indexed", reports=n)
        except doc_fetcher.FetchError as e:
            repository.set_doc_status(company, "failed", str(e))
        except Exception as e:
            log.exception("Document pipeline failed for %s", ticker)
            repository.set_doc_status(company, "failed", f"Unexpected error: {type(e).__name__}: {e}")


def ensure_documents(ticker: str):
    """Start fetching+indexing `ticker`'s documents unless that's already done or in
    progress. Safe to call repeatedly. Returns the Thread (or None if nothing to do)."""
    company = doc_fetcher.company_folder(ticker)

    if doc_fetcher.to_nse_symbol(ticker) is None and company not in rag.index_status():
        repository.set_doc_status(company, "unsupported",
                                  "Only NSE-listed stocks (.NS) get automatic documents.")
        return None

    # Documents already indexed (added manually / via ingest.py): just record that.
    docs = rag.indexed_documents(company)
    if docs:
        if repository.get_doc_statuses([company]).get(company, {}).get("status") != "ready":
            repository.set_doc_status(company, "ready", f"{len(docs)} document(s) indexed", len(docs))
        return None

    if not repository.claim_doc_fetch(company):   # already fetching / ready / unsupported
        return None

    t = threading.Thread(target=_worker, args=(ticker, company), daemon=True)
    t.start()
    return t