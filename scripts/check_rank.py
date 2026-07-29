"""Print our Track A self-ranking: rank, composite score, and the percentile
breakdown that shows exactly where the score comes from.

Uses the organizers' Self-Ranking API (announced 2026-07-29) with the same
V2 signature the feeds client already implements. Ranking data refreshes
daily at 00:00 UTC, so intraday runs show the previous midnight's snapshot.

Read-only. Run from src/:  python3 ../scripts/check_rank.py
"""

import sys

sys.path.insert(0, ".")
from feeds.news import feeds_get  # noqa: E402

WEIGHTS = {"sharpe": 0.40, "pnl": 0.25, "roi": 0.20, "mdd": 0.15}


def main():
    data = feeds_get("/api/v1/tracka/ranking/self", {"phase": "PHASE_I"})
    parts = {
        "sharpe": float(data["ssharpe"]) * WEIGHTS["sharpe"],
        "pnl": float(data["spnl"]) * WEIGHTS["pnl"],
        "roi": float(data["sroi"]) * WEIGHTS["roi"],
        "mdd": float(data["mddTierScore"]) * WEIGHTS["mdd"],
    }
    print(f"rank {data['rankNo']}   composite {float(data['compositeScore']):.2f}   "
          f"equity {float(data['equity']):.2f}   pnl {float(data['pnlUsdt']):+.2f}   "
          f"eliminated: {data['isEliminated']}")
    print("score anatomy (percentile x weight = contribution):")
    print(f"  sharpe  {float(data['ssharpe']):6.2f} x 0.40 = {parts['sharpe']:6.2f}")
    print(f"  pnl     {float(data['spnl']):6.2f} x 0.25 = {parts['pnl']:6.2f}")
    print(f"  roi     {float(data['sroi']):6.2f} x 0.20 = {parts['roi']:6.2f}")
    print(f"  mdd     {float(data['mddTierScore']):6.2f} x 0.15 = {parts['mdd']:6.2f}")
    print(f"  total          = {sum(parts.values()):.2f}")
    tok = data.get("aiTokens") or {}
    cost = data.get("aiCost") or {}
    print(f"ai: {tok.get('totalTokens', '?')} tokens yesterday, "
          f"cumulative cost {float(cost.get('cumulativeAiCostUsdt', 0)):.2f} USDT")


if __name__ == "__main__":
    main()
