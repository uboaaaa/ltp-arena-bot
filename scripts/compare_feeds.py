"""Probe the SoSoValue news API and compare its crypto coverage against LTP's feed.

Run from src/ with SOSO_API_KEY and the LTP keys in the environment.
"""

import json
import os
import sys
import time

import requests

SOSO_BASE = "https://openapi.sosovalue.com/openapi/v1"
KEY = os.environ.get("SOSO_API_KEY")
HEADERS = {"x-soso-api-key": KEY or "", "Content-Type": "application/json"}


def probe(path: str, params: dict | None = None, method: str = "GET") -> dict | None:
    url = SOSO_BASE + path
    try:
        if method == "GET":
            r = requests.get(url, headers=HEADERS, params=params or {}, timeout=20)
        else:
            r = requests.post(url, headers=HEADERS, json=params or {}, timeout=20)
        print(f"\n--- {method} {path} params={params} -> HTTP {r.status_code}")
        try:
            body = r.json()
        except ValueError:
            print("    non-JSON body:", r.text[:200])
            return None
        print("    top-level keys:", list(body.keys()))
        print("    code:", body.get("code"), "message:", body.get("message"))
        data = body.get("data")
        if isinstance(data, dict):
            print("    data keys:", list(data.keys()))
            items = data.get("list") or data.get("records") or data.get("items")
        elif isinstance(data, list):
            items = data
        else:
            items = None
        if items:
            print(f"    item count: {len(items)}")
            print("    first item keys:", list(items[0].keys())[:20])
            return {"items": items}
        print("    raw (trimmed):", json.dumps(body)[:400])
        return None
    except Exception as exc:
        print(f"    ERROR: {exc}")
        return None


def title_of(item: dict) -> str:
    for key in ("title", "headline", "name", "content", "text"):
        val = item.get(key)
        if val:
            return " ".join(str(val).split())[:150]
    return ""


def main() -> None:
    if not KEY:
        print("SOSO_API_KEY not set - add it to ~/.env and re-run")
        sys.exit(1)

    print("=" * 70)
    print("PROBING SOSOVALUE ENDPOINTS")
    print("=" * 70)

    results = {}
    results["news"] = probe("/news", {"page": 1, "pageSize": 20})
    results["news_alt"] = probe("/news", {"page": 1, "page_size": 20})
    results["hot"] = probe("/news/hot", {"page": 1, "pageSize": 20})
    results["pick"] = probe("/news/pick", {"page": 1, "pageSize": 20})
    results["search"] = probe("/news/search", {"keyword": "bitcoin", "page": 1, "pageSize": 20})
    results["search_q"] = probe("/news/search", {"q": "bitcoin", "page": 1, "pageSize": 20})

    print("\n" + "=" * 70)
    print("SAMPLE HEADLINES FROM WHATEVER WORKED")
    print("=" * 70)
    best = None
    for name, res in results.items():
        if res and res.get("items"):
            print(f"\n[{name}] {len(res['items'])} items:")
            for item in res["items"][:8]:
                text = title_of(item)
                if text:
                    print("   -", text)
            if best is None or len(res["items"]) > len(best[1]["items"]):
                best = (name, res)

    print("\n" + "=" * 70)
    print("LTP FEED, SAME WINDOW, FOR COMPARISON")
    print("=" * 70)
    try:
        from feeds.news import get_recent_news, headline_lines, is_crypto_relevant
        ltp_items = get_recent_news(hours=12)
        relevant = [i for i in ltp_items if is_crypto_relevant(i)]
        print(f"LTP: {len(ltp_items)} raw items, {len(relevant)} crypto-relevant")
        for line in headline_lines(ltp_items, limit=8):
            print("   -", line)
    except Exception as exc:
        print("LTP fetch failed:", exc)

    if best:
        print(f"\nBest SoSoValue endpoint by volume: /{best[0]} ({len(best[1]['items'])} items)")


if __name__ == "__main__":
    main()
