"""
sentiment.py — headline sentiment (Positive / Neutral / Negative).

Two engines, picked via SENTIMENT_ENGINE in .env:
  rule    (default) keyword lexicon, no downloads, instant
  finbert ProsusAI/finbert via HuggingFace, needs `pip install transformers torch`
          (~450MB model download on first use). Falls back to rule if unavailable.

Every result: {"label": "Positive"|"Neutral"|"Negative", "score": -1..1, "engine": str}
score > 0 leans positive, < 0 leans negative.
"""

import os
import re
from functools import lru_cache

POSITIVE = {
    "surge", "surges", "surged", "soar", "soars", "soared", "jump", "jumps", "jumped",
    "gain", "gains", "gained", "rally", "rallies", "rallied", "rise", "rises", "rose",
    "profit", "profits", "growth", "grows", "grew", "beat", "beats", "strong", "stronger",
    "record", "high", "upgrade", "upgraded", "outperform", "bullish", "boost", "boosts",
    "win", "wins", "won", "order", "orders", "expansion", "expands", "dividend", "buyback",
    "positive", "optimistic", "recovery", "recovers", "robust", "upbeat", "approval", "approved",
}
NEGATIVE = {
    "fall", "falls", "fell", "drop", "drops", "dropped", "plunge", "plunges", "plunged",
    "slump", "slumps", "crash", "crashes", "decline", "declines", "declined", "loss", "losses",
    "miss", "misses", "missed", "weak", "weaker", "downgrade", "downgraded", "underperform",
    "bearish", "cut", "cuts", "layoff", "layoffs", "probe", "fraud", "lawsuit", "penalty",
    "fine", "fined", "default", "risk", "concern", "concerns", "warning", "warns", "slowdown",
    "negative", "pessimistic", "sell-off", "selloff", "ban", "banned", "investigation",
}
NEGATORS = {"not", "no", "never", "fails", "fail", "failed", "without", "unlikely"}


def _label(score: float) -> str:
    if score > 0.1:
        return "Positive"
    if score < -0.1:
        return "Negative"
    return "Neutral"


def rule_based(text: str) -> dict:
    tokens = re.findall(r"[a-z'-]+", (text or "").lower())
    pos = neg = 0
    for i, tok in enumerate(tokens):
        negated = i > 0 and tokens[i - 1] in NEGATORS
        if tok in POSITIVE:
            neg, pos = (neg + 1, pos) if negated else (neg, pos + 1)
        elif tok in NEGATIVE:
            pos, neg = (pos + 1, neg) if negated else (pos, neg + 1)
    total = pos + neg
    score = (pos - neg) / total if total else 0.0
    return {"label": _label(score), "score": round(score, 3), "engine": "rule"}


@lru_cache(maxsize=1)
def _load_finbert():
    from transformers import pipeline  # imported lazily: heavy, optional
    return pipeline("text-classification", model="ProsusAI/finbert", top_k=None)


def _finbert_many(texts: list) -> list:
    clf = _load_finbert()
    out = []
    for scores in clf(texts, truncation=True):
        by_label = {s["label"].lower(): s["score"] for s in scores}
        score = by_label.get("positive", 0) - by_label.get("negative", 0)
        top = max(by_label, key=by_label.get).capitalize()
        out.append({"label": top, "score": round(score, 3), "engine": "finbert"})
    return out


def get_engine() -> str:
    return os.getenv("SENTIMENT_ENGINE", "rule").strip().lower()


def analyze_many(texts: list) -> list:
    if not texts:
        return []
    if get_engine() == "finbert":
        try:
            return _finbert_many(texts)
        except Exception:
            pass  # transformers/torch missing or model download failed -> fall back
    return [rule_based(t) for t in texts]