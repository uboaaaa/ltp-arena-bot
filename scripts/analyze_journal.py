"""Read-only journal analysis: reconstructs round-trip trades from decisions.jsonl
and reports win rate and net PnL by trade category.

Usage (from repo root):  python3 scripts/analyze_journal.py [path-to-decisions.jsonl]

Reads one file and prints. Never touches the network or places orders.

Caveats baked in:
- pnl_pct in bracket_exit records is measured at trigger time from markPrice,
  not the actual close fill, so treat results as approximate to a few bps.
- Fees are modeled as a flat taker round trip (FEE_ROUND_TRIP_PCT), not read
  from fills.
- The catalyst column is a keyword GUESS from the model's reasoning text; with
  small samples, eyeball each trade's reasoning yourself before trusting it.
"""

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

FEE_ROUND_TRIP_PCT = 0.08   # taker in + taker out, percent of notional
CHOP_THRESHOLD_PCT = 0.8    # same regime threshold the prompt uses

CATALYST_HINTS = ("acquisition", "acquire", "etf", "whale", "inflow", "liquidation",
                  "unlock", "halving", "ruling", "approval", "consortium", "flip")
NO_CATALYST_HINTS = ("no catalyst", "no near-term catalyst", "no immediate catalyst",
                     "no directional catalyst", "not a near-term catalyst",
                     "without a catalyst", "no actionable")


def parse_ts(ts):
    return datetime.fromisoformat(ts)


def load_events(path):
    """One pass over the journal. Returns (opens, exits_by_decision_id)."""
    opens = []
    exits = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("event") in ("bracket_exit", "model_exit"):
                # early records misspelled the key ("deicison_id"); the journal is
                # append-only history, so the reader tolerates both and falls back
                # to the id inside the saved plan
                did = (rec.get("decision_id") or rec.get("deicison_id")
                       or (rec.get("plan") or {}).get("decision_id"))
                exits[did] = {
                    "ts": rec.get("ts"),
                    "trigger": rec.get("trigger"),
                    "pnl_pct": float(rec.get("pnl_pct", "0")),
                }
                continue
            ex = rec.get("execution") or {}
            orders = ex.get("orders") or []
            entry_orders = [o for o in orders if str(o.get("type", "")).startswith("open_")]
            if not entry_orders:
                continue
            result = entry_orders[0].get("result") or {}
            dec = rec.get("decision") or {}
            prompt = rec.get("prompt", "")
            m = re.search(r"(\d+)h change ([+-]?[\d.]+)%", prompt)
            chg12h = float(m.group(2)) if m else None
            m = re.search(r"- range: ([\d.]+) - ([\d.]+)", prompt)
            rng = (float(m.group(1)), float(m.group(2))) if m else None
            entry_px = float(result.get("executedAvgPrice") or 0) or None
            opens.append({
                "decision_id": rec.get("decision_id"),
                "ts": rec.get("ts"),
                "action": dec.get("action"),
                "confidence": dec.get("confidence"),
                "entry": entry_px,
                "chg12h": chg12h,
                "range": rng,
                "reasoning": dec.get("reasoning") or "",
                "catalyst_model": dec.get("catalyst"),
                "edge_zone" : bool(ex.get("edge_zone")),
            })
    return opens, exits


def range_position_pct(trade):
    """Where in the day's range we entered: 0 = at the low, 100 = at the high."""
    if not trade["range"] or not trade["entry"]:
        return None
    lo, hi = trade["range"]
    if hi <= lo:
        return None
    return (trade["entry"] - lo) / (hi - lo) * 100


def classify(trade):
    chg = trade["chg12h"]
    if trade.get("edge_zone"):
        return "edge-zone-fade"
    if chg is None or trade["action"] not in ("LONG", "SHORT"):
        return "unclassified"
    if abs(chg) < CHOP_THRESHOLD_PCT:
        return "chop-entry"
    trend_side = "LONG" if chg > 0 else "SHORT"
    return "trend-follow" if trade["action"] == trend_side else "counter-trend-fade"


def catalyst_guess(reasoning):
    text = reasoning.lower()
    if any(kw in text for kw in NO_CATALYST_HINTS):
        return False
    return any(kw in text for kw in CATALYST_HINTS)


