"""
news_service.py — fetch news per stock, score sentiment, store in DB.

Stored shape (matches the Phase 6 spec):
  company/symbol, title, date, source, url, sentiment
"""

from datetime import datetime, timezone
import yfinance as yf

import repository
import sentiment


def _parse_date(value):
    """yfinance returns either an ISO string (new schema) or epoch seconds (old)."""
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)
        if isinstance(value, str) and value:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass
    return None


def normalize_item(raw: dict, symbol: str):
    """Handle both yfinance news schemas. Returns None if there's no title/url."""
    content = raw.get("content", raw)
    title = content.get("title") or raw.get("title")
    url = ((content.get("canonicalUrl") or {}).get("url")
           or (content.get("clickThroughUrl") or {}).get("url")
           or raw.get("link"))
    if not title or not url:
        return None
    source = (content.get("provider") or {}).get("displayName") or raw.get("publisher") or ""
    published = _parse_date(content.get("pubDate") or raw.get("providerPublishTime"))
    return {
        "symbol": symbol, "title": title[:500], "source": source[:120],
        "url": url[:1000], "published_at": published,
    }


def _fetch_raw(symbol: str) -> list:
    return yf.Ticker(symbol).news or []


def refresh_news(symbols: list) -> dict:
    """Fetch -> skip already-stored URLs -> score only the new ones -> save.
    Returns {"new": int, "failed": [symbols]}."""
    new_total, failed = 0, []
    for symbol in symbols:
        try:
            raw = _fetch_raw(symbol)
        except Exception:
            failed.append(symbol)
            continue

        existing = repository.get_existing_news_urls(symbol)
        fresh, seen = [], set(existing)
        for r in raw:
            item = normalize_item(r, symbol)
            if item and item["url"] not in seen:
                seen.add(item["url"])
                fresh.append(item)
        if not fresh:
            continue

        for item, result in zip(fresh, sentiment.analyze_many([i["title"] for i in fresh])):
            item.update(sentiment=result["label"], score=result["score"], engine=result["engine"])
        repository.save_news_items(fresh)
        new_total += len(fresh)
    return {"new": new_total, "failed": failed}


def summarize(items: list) -> dict:
    counts = {"Positive": 0, "Neutral": 0, "Negative": 0}
    for i in items:
        counts[i["sentiment"]] = counts.get(i["sentiment"], 0) + 1
    avg = round(sum(i["score"] for i in items) / len(items), 2) if items else 0.0
    return {"counts": counts, "avg_score": avg, "total": len(items)}