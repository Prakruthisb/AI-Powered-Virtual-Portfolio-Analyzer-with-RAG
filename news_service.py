"""
news_service.py — fetch news per stock, score sentiment, store in DB.

Stored shape (matches the Phase 6 spec):
  company/symbol, title, date, source, url, sentiment
"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import requests
import yfinance as yf

import repository
import sentiment
from stock_universe import NSE_STOCKS


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


MIN_YAHOO_ITEMS = 5   # below this, Google News is added as a second source
_NAMES = {sym: name for sym, name in NSE_STOCKS}


def company_name(symbol: str) -> str:
    """'TCS.NS' -> 'Tata Consultancy Services' (searching the company name beats the bare ticker)."""
    return _NAMES.get(symbol.upper(), symbol.upper().replace(".NS", "").replace(".BO", ""))


def _fetch_google_news(symbol: str, limit: int = 10) -> list:
    """Google News RSS search for '<company> stock' (last 30 days) — the spec's
    'TCS latest news' idea. Free, no API key. Returns normalized items."""
    query = quote_plus(f"{company_name(symbol)} stock when:30d")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    resp.raise_for_status()

    items = []
    for node in ET.fromstring(resp.content).iter("item"):
        title, link = (node.findtext("title") or "").strip(), (node.findtext("link") or "").strip()
        if not title or not link:
            continue
        source = (node.findtext("source") or "").strip()
        if source and title.endswith(f" - {source}"):       # Google appends " - Publisher" to titles
            title = title[: -len(source) - 3].rstrip()
        try:
            published = parsedate_to_datetime(node.findtext("pubDate")).astimezone(timezone.utc).replace(tzinfo=None)
        except (TypeError, ValueError):
            published = None
        items.append({"symbol": symbol, "title": title[:500], "source": source[:120],
                      "url": link[:1000], "published_at": published})
        if len(items) >= limit:
            break
    return items


def refresh_news(symbols: list) -> dict:
    """Per symbol: Yahoo first; if it gives fewer than MIN_YAHOO_ITEMS, add Google News.
    Skip URLs already stored, score only the new ones, save.
    Returns {"new": int, "failed": [symbols], "details": {symbol: {...}}} — `details`
    says exactly where headlines came from (or why there were none)."""
    new_total, failed, details = 0, [], {}
    for symbol in symbols:
        info = {"yahoo": 0, "google": 0, "new": 0, "errors": []}
        details[symbol] = info
        found = []

        try:
            found += [n for n in (normalize_item(r, symbol) for r in _fetch_raw(symbol)) if n]
            info["yahoo"] = len(found)
        except Exception as e:
            info["errors"].append(f"Yahoo: {type(e).__name__}")

        if len(found) < MIN_YAHOO_ITEMS:
            try:
                google = _fetch_google_news(symbol)
                info["google"] = len(google)
                found += google
            except Exception as e:
                info["errors"].append(f"Google News: {type(e).__name__}")

        if not found and info["errors"]:
            failed.append(symbol)          # nothing came back AND something broke
            continue

        seen = repository.get_existing_news_urls(symbol)
        fresh = []
        for item in found:
            if item["url"] not in seen:
                seen.add(item["url"])
                fresh.append(item)
        if not fresh:
            continue

        for item, result in zip(fresh, sentiment.analyze_many([i["title"] for i in fresh])):
            item.update(sentiment=result["label"], score=result["score"], engine=result["engine"])
        repository.save_news_items(fresh)
        info["new"] = len(fresh)
        new_total += len(fresh)
    return {"new": new_total, "failed": failed, "details": details}


def summarize(items: list) -> dict:
    counts = {"Positive": 0, "Neutral": 0, "Negative": 0}
    for i in items:
        counts[i["sentiment"]] = counts.get(i["sentiment"], 0) + 1
    avg = round(sum(i["score"] for i in items) / len(items), 2) if items else 0.0
    return {"counts": counts, "avg_score": avg, "total": len(items)}