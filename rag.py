"""
rag.py — Phase 7 RAG pipeline: extract -> chunk -> metadata -> embed -> FAISS -> retrieve.

Layout:
  data/<TICKER>/<document>.pdf        e.g. data/TCS/annual_report_2025.pdf
  vectorstore/manifest.json           which PDFs are ingested (+ embedding model used)
  vectorstore/<TICKER>/index.faiss    one FAISS index per company
  vectorstore/<TICKER>/chunks.json    chunk text + metadata, aligned with index row ids

One index per company means "only search the companies in this portfolio"
is just "load those companies' indexes" — no filtering over a giant index.
Embeddings are L2-normalised and the index is inner-product, so score = cosine similarity.
"""

import json
import os
import re
import shutil
from functools import lru_cache
from pathlib import Path

import faiss
import numpy as np
import pymupdf
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

BASE = Path(__file__).parent
DATA_DIR = BASE / "data"
STORE_DIR = BASE / "vectorstore"
MANIFEST = STORE_DIR / "manifest.json"

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
MIN_CHUNK_CHARS = 50  # drops page numbers / stray headers
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

_splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)


# ---------------------------------------------------------------
# Step 6: embeddings (sentence-transformers, loaded lazily on first use)
# ---------------------------------------------------------------
_embed_fn = None


def set_embedder(fn):
    """Override the embedding function (used for tests / swapping models)."""
    global _embed_fn
    _embed_fn = fn


def embed(texts: list) -> np.ndarray:
    global _embed_fn
    if _embed_fn is None:
        from sentence_transformers import SentenceTransformer  # heavy import, kept lazy
        model = SentenceTransformer(EMBEDDING_MODEL)
        _embed_fn = lambda t: model.encode(
            t, normalize_embeddings=True, batch_size=32, show_progress_bar=False
        )
    return np.ascontiguousarray(np.asarray(_embed_fn(texts), dtype="float32"))


# ---------------------------------------------------------------
# Step 3: extract text (PyMuPDF), page by page
# ---------------------------------------------------------------
def extract_pages(pdf_path: Path) -> list:
    pages = []
    with pymupdf.open(pdf_path) as doc:
        for i, page in enumerate(doc, start=1):
            pages.append((i, page.get_text()))
    return pages


# ---------------------------------------------------------------
# Step 5: metadata — company, document, year, section, page
# ---------------------------------------------------------------
SECTION_PATTERNS = {
    "Risk Factors": r"^(risk factors|risk management|key risks|principal risks)\b",
    "Management Discussion & Analysis": r"^(management'?s? discussion (and|&) analysis|md&a)",
    "Business Overview": r"^(business overview|company overview|about the company|our business)",
    "Corporate Governance": r"^(report on )?corporate governance",
    "Directors' Report": r"^(board'?s|directors'?) report",
    "Auditor's Report": r"^independent auditor'?s report",
    "Financial Statements": r"^(standalone |consolidated )?(financial statements|balance sheet|statement of profit)",
    "Outlook": r"^(outlook|guidance)\b",
    "Sustainability": r"^(sustainability|esg|business responsibility)",
}


def detect_sections(page_text: str) -> set:
    found = set()
    for line in page_text.splitlines():
        line = line.strip().lower()
        if 3 < len(line) < 80:
            for name, pattern in SECTION_PATTERNS.items():
                if re.match(pattern, line):
                    found.add(name)
    return found


def parse_filename(stem: str) -> tuple:
    """annual_report_2025 -> ("Annual Report", 2025); earnings_q2_fy26 -> ("Earnings", 2026)."""
    s = stem.lower()
    year = None
    if m := re.search(r"(20\d{2})", s):
        year = int(m.group(1))
    elif m := re.search(r"fy[-_]?(\d{2})\b", s):
        year = 2000 + int(m.group(1))

    if s.startswith("annual"):
        doc_type = "Annual Report"
    elif s.startswith(("earnings", "transcript", "concall")):
        doc_type = "Earnings"
    elif s.startswith(("filing", "10k", "sebi", "bse", "nse")):
        doc_type = "Filing"
    else:
        doc_type = stem.replace("_", " ").title()
    return doc_type, year


# ---------------------------------------------------------------
# Step 4: chunk (1000 chars, 200 overlap) — per page, so every chunk
# keeps an accurate page number and section.
# ---------------------------------------------------------------
def build_chunks(pdf_path: Path) -> list:
    company = pdf_path.parent.name.upper()
    doc_type, year = parse_filename(pdf_path.stem)

    chunks, section = [], "General"
    for page_no, text in extract_pages(pdf_path):
        found = detect_sections(text)
        # A page naming 3+ sections is a table of contents, not a real heading.
        if len(found) == 1:
            section = next(iter(found))
        elif len(found) == 2:
            section = sorted(found)[0]

        for piece in _splitter.split_text(text):
            piece = piece.strip()
            if len(piece) < MIN_CHUNK_CHARS:
                continue
            chunks.append({
                "text": piece,
                "metadata": {
                    "company": company, "document": doc_type, "year": year,
                    "section": section, "page": page_no, "source": pdf_path.name,
                },
            })
    return chunks


