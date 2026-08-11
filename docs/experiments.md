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
### Review 1 (2026-07-30, at 12 fired votes - pre-registered gate was 10)
Counterfactual replay of all 8 passed votes: vote exits beat the bracket
alternative by +1.61% net (5 beats incl. a +1.02% escaped stop, 3 forgone
take-profits). Abort criterion not triggered. Min-hold-window votes showed
no adverse pattern (n=2, split). VERDICT: rule kept unchanged.
Tracked question for review 2 (at 25 fired votes): in 3 of 4 FAILED votes the
lone minority opinion was right (+0.58% forgone); evaluate honoring first
signals without a vote, but only with the larger sample.

### Stop review (2026-07-30, at 11 completed trades under the 0.7 stop)
Replay of the new-era entries: live 0.7 stop beat the old 1.3 by ~+0.47%.
Far-tight stops (0.4-0.5) flipped from worst (review 1) to best (this week)
- regime-dependent, so no further tightening; SL 0.7 KEPT.
TP finding: 0.6 x vol beat the live 0.8 in BOTH independent samples
(+0.25% and +1.23%); registered question resolved -> RECOMMEND VOL_TP_MULT
0.8 -> 0.6. All grid cells negative again: entry quality remains the
frontier (third confirmation).

## Entry confirmation vote (enabled 2026-07-30)
Rule: while flat, a proposed LONG/SHORT at conf >= 0.6 triggers two extra
model calls on the same prompt; the entry proceeds only if at least 2 of 3
opinions agree on the direction. The original decision executes (brackets
derive from it); the vote only gates. All three opinions journaled under
entry_votes.
Evidence at adoption: documented model flip-flops on near-identical prompts;
2026-07-30 churn (three single-opinion 0.6-conf entries, all losses, one
renounced 3-0 by its own exit vote 5 min later); exit-side sibling mechanism
beat its counterfactual +1.61% at review 1.
Review: after 15 FAILED entry votes, counterfactual-replay the skipped
entries. Abort: disable if skipped entries would have netted > +1.5%
(the filter is blocking good trades).

## Trend-only pivot (2026-08-01)
Every green period in the bot's life was a trend day (Jul 24, Jul 27-28,
Jul 31 ladder); chop-adjacent trading has been net negative lifetime across
every category (chop entries, fades, marginal-conf entries). Three replay
studies showed the entry population carries no edge that exit geometry can
rescue. Decision: stop paying the chop tax entirely.
Changes: CHOP_CONF_FLOOR raised to 1.01 (no rangebound entries can pass);
edge-zone experiment CLOSED EARLY at 2 of 15 trades (1 stop-loss, 1 vote
scratch - insufficient opportunity, superseded by this pivot).
Expected shape: many zero-trade days punctuated by trend-day clusters.
This is the NDAR profile and the best available Sharpe shape.
Review: standing - compare trend-only era daily PnL and Sharpe percentile
vs the 2026-07-23..31 era at phase end.

## Unanimity sizing (2026-08-01)
Rule: an entry that passes its vote 3-of-3 (all opinions same direction, no
parse failures) AND carries catalyst=true is sized at 2x the minimum lot
(~13 pct of equity at 1x; worst-case ~0.06 pct of equity per stop). All
other entries stay at minimum. Rationale: wins are too small to move the
Sharpe percentile (Jul 31 ladder: 4 wins = ~USD 0.90); unanimity+catalyst
is the highest-evidence gate we have and included the best winners.
Review: after 10 boosted trades, compare boosted vs single-size outcomes.
Abort: revert to flat sizing if boosted trades underperform singles.

## Size escalation (2026-08-01, user-approved)
BASE_POSITION_FRACTION 0.08 -> 0.25 (still 1x leverage, trend-only entries,
all votes and brackets unchanged; unanimity boost stacks to ~0.5 of equity).
Rationale: tournament position (rank 44/49, ~11 composite points below the
cutoff, 20 days left). Cutoff is held by dormant bots at Sharpe -5.3; only
real green PnL (~+4 to +6 USDT) climbs past it, which is unreachable at
minimum size. Behind-with-a-deadline = maximize variance.
Risk: ~0.1-0.2 pct of equity per stopped trade; existing halt floors
(soft 965 / hard 955) are the pre-committed abort. MDD tier may take scars;
accepted knowingly.
Review: standing at phase end; abort = the halt floors themselves.

