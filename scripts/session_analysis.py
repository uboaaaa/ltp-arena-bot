"""One-off session queries for the 2026-07-28 analyzer session.

Q2: does entering after the move already ran predict losses?
Q3: win size versus loss size, post-Part-B only.
Q4: would honoring the model's moderate-confidence exit signals have helped?

Read-only. Run from repo root: python3 scripts/session_analysis.py
"""

import json
import re
from datetime import datetime

PATH = "src/data/decisions.jsonl"
CUTOFF = "2026-07-23T00:00"   # start of the post-Part-B era
FEE = 0.08                    # taker round trip, percent


def parse_ts(ts):
    return datetime.fromisoformat(ts)


records = []
for line in open(PATH):
    try:
        records.append(json.loads(line))
    except json.JSONDecodeError:
        continue

opens = {}
exits = {}
for d in records:
    ts = d.get("ts", "")
    if d.get("event") == "bracket_exit":
        did = (d.get("decision_id") or d.get("deicison_id")
               or (d.get("plan") or {}).get("decision_id"))
        exits[did] = {"ts": ts, "trigger": d.get("trigger"),
                      "pnl": float(d.get("pnl_pct", "0"))}
        continue
    ex = d.get("execution") or {}
    for o in (ex.get("orders") or []):
        if str(o.get("type", "")).startswith("open_"):
            dec = d.get("decision") or {}
            m3 = re.search(r"last 3h ([+-]?[\d.]+)%", d.get("prompt", ""))
            opens[d.get("decision_id")] = {
                "ts": ts,
                "type": o.get("type"),
                "conf": dec.get("confidence"),
                "cat": dec.get("catalyst"),
                "ext3h": float(m3.group(1)) if m3 else None,
            }

# ---------- Q2: extension at entry ----------
print("=== Q2: post-Part-B entries, sorted by time ===")
print("ext3h(dir) = how far the last 3h had ALREADY moved in the trade's direction at entry\n")
exit_times = sorted(x["ts"] for x in exits.values())
rows = []
for did, op in sorted(opens.items(), key=lambda kv: kv[1]["ts"]):
    if op["ts"] < CUTOFF:
        continue
    x = exits.get(did)
    direction = 1 if op["type"] == "open_long" else -1
    ext = op["ext3h"] * direction if op["ext3h"] is not None else None
    prev = [t for t in exit_times if t < op["ts"]]
    reentry_min = (parse_ts(op["ts"]) - parse_ts(prev[-1])).total_seconds() / 60 if prev else None
    net = (x["pnl"] - FEE) if x else None
    rows.append({"ts": op["ts"][:16], "side": op["type"][5:], "ext": ext,
                 "reentry": reentry_min, "trigger": x["trigger"] if x else "still-open",
                 "net": net, "cat": op["cat"]})

for r in rows:
    ext = f"{r['ext']:+.2f}%" if r["ext"] is not None else "   ?  "
    re_m = f"{r['reentry']:6.0f}m ago" if r["reentry"] is not None else "  first   "
    net = f"{r['net']:+.3f}" if r["net"] is not None else " open"
    print(f"  {r['ts']}  {r['side']:<5} cat={str(r['cat']):<5} ext3h {ext:>8}  last-exit {re_m}  {r['trigger']:<11} net {net}")

done = [r for r in rows if r["net"] is not None and r["ext"] is not None]
print()
for name, grp in (
    ("entries AFTER >=0.50% same-direction 3h move (late entries)",
     [r for r in done if r["ext"] >= 0.50]),
    ("entries with <0.50% prior same-direction move (early entries)",
     [r for r in done if r["ext"] < 0.50]),
):
    if grp:
        wins = [g for g in grp if g["net"] > 0]
        avg = sum(g["net"] for g in grp) / len(grp)
        tot = sum(g["net"] for g in grp)
        print(f"  {name}:")
        print(f"      n={len(grp)}  wins={len(wins)}  winrate={len(wins)/len(grp):.0%}  avg net {avg:+.3f}%  total {tot:+.3f}%")

# ---------- Q3: geometry ----------
completed = [r["net"] for r in rows if r["net"] is not None]
wins = [n for n in completed if n > 0]
losses = [n for n in completed if n <= 0]
print("\n=== Q3: win/loss geometry, post-Part-B, net of fees ===")
print(f"  completed trades: {len(completed)}")
print(f"  wins:   {len(wins):>2}  average {sum(wins)/len(wins):+.3f}%")
print(f"  losses: {len(losses):>2}  average {sum(losses)/len(losses):+.3f}%")
aw = sum(wins) / len(wins)
al = abs(sum(losses) / len(losses))
print(f"  net total: {sum(completed):+.3f}%")
print(f"  with these sizes, the win rate needed just to break even is {al/(al+aw):.1%}")

# ---------- Q4: weak exit signals ----------
print("\n=== Q4: moderate-confidence exit signals while holding (first signal per trade) ===")
intervals = []
for did, op in opens.items():
    x = exits.get(did)
    if x:
        side = "LONG" if op["type"] == "open_long" else "SHORT"
        intervals.append({"start": op["ts"], "end": x["ts"], "side": side,
                          "final": x["pnl"], "trigger": x["trigger"], "first_sig": None})

for d in records:
    if d.get("event"):
        continue
    ts = d.get("ts", "")
    dec = d.get("decision") or {}
    prompt = d.get("prompt", "")
    mp = re.search(r"currently ([+-][\d.]+)%", prompt)
    if not mp:
        continue
    pnl_now = float(mp.group(1))
    act = dec.get("action")
    conf = dec.get("confidence") or 0
    iv = next((i for i in intervals if i["start"] <= ts <= i["end"]), None)
    if iv is None or iv["first_sig"] is not None:
        continue
    contrary = (act == "FLAT") or (act in ("LONG", "SHORT") and act != iv["side"])
    if contrary and 0.60 <= conf < 0.80:
        iv["first_sig"] = {"ts": ts, "act": act, "conf": conf, "pnl_now": pnl_now}

n_sig = 0
saved_total = 0.0
for iv in sorted(intervals, key=lambda i: i["start"]):
    s = iv["first_sig"]
    if not s:
        continue
    n_sig += 1
    diff = s["pnl_now"] - iv["final"]
    saved_total += diff
    verdict = "SAVED" if diff > 0 else "would have COST"
    print(f"  {s['ts'][:16]}  holding {iv['side']}: model said {s['act']} conf {s['conf']}")
    print(f"      position was {s['pnl_now']:+.2f}% then; actually ended {iv['final']:+.2f}% ({iv['trigger']})"
          f"  -> closing on the signal {verdict} {abs(diff):.2f}%")
print(f"\n  trades with a weak exit signal: {n_sig}")
print(f"  net effect if the bot had closed on every first signal: {saved_total:+.2f}% (price terms)")
print("  (note: only trades after the stance line was added on Jul 23 evening carry the")
print("   'currently X%' data, so this covers the recent era only)")
