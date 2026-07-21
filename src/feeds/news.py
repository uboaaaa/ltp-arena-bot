"""LTP News Feed client.

The RapidX CLI does not expose the feeds endpoints, so we call the REST API
directly with the V2 header signature (same credentials as trading).

The feed is a general financial wire - most items are equities or macro and
irrelevant to a BTC bot - so everything is filtered for crypto relevance
before it reaches the prompt.

Call via asyncio.to_thread from the async loops.
"""

import hashlib
import hmac
import logging
import os
import re
import time

import requests

log = logging.getLogger("feeds.news")

BASE_URL = "https://api.ltp-contest.com"
TIMEOUT = 15
MAX_PAGE_SIZE = 30          # server rejects larger pages with code 30012

CRYPTO_SYMBOLS = {
    "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "LINK", "DOT",
    "LTC", "BCH", "TRX", "TON", "SUI", "APT", "ARB", "OP", "HYPE", "ENA",
    "NEAR", "ATOM", "XMR", "XLM", "HBAR", "ICP", "UNI", "AAVE", "PEPE",
    "SHIB", "WLD", "ONDO", "TAO", "KAS", "JUP", "RENDER", "ALGO", "ETC",
    "QNT", "SKY", "MORPHO", "DEXE", "ZEC", "POL", "PAXG", "XAUT", "USDC",
}

CRYPTO_KEYWORDS = (
    "crypto", "bitcoin", "ethereum", "blockchain", "stablecoin", "defi",
    "altcoin", "digital asset", "web3", "binance", "coinbase", "etf flows",
)


def _sign_v2(params: dict, nonce: int) -> str:
    """Alpha-sorted 'k=v&k=v' + '&' + nonce, HMAC-SHA256 with the secret key."""
    secret = os.environ["LTP_SECRET_KEY"]
    payload = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hmac.new(secret.encode(), f"{payload}&{nonce}".encode(),
                    hashlib.sha256).hexdigest()


def feeds_get(path: str, params: dict) -> dict:
    """Authenticated GET against the feeds API. Raises on transport or API error."""
    nonce = int(time.time())
    headers = {
        "X-MBX-APIKEY": os.environ["LTP_ACCESS_KEY"],
        "nonce": str(nonce),
        "signature": _sign_v2(params, nonce),
    }
    response = requests.get(BASE_URL + path, params=params,
                            headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    body = response.json()
    # feeds use code 200 for success, unlike the trading API's 200000
    if body.get("code") != 200:
        raise RuntimeError(f"feeds error {body.get('code')}: {body.get('message')}")
    return body.get("data", {})


def _symbols_of(item: dict) -> set[str]:
    """Currency tags, upper-cased (the API returns mixed case)."""
    return {(c.get("symbol") or "").upper()
            for c in (item.get("currencies") or []) if c.get("symbol")}


def _text_of(item: dict) -> str:
    """Headline, falling back to a content snippet when title is empty."""
    title = (item.get("title") or "").strip()
    if title:
        return " ".join(title.split())
    stripped = re.sub(r"<[^>]+>", " ", item.get("content") or "")
    return " ".join(stripped.split())[:160]


def is_crypto_relevant(item: dict) -> bool:
    """Keep crypto-tagged or crypto-worded items; drop equities and macro noise."""
    if _symbols_of(item) & CRYPTO_SYMBOLS:
        return True
    text = (_text_of(item) + " " + (item.get("content") or "")[:300]).lower()
    return any(keyword in text for keyword in CRYPTO_KEYWORDS)


def get_recent_news(hours: int = 12, pages: int = 2) -> list[dict]:
    """Raw news items from the last N hours, newest first."""
    now_ms = int(time.time() * 1000)
    items: list[dict] = []
    for page in range(1, pages + 1):
        data = feeds_get("/api/v1/feeds/queryNews", {
            "startTime": str(now_ms - hours * 3_600_000),
            "endTime": str(now_ms),
            "page": str(page),
            "pageSize": str(MAX_PAGE_SIZE),
        })
        batch = data.get("list", [])
        items.extend(batch)
        if len(batch) < MAX_PAGE_SIZE:
            break
    return items


def headline_lines(items: list[dict], limit: int = 6,
                   prefer_symbol: str = "BTC") -> list[str]:
    """Compact one-liners for the prompt: crypto only, BTC-tagged first."""
    now_ms = int(time.time() * 1000)
    preferred, other = [], []

    for item in items:
        if not is_crypto_relevant(item):
            continue
        text = _text_of(item)
        if not text:
            continue
        symbols = _symbols_of(item)
        age_min = max(0, int((now_ms - (item.get("publishTime") or now_ms)) / 60_000))
        tag = f" [{','.join(sorted(symbols & CRYPTO_SYMBOLS)[:3])}]" if symbols & CRYPTO_SYMBOLS else ""
        line = f"{age_min}m ago{tag}: {text[:180]}"
        (preferred if prefer_symbol in symbols else other).append(line)

    return (preferred + other)[:limit]


def get_recent_headlines(hours: int = 12, limit: int = 6) -> list[str]:
    """Fetch and format in one call. Returns [] rather than raising on no data."""
    return headline_lines(get_recent_news(hours=hours), limit=limit)
