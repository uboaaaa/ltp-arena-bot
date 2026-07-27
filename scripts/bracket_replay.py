"""Bracket geometry replay study, 2026-07-28.

Takes the real post-Part-B entries from the journal and replays each one
against a grid of alternative take-profit / stop-loss multipliers, using
historical candles fetched from the exchange. Entries are reusable because
the model never sees bracket levels; only exits change.

Ambiguity handling: when one candle's range spans BOTH the TP and SL levels,
first-touch order is unknowable at that resolution. We therefore report two
bounds: pessimistic (stop fired first in every ambiguous candle) and
optimistic (target fired first). Trust only conclusions that hold under both.

Read-only with respect to the account: fetches market data, prints tables.
Run from src/:  python3 ../scripts/bracket_replay.py
"""

import json
import sys
from datetime import datetime, timezone
from decimal import Decimal

sys.path.insert(0, ".")
from broker.rapidx import get_klines  # noqa: E402

JOURNAL = "data/decisions.jsonl"
CUTOFF = "2026-07-23T00:00"
FEE = 0.08          # taker round trip, percent
MAX_AGE_MIN = 240   # 4 hours, same as the live bot
SYMBOL = "BINANCE_PERP_BTC_USDT"

TP_MULTS = [0.6, 0.8, 1.0, 1.2, 1.4]
SL_MULTS = [0.4, 0.5, 0.6, 0.7, 0.9, 1.1, 1.3]
CURRENT = (0.8, 1.3)


def parse_ts_ms(ts):
    return int(datetime.fromisoformat(ts).timestamp() * 1000)


def load_entries():
    """Post-Part-B completed entries with entry price and per-trade volatility."""
    opens = {}
    exits = {}
    for line in open(JOURNAL):
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = d.get("ts", "")
        if d.get("event") == "bracket_exit":
            did = (d.get("decision_id") or d.get("deicison_id")
                   or (d.get("plan") or {}).get("decision_id"))
            plan_tp = (d.get("plan") or {}).get("tp_pct")
            exits[did] = {"pnl": float(d.get("pnl_pct", "0")),
                          "plan_tp": float(plan_tp) if plan_tp else None,
                          "trigger": d.get("trigger")}
            continue
        ex = d.get("execution") or {}
        for o in (ex.get("orders") or []):
            if str(o.get("type", "")).startswith("open_"):
                r = o.get("result") or {}
                eb = ex.get("effective_brackets") or {}
                dec = d.get("decision") or {}
                opens[d.get("decision_id")] = {
                    "ts": ts,
                    "side": 1 if o["type"] == "open_long" else -1,
                    "entry": float(r.get("executedAvgPrice") or 0),
                    "eb_tp": float(eb["tp"]) if eb.get("tp") else None,
                    "catalyst": dec.get("catalyst"),
                }

    entries = []
    for did, op in sorted(opens.items(), key=lambda kv: kv[1]["ts"]):
        if op["ts"] < CUTOFF or not op["entry"]:
            continue
        x = exits.get(did)
        if not x:
            continue
        tp_pct = op["eb_tp"] or x["plan_tp"]
        if not tp_pct:
            print(f"  skipping {op['ts'][:16]}: no bracket data to derive volatility")
            continue
        vol = tp_pct / 0.8   # live brackets were tp = 0.8 * vol
        entries.append({"ts": op["ts"], "ts_ms": parse_ts_ms(op["ts"]),
                        "side": op["side"], "entry": op["entry"], "vol": vol,
                        "actual_pnl": x["pnl"], "actual_trigger": x["trigger"],
                        "catalyst": op["catalyst"]})
    if "catalyst-only" in sys.argv:
        entries = [e for e in entries if e["catalyst"] is True]
    return entries


