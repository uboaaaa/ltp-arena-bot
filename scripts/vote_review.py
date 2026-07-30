"""Pre-registered review of the weak-exit confirmation vote (docs/experiments.md).

For every PASSED vote: replay minute candles from the exit moment forward and
compute what the original brackets (tp/sl/max-age from the trade's plan) would
have delivered had the vote not fired. diff = actual - counterfactual, so
positive diff means the vote beat the brackets. Fees cancel (both paths pay
one close), so gross pnl is compared directly.

For every FAILED vote: compare the position's pnl at the vote moment (parsed
from the prompt's stance line) against the trade's actual final outcome, i.e.
what honoring the minority opinion would have changed.

Read-only. Run from src/:  python3 ../scripts/vote_review.py
"""

import json
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")
from broker.rapidx import get_klines  # noqa: E402

JOURNAL = "data/decisions.jsonl"
SYMBOL = "BINANCE_PERP_BTC_USDT"
MAX_AGE_S = 4 * 3600
MIN_HOLD_S = 900


def ts_ms(ts):
    return int(datetime.fromisoformat(ts).timestamp() * 1000)


def load():
    opens, exits, passed, failed = {}, {}, [], []
    for line in open(JOURNAL):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = rec.get("ts", "")
        ev = rec.get("event")
        if ev == "model_exit":
            passed.append(rec)
            exits[rec.get("decision_id")] = rec
            continue
        if ev == "bracket_exit":
            did = (rec.get("decision_id") or rec.get("deicison_id")
                   or (rec.get("plan") or {}).get("decision_id"))
            exits[did] = rec
            continue
        ex = rec.get("execution") or {}
        if str(ex.get("transition")) == "VOTE_HOLD":
            failed.append(rec)
        for o in (ex.get("orders") or []):
            if str(o.get("type", "")).startswith("open_"):
                r = o.get("result") or {}
                opens[rec.get("decision_id")] = {
                    "ts": ts, "entry": float(r.get("executedAvgPrice") or 0),
                    "side": 1 if o["type"] == "open_long" else -1}
    return opens, exits, passed, failed


def fetch_series():
    out = {}
    for interval in ("1m", "5m"):
        r = get_klines(SYMBOL, interval=interval, limit=1500)
        c = r.get("candles", r) if isinstance(r, dict) else r
        out[interval] = sorted((int(x[0]), float(x[2]), float(x[3]), float(x[4])) for x in c)
    return out


def counterfactual(entry_px, side, tp_pct, sl_pct, from_ms, deadline_ms, series):
    candles = series["1m"] if from_ms >= series["1m"][0][0] else series["5m"]
    tp_lvl = entry_px * (1 + side * tp_pct / 100)
    sl_lvl = entry_px * (1 - side * sl_pct / 100)
    last_close = None
    for t, high, low, close in candles:
        if t < from_ms:
            continue
        if t >= deadline_ms:
            break
        last_close = close
        tp_hit = high >= tp_lvl if side == 1 else low <= tp_lvl
        sl_hit = low <= sl_lvl if side == 1 else high >= sl_lvl
        if tp_hit and sl_hit:
            return ("ambiguous->sl", -sl_pct)
        if tp_hit:
            return ("take_profit", tp_pct)
        if sl_hit:
            return ("stop_loss", -sl_pct)
    if last_close is None:
        return ("no-data", 0.0)
    return ("max_age", (last_close - entry_px) / entry_px * 100 * side)


def main():
    opens, exits, passed, failed = load()
    series = fetch_series()
    print(f"PASSED votes: {len(passed)}   FAILED votes: {len(failed)}\n")

    print("=== passed votes: actual vote exit vs bracket counterfactual ===")
    total_diff = 0.0
    for rec in passed:
        did = rec.get("decision_id")
        op = opens.get(did)
        plan = rec.get("plan") or {}
        if not op or not plan.get("tp_pct"):
            print(f"  {rec['ts'][:16]}  SKIP (missing open or plan)")
            continue
        side = 1 if plan.get("side") == "LONG" else -1
        opened_at = float(plan.get("opened_at", 0))
        actual = float(rec.get("pnl_pct") or 0)
        held_s = ts_ms(rec["ts"]) / 1000 - opened_at
        cf_kind, cf_pnl = counterfactual(
            op["entry"], side, float(plan["tp_pct"]), float(plan["sl_pct"]),
            ts_ms(rec["ts"]), int((opened_at + MAX_AGE_S) * 1000), series)
        diff = actual - cf_pnl
        total_diff += diff
        inhold = " <MIN-HOLD" if held_s < MIN_HOLD_S else ""
        print(f"  {rec['ts'][:16]}  {plan.get('side'):<5} held {held_s/60:4.0f}m{inhold}"
              f"  vote exit {actual:+.3f}%  brackets would: {cf_kind:<13} {cf_pnl:+.3f}%"
              f"  -> vote {'BEAT' if diff > 0 else 'LOST'} by {abs(diff):.3f}%")
    print(f"\n  net: vote vs brackets across passed votes: {total_diff:+.3f}% "
          f"({'vote is ahead' if total_diff > 0 else 'brackets were better'})")
    print(f"  abort criterion (worse than -1.0%): {'TRIGGERED' if total_diff < -1.0 else 'not triggered'}")

    print("\n=== failed votes: what honoring the minority would have changed ===")
    for rec in failed:
        ts = rec.get("ts", "")
        m = re.search(r"currently ([+-][\d.]+)%", rec.get("prompt", ""))
        pnl_then = float(m.group(1)) if m else None
        # find the trade this vote belonged to: latest open before ts with exit after ts
        owner = None
        for did, op in opens.items():
            x = exits.get(did)
            if op["ts"] <= ts and x and x.get("ts", "") >= ts:
                owner = (op, x)
        if not owner or pnl_then is None:
            print(f"  {ts[:16]}  (context incomplete)")
            continue
        final = float(owner[1].get("pnl_pct") or 0)
        trig = owner[1].get("trigger")
        diff = pnl_then - final
        print(f"  {ts[:16]}  pnl then {pnl_then:+.2f}%  actual end: {trig} {final:+.2f}%"
              f"  -> minority would have {'SAVED' if diff > 0 else 'COST'} {abs(diff):.2f}%")


if __name__ == "__main__":
    main()