## Audit Tier 1 (2026-08-02, from the 29-agent audit; user: ship it)
1. Conviction tiers FLATTENED: confidence measured non-predictive (no band has
   positive edge; model max executed conf 0.72, CONF_FULL 0.8 unreachable),
   so the silent 0.5x half-sizing is removed - approved sizing now delivers
   ~250 USD base, ~500 boosted. CONF_FULL still gates reversals.
2. Unanimity boost accepts catalyst from ANY of the 3 unanimous samples
   (was first-sample-only); catalyst journaled per vote (was unmeasurable).
3. Direction-alignment gate: in a trending regime, entries opposing the 12h
   sign are refused (counter-trend lifetime record 1W/9L).
4. sleep_for bug fixed (loop hardcoded STRATEGY_INTERVAL, silently disabling
   the 1800s AI-budget backoff); adaptive cadence 150s while FLAT in trend.
5. Hardening: model-exit survives the bracket-race NO_POSITION error (prod
   crash 2026-07-30 13:35); entries fail CLOSED on missing 12h/vol data.
6. Daily-loss circuit breaker: new entries blocked when ranking-day pnl
   (16:00 UTC anchor) reaches -1.5 USDT. One -2 day costs ~1.6 Sharpe units.
Review: standing at phase end; full audit in memory + task output file.

## Post-sweep batch (2026-08-02, user: ship it)
1. Fee-viability gate: entries refused when derived TP (0.6 x vol) would floor
   below MIN_TP_PCT - the floor was silently inverting risk-reward in low vol
   (Aug 1 boosted trades ran TP 0.15 vs SL 0.163-0.170, breakeven 68%).
2. Daily-loss breaker anchor persists to data/day_anchor.json - restarts no
   longer reset the ranking-day loss budget (regression in d20b372, fixed).
3. MAX_POSITION_AGE 4h -> 1h (trend-entry holds of 60-120min ran 9% winrate,
   n=11, in-sample caveat); unanimity-boosted trades keep a 2h leash.
4. PROMPT_HEADER truth rewrite: trend-only rules stated, vol-derived brackets
   acknowledged (model tp/sl advisory), ~1h force-close disclosed, real fees
   (0.05%), dead chop-fade language removed. JSON contract unchanged.
Review: standing at phase end; per-change notes in the sweep results file.

## Trailing ratchet on boosted trades (2026-08-02); trend-onset carve-out REJECTED
Ratchet (boosted = unanimous 3-of-3 + catalyst entries only): fixed take-profit
replaced by a trail - at +0.6x vol the stop locks to +0.08% (fees floor) and
trails the peak by 0.7x vol; only ever tightens. Trail exits (trigger
trail_stop) carry no stop cooldown; an armed ratchet suppresses exit votes
(the trade is risk-free, the trail owns the exit). Regular trades unchanged.
Judged at the pre-registered 10-boosted-trade review. Honest basis: +-6
expected over the window, n=8 replayed, 2 runners drove it - variance play.
Trend-onset carve-out: REJECTED by its own counterfactual before shipping.
Full-population replay (all sub-threshold signals with aligned 3h>=0.5,
flat stance, conf>=0.6, 45-min dedupe, 15m candles pessimistic): n=6 over
the whole phase, 3 TP / 0 SL / 3 age-outs, net +0.10% total. The earlier
6-of-8 figure was hindsight-selected on days that became trends. Not worth
prompt+gate complexity; re-examine only if trend days prove scarcer still.

## ETH rotation + max-age revert (2026-08-04, user: ship ETH / stop the bleeding)
Rotation: SYMBOLS = [BTC, ETH]; when flat, each cycle scans both and runs the
normal single-symbol pipeline on the one with the larger |12h| change; when
holding, only the held symbol is watched. One position at a time, ever. Plans
carry their symbol and survive restarts. ETH leverage verified set to 1
(default was 5; competition cap 2) BEFORE the code shipped. Model-call budget
unchanged (still one decision per cycle). Basis: ETH trends ~25% more often
and moves ~42% more per hour (audit-verified); this roughly doubles hunting
days for the same signal.
Max-age reverted 1h -> 2h: the 1h leash's live record was 8 timeouts / 1 win
of pure fee churn in slow-grind markets; the in-sample +1.9 never materialized.
Review: standing at phase end - ETH trades graded against BTC trades by the
analyzer (symbol is in every order result and plan).