# ---------------------------------------------------------------
# Step 7: store in FAISS (one index per company) + manifest
# ---------------------------------------------------------------
def _load_manifest() -> dict:
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"files": {}}


def _save_manifest(m: dict):
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, indent=2))


def _add_to_store(company: str, chunks: list):
    folder = STORE_DIR / company
    folder.mkdir(parents=True, exist_ok=True)
    vectors = embed([c["text"] for c in chunks])

    index_path, chunks_path = folder / "index.faiss", folder / "chunks.json"
    if index_path.exists():
        index = faiss.read_index(str(index_path))
        existing = json.loads(chunks_path.read_text())
    else:
        index, existing = faiss.IndexFlatIP(vectors.shape[1]), []

    index.add(vectors)
    # Write to temp files, then swap in: a search running at the same time
    # (this runs in a background thread) never sees a half-written file.
    tmp_index, tmp_chunks = folder / "index.faiss.tmp", folder / "chunks.json.tmp"
    faiss.write_index(index, str(tmp_index))
    tmp_chunks.write_text(json.dumps(existing + chunks))
    os.replace(tmp_chunks, chunks_path)
    os.replace(tmp_index, index_path)


def ingest(rebuild: bool = False, companies: list = None) -> dict:
    """Ingest data/<TICKER>/*.pdf not already in the manifest.
    `companies` limits it to those tickers (used when a user adds a stock)."""
    only = {c.upper() for c in companies} if companies else None
    if rebuild and STORE_DIR.exists():
        shutil.rmtree(STORE_DIR)

    manifest = _load_manifest()
    prev_model = manifest.get("embedding_model")
    if prev_model and prev_model != EMBEDDING_MODEL:
        raise RuntimeError(
            f"Index was built with '{prev_model}' but EMBEDDING_MODEL is '{EMBEDDING_MODEL}'. "
            "Run with --rebuild (vectors from different models can't be mixed)."
        )

    summary = {"added": [], "skipped": [], "changed": [], "no_text": [], "chunks": 0}
    for pdf in sorted(DATA_DIR.glob("*/*.pdf")):
        if only and pdf.parent.name.upper() not in only:
            continue
        key = f"{pdf.parent.name.upper()}/{pdf.name}"
        mtime = pdf.stat().st_mtime
        known = manifest["files"].get(key)
        if known:
            (summary["changed"] if known["mtime"] != mtime else summary["skipped"]).append(key)
            continue

        chunks = build_chunks(pdf)
        if not chunks:
            summary["no_text"].append(key)  # usually a scanned PDF -> needs OCR
            continue

        _add_to_store(pdf.parent.name.upper(), chunks)
        manifest["files"][key] = {"company": pdf.parent.name.upper(), "chunks": len(chunks), "mtime": mtime}
        manifest["embedding_model"] = EMBEDDING_MODEL
        _save_manifest(manifest)  # saved per file so a crash doesn't lose finished work
        summary["added"].append(key)
        summary["chunks"] += len(chunks)
    return summary


def index_status() -> dict:
    """{company: total_chunks} for everything currently indexed."""
    status = {}
    for info in _load_manifest()["files"].values():
        status[info["company"]] = status.get(info["company"], 0) + info["chunks"]
    return status


# ---------------------------------------------------------------
# Step 8: retrieval — only the portfolio's companies, balanced per company
# ---------------------------------------------------------------
@lru_cache(maxsize=32)
def _load_store(company: str, stamp: float):
    """`stamp` (index file mtime) busts the cache when new documents are ingested."""
    folder = STORE_DIR / company
    index = faiss.read_index(str(folder / "index.faiss"))
    chunks = json.loads((folder / "chunks.json").read_text())
    return index, chunks


def retrieve(question: str, companies: list, k_per_company: int = 3) -> list:
    """Top chunks for `question` from each listed company, merged best-first.
    Per-company retrieval guarantees every holding is represented, so a big
    company with lots of text can't crowd out a smaller one."""
    question = (question or "").strip()
    if not question:
        return []
    query = embed([question])

    results = []
    for company in dict.fromkeys(c.upper() for c in companies):
        index_path = STORE_DIR / company / "index.faiss"
        if not index_path.exists():
            continue
        index, chunks = _load_store(company, index_path.stat().st_mtime)
        scores, ids = index.search(query, min(k_per_company, index.ntotal))
        for score, i in zip(scores[0], ids[0]):
            if 0 <= i < len(chunks):
                results.append({
                    "text": chunks[i]["text"],
                    "metadata": chunks[i]["metadata"],
                    "similarity": round(float(score), 3),
                })
    return sorted(results, key=lambda r: r["similarity"], reverse=True)


def indexed_documents(company: str) -> list:
    """File names already indexed for a company (from the manifest)."""
    company = company.upper()
    return [k.split("/", 1)[1] for k, v in _load_manifest()["files"].items() if v["company"] == company]