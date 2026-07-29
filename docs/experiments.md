# Pre-registered experiments

## Weak-exit confirmation vote (live 2026-07-29)
Rule: while holding a position, a model opinion that disagrees with it at
confidence 0.65-0.79 triggers two extra model calls on the same prompt.
If at least 2 of the 3 opinions vote to be out, close (no reversal, no
stop cooldown). Strong reversals (conf >= 0.8) keep their existing path.
Knobs: EXIT_CONF=0.65, EXIT_VOTE_CALLS=2, EXIT_VOTES_NEEDED=2.
Evidence at adoption: 6 historical weak-exit signals; honoring the first
signal each time would have netted +0.41% (4 saves, 2 costs). That mean is
statistically indistinguishable from zero. The voting layer itself is
untested and cannot be tested retroactively. This is a capped experiment.
After 10 fired votes (passed or failed), compare each vote's exit
pnl against the counterfactual bracket outcome via minute-candle replay.
We abort this experiment if completed exits cost more than 1.0% cumulative versus
counterfactual.

## Stop tightening, VOL_SL_MULT 1.3 -> 0.7 (live 2026-07-27)
Basis: replay of 16 real entries across a tp/sl grid (scripts/bracket_replay.py).
Stop at 0.6-0.7 x vol was optimal with a cliff below 0.5; tp effect within noise.
Review: rerun the replay after 15 completed trades under the new stop.

## Edge-zone fade exception (built inert 2026-07-29, enabled 2026-07-29)
Rule: in chop (|12h| < 0.8%), entries at conf 0.60-0.69 survive the chop
backstop only when fading from the outer 20% of the day's range (LONG at
<= 20% of range, SHORT at >= 80%). Chasing at the edge and mid-range
entries stay gated. Brackets, sizing, and cooldowns unchanged.
Evidence at adoption: 9 vetoed fade proposals over one chop week; historical
fade category 0-for-3 post-overhaul (small max_age losses) - this is a
hypothesis test, not a proven edge.
Review: after 15 completed edge-zone trades or -1.0% cumulative category
net, whichever first; judged by the analyzer's edge-zone-fade row.
Abort: disable the flag at the -1.0% cap.