## Max throttle + SOL (2026-08-04, user conditional: ship only if top-30 plausible - it is, barely)
BASE_POSITION_FRACTION 0.25 -> 0.5; leverage set and VERIFIED at 2 on BTC/ETH/SOL
(competition cap, fully used); DAILY_LOSS_LIMIT 2.5 -> 5.0 (~1 boosted stop + 1 base
stop of daily room); SOL added to scan list. Base trade ~USD 490, boosted ~USD 980.
Ordinary win ~+2.4, ordinary stop ~-2.1, boosted stop ~-4.2, ratchet runner 10-20.
Honest odds stated: ~1 in 10 with cooperative weather; at previous throttle the
16-point composite gap was not plausibly closable. Compliance reconstruction
explicitly SKIPPED by user directive (on record). Review: phase end.

## Time limit removed (2026-08-05, user directive)
MAX_POSITION_AGE deleted entirely (was 4h -> 1h -> 2h across its life).
Positions now end only at the stop, the trailing ratchet, or an exit vote.
Rationale: the limit's own record - 13 lifetime timeout exits netting ~zero,
the 1h version proven fee churn, the death-zone stats revealed as in-sample
noise - plus the T.Anh observation (only currently-winning team holds
positions for days; +15 USD in a week on zero new trades). The limit made
ratchet runners structurally impossible. Risk accepted: stagnant positions
can block the single trading slot; the exit vote and 5-min re-evaluation
are the remaining slot-clearing mechanisms.

### Exit-vote review 2 (2026-08-07, at 30+ fired votes) + floors drop
Counterfactual: 13 of 14 recent passed votes BEAT the bracket alternative
(cumulative +1.9%); the vote consistently cuts losers at roughly half the
full stop. Mechanism KEPT and STRENGTHENED per the tracked review-1 question:
lone minority opinions were right 10/14 across both reviews (net ~+1.1%),
so confirmation sampling is removed - EXIT_VOTE_CALLS 0, EXIT_VOTES_NEEDED 1:
the first exit opinion at conf >= 0.65 closes the position immediately.
Saves 2 LLM calls per event and exits earlier, which the counterfactuals
consistently reward in this regime.
Floors dropped 965/955 -> 850/825 (user directive: trade every remaining
day). Arithmetic: daily breaker caps losses at 5/day x 14 days = max -70
from equity 970, so the floors are unreachable before Aug 21 and now serve
only as elimination insurance (800). MDD tier already broke 100 -> 90.

### BUG FIX: position stacking on ETH/SOL (2026-08-07)
execute_decision computed its stance with current_stance(open_positions) - no
symbol argument - so it always asked about BTC. While holding SOL or ETH it
therefore read FLAT and opened ANOTHER position on the same symbol (NET mode
compounds these into one oversized position). Introduced with the rotation
build (ffbb252, Aug 4); visible in the journal as consecutive 'FLAT ->
OPEN_LONG' transitions whose prompts said 'holding a LONG'. Confirmed cases:
Aug 7 09:27/09:46/10:01 SOL (3 stacked), plus similar ETH runs Aug 5-6.
Real sizes were therefore up to ~3x intended on those days.
Fixes: (1) stance is now computed for the traded symbol; (2) NEW one-position
invariant - any nonzero position on a different symbol refuses the entry
outright; (3) describe_stance filters by the plan's symbol so the prompt and
the gate can never disagree again. 3 regression tests added (122 total).

## Boosted-only endgame mode (2026-08-11, user: ship it)
The governing arithmetic, finally stated as policy: EV per trade = gross edge
(~0, measured) minus fees (0.05%), so ordinary trades are a guaranteed drip
of ~-$2-4/day at full frequency and size. The win condition lives entirely
in the rare full-alignment trade (unanimous 3-of-3 vote + catalyst, ~$980
boosted, trailing ratchet). BOOSTED_ONLY=True retires ordinary entries:
passed votes without full alignment are journaled as BOOSTED_ONLY_SKIP and
not traded. Expected effect: daily bleed to ~0, tail exposure retained at
~1 strike every 1-2 days. This is the final strategic configuration of the
campaign. Review: phase end.