def fetch_series():
    series = {}
    for interval, minutes in (("1m", 1), ("5m", 5)):
        r = get_klines(SYMBOL, interval=interval, limit=1500)
        candles = r.get("candles", r) if isinstance(r, dict) else r
        parsed = [(int(c[0]), float(c[2]), float(c[3]), float(c[4])) for c in candles]
        parsed.sort()
        series[interval] = {"step_min": minutes, "candles": parsed}
        first = datetime.fromtimestamp(parsed[0][0] / 1000, tz=timezone.utc)
        print(f"  {interval}: {len(parsed)} candles, back to {first:%m-%d %H:%M} UTC")
    return series


def pick_series(series, ts_ms):
    if ts_ms >= series["1m"]["candles"][0][0]:
        return series["1m"]
    return series["5m"]


def simulate(entry, tp_mult, sl_mult, series, pessimistic):
    """Walk candles after entry; return (net_pnl, outcome, ambiguous_hit)."""
    s = pick_series(series, entry["ts_ms"])
    tp_pct = entry["vol"] * tp_mult
    sl_pct = entry["vol"] * sl_mult
    side = entry["side"]
    e = entry["entry"]
    tp_level = e * (1 + side * tp_pct / 100)
    sl_level = e * (1 - side * sl_pct / 100)
    end_ms = entry["ts_ms"] + MAX_AGE_MIN * 60_000

    last_close = None
    ambiguous = False
    for t, high, low, close in s["candles"]:
        if t < entry["ts_ms"]:
            continue
        if t >= end_ms:
            break
        last_close = close
        tp_hit = high >= tp_level if side == 1 else low <= tp_level
        sl_hit = low <= sl_level if side == 1 else high >= sl_level
        if tp_hit and sl_hit:
            ambiguous = True
            return (-sl_pct - FEE, "sl", True) if pessimistic else (tp_pct - FEE, "tp", True)
        if tp_hit:
            return (tp_pct - FEE, "tp", False)
        if sl_hit:
            return (-sl_pct - FEE, "sl", False)
    if last_close is None:
        return (0.0, "no-data", False)
    age_pnl = (last_close - e) / e * 100 * side
    return (age_pnl - FEE, "age", ambiguous)


def run_grid(entries, series, pessimistic):
    label = "PESSIMISTIC (stop first in ambiguous candles)" if pessimistic \
        else "OPTIMISTIC (target first in ambiguous candles)"
    print(f"\n=== {label} ===")
    print("total net % over all {} entries; (w/l/a = wins/losses/age-outs)".format(len(entries)))
    header = "  tp\\sl |" + "".join(f"   {sl:>4}    " for sl in SL_MULTS)
    print(header)
    for tp in TP_MULTS:
        cells = []
        for sl in SL_MULTS:
            total = 0.0
            w = l = a = amb = 0
            for en in entries:
                net, outcome, was_amb = simulate(en, tp, sl, series, pessimistic)
                total += net
                amb += was_amb
                if outcome == "tp":
                    w += 1
                elif outcome == "sl":
                    l += 1
                else:
                    a += 1
            mark = "*" if (tp, sl) == CURRENT else " "
            cells.append(f"{mark}{total:+6.2f} {w}/{l}/{a}")
        print(f"  {tp:>4}  |" + " | ".join(cells))
    print("  (* = current live geometry)")


def main():
    entries = load_entries()
    print(f"loaded {len(entries)} completed post-Part-B entries")
    actual = sum(e["actual_pnl"] - FEE for e in entries)
    print(f"actual realized total (net): {actual:+.2f}%")
    print("\nfetching candle series:")
    series = fetch_series()

    # sanity check: replay the CURRENT geometry and compare with reality
    for pess in (True, False):
        total = sum(simulate(e, *CURRENT, series, pess)[0] for e in entries)
        tag = "pessimistic" if pess else "optimistic"
        print(f"sanity check, current geometry replayed ({tag}): {total:+.2f}% "
              f"(reality was {actual:+.2f}%)")

    run_grid(entries, series, pessimistic=True)
    run_grid(entries, series, pessimistic=False)


if __name__ == "__main__":
    main()
