"""SoSoValue news client.

Primary news source: a keyword-targeted crypto stream, denser and more
on-topic than the general LTP wire. Exposes the same get_recent_headlines()
interface as feeds.news so the two are interchangeable in main.py.

Call via asyncio.to_thread from the async loops.
"""

import html
import logging
import os
import re
import time

import requests

log = logging.getLogger("feeds.soso")

BASE_URL = "https://openapi.sosovalue.com/openapi/v1"
TIMEOUT = 15


def _get(path: str, params: dict) -> list[dict]:
    """Authenticated GET; returns the data.list array. Raises on error."""
    headers = {"x-soso-api-key": os.environ["SOSO_API_KEY"]}
    response = requests.get(BASE_URL + path, params=params,
                            headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    body = response.json()
    if body.get("code") != 0:
        raise RuntimeError(f"sosovalue error {body.get('code')}: "
                           f"{body.get('message') or body.get('msg')}")
    return (body.get("data") or {}).get("list", [])


def clean_text(raw: str) -> str:
    """Strip HTML tags/entities and collapse whitespace."""
    if not raw:
        return ""
    no_tags = re.sub(r"<[^>]+>", " ", raw)
    return " ".join(html.unescape(no_tags).split())


def _symbols_of(item: dict) -> list[str]:
    out = []
    for cur in (item.get("matched_currencies") or []):
        sym = cur.get("symbol") if isinstance(cur, dict) else cur
        if sym:
            out.append(str(sym).upper())
    return out


def _format(item: dict, now_ms: int) -> str | None:
    text = clean_text(item.get("title") or "") or clean_text(item.get("content") or "")[:160]
    if not text:
        return None
    published = item.get("release_time") or now_ms
    try:
        age_min = max(0, int((now_ms - int(published)) / 60_000))
    except (TypeError, ValueError):
        age_min = 0
    syms = _symbols_of(item)
    tag = f" [{','.join(syms[:3])}]" if syms else ""
    return f"{age_min}m ago{tag}: {text[:180]}"


def get_recent_headlines(limit: int = 6, page_size: int = 20) -> list[str]:
    """BTC-focused headlines plus market-wide hot topics, newest first, deduped.

    Never raises: on any failure returns [] so the caller degrades gracefully.
    """
    now_ms = int(time.time() * 1000)
    try:
        btc = _get("/news/search", {"keyword": "bitcoin", "page": 1, "pageSize": page_size})
    except Exception:
        log.warning("sosovalue search failed", exc_info=True)
        btc = []
    try:
        hot = _get("/news/hot", {"page": 1, "pageSize": page_size})
    except Exception:
        log.warning("sosovalue hot failed", exc_info=True)
        hot = []

    if not btc and not hot:
        return []

    lines, seen = [], set()
    for item in list(btc) + list(hot):     # BTC-specific first, then hot topics
        line = _format(item, now_ms)
        if not line:
            continue
        key = line.split(": ", 1)[-1][:60]  # dedupe on headline text, not timestamp
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
        if len(lines) >= limit:
            break
    return lines