def catalyst_label(trade):
    """Prefer the model's own tag (records after 2026-07-23); keyword-guess older ones."""
    tag = trade.get("catalyst_model")
    if tag is True:
        return "yes"
    if tag is False:
        return "no"
    return "~yes(guess)" if catalyst_guess(trade["reasoning"]) else "~no(guess)"


def match_trades(opens, exits):
    """Join opens to exits on decision_id. Returns (trades, unmatched_opens, orphan_exits)."""
    remaining = dict(exits)
    trades = []
    unmatched = []
    for o in opens:
        x = remaining.pop(o["decision_id"], None)
        if x is None:
            unmatched.append(o)
            continue
        held_min = None
        try:
            held_min = (parse_ts(x["ts"]) - parse_ts(o["ts"])).total_seconds() / 60
        except (TypeError, ValueError):
            pass
        trades.append({
            **o,
            "trigger": x["trigger"],
            "pnl_gross_pct": x["pnl_pct"],
            "pnl_net_pct": x["pnl_pct"] - FEE_ROUND_TRIP_PCT,
            "held_min": held_min,
        })
    return trades, unmatched, remaining


def print_trades(trades):
    print(f"{'when':<17} {'side':<6} {'conf':<5} {'cat':<18} {'rng%':<5} "
          f"{'exit':<12} {'held':<6} {'net%':<7} catalyst?  reasoning")
    for t in trades:
        rp = range_position_pct(t)
        held = f"{t['held_min']:.0f}m" if t["held_min"] is not None else "?"
        print(f"{t['ts'][:16]:<17} {t['action']:<6} {t['confidence']:<5} "
              f"{classify(t):<18} {rp if rp is None else round(rp):<5} "
              f"{t['trigger']:<12} {held:<6} {t['pnl_net_pct']:+.3f}  "
              f"{catalyst_label(t):<11} "
              f"{t['reasoning'][:70]}")


def print_summary(trades, title, keyfn):
    buckets = defaultdict(list)
    for t in trades:
        buckets[keyfn(t)].append(t)
    print(f"\n=== {title} ===")
    print(f"{'category':<20} {'n':>3} {'wins':>5} {'winrate':>8} {'avg net%':>9} "
          f"{'total net%':>11} {'avg held':>9}  exit triggers")
    for cat, ts in sorted(buckets.items()):
        wins = [t for t in ts if t["pnl_net_pct"] > 0]
        helds = [t["held_min"] for t in ts if t["held_min"] is not None]
        avg_held = f"{sum(helds)/len(helds):.0f}m" if helds else "?"
        triggers = dict(Counter(t["trigger"] for t in ts))
        avg_net = sum(t["pnl_net_pct"] for t in ts) / len(ts)
        total_net = sum(t["pnl_net_pct"] for t in ts)
        print(f"{cat:<20} {len(ts):>3} {len(wins):>5} {len(wins)/len(ts):>7.0%} "
              f"{avg_net:>+9.3f} {total_net:>+11.3f} {avg_held:>9}  {triggers}")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "src/data/decisions.jsonl"
    opens, exits = load_events(path)
    trades, unmatched_opens, orphan_exits = match_trades(opens, exits)

    print(f"journal: {len(opens)} opens, {len(exits)} bracket exits, "
          f"{len(trades)} matched round trips\n")
    print_trades(trades)
    print_summary(trades, "by price context", classify)
    print_summary(trades, "by catalyst (model tag when available, ~guess for old records)",
                  lambda t: "catalyst-" + catalyst_label(t))

    if unmatched_opens:
        print("\n--- opens with no recorded exit (last one may still be held) ---")
        for o in unmatched_opens:
            print(f"  {o['ts'][:16]}  {o['action']}  conf {o['confidence']}  {o['decision_id']}")
    if orphan_exits:
        print("\n--- bracket exits whose open is missing from the journal ---")
        for did, x in orphan_exits.items():
            print(f"  {str(x['ts'])[:16]}  {x['trigger']}  {x['pnl_pct']:+.3f}%  {did}")


if __name__ == "__main__":
    main()
