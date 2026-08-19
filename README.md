# LTP Hackathon Trading Bot

An autonomous crypto trading bot built for the Liquidity Arena AI Quant Competition (Track A, Phase 1: July 20 – August 21, 2026). The bot traded Binance perpetual futures (BTC / ETH / SOL) on a 1,000 USDT sandbox account, under a platform rule that every trading decision had to originate from a mandated LLM (MiniMax M3). Our code was only allowed to filter, gate, size, and protect what the model decided.

# How this was built
I built this solo over four weeks as a deliberate double exercise. The first main objective was learning quantitative execution (risk controls, order mechanics, fee arithmetic, experiment design, etc) by operating a live system. The second was learning to engineer things with an AI-assisted pair programmer (Claude Code, in this case). The division of labor stayed fixed throughout: I conceptualized the strategy decisions, the invariants, and everything that shipped, while the AI focused on implementation and analysis. Nothing was implemented unreviewed. Every strategy change was pre-registered in `docs/experiments.md` before going live, every incident closed with a regression test, and both audits in the commit history found their biggest bugs under "fully green" testing environments.

# Some features:

# Architecture
The bot in its initial state way back when the competition started was actually very simple: query the MiniMax M3 model, politely yet firmly ask it to structure its responses in a certain way, then make trades based off that. Many aspects of the final iteration came about through backtesting on then-current trading histories, experimentation, and raw intuition (for better or worse). The final decision pipeline is as follows:

1. **Market scan**: every 300s (150s when flat in a trend), scan BTC/ETH/SOL and select the symbol with the largest absolute 12-hour move.
2. **Trend-only regime gate**: trade entries require that |12h change| ≥ 0.8%. Rangebound entries are structurally impossible. Most, if not all of our profits came from trend days.
3. **Direction alignment**: entries must match the trend sign.
4. **LLM decision**: feed the LLM every available data source (our current trades, candle histories, market data, and news headlines via the competition organizer's API, our own structured rules on entering trades, etc), then query it for its response, which was to include the following: the action to take, its confidence level (between 0 and 1), its reasoning for said action, a "catalyst" flag (whether news headlines were driving the current trade), and its suggested stop and profit brackets. Underlying all of this are parsing methods that strip the LLM response into a designated structure, with the worst-case fallback of skipping the LLM's response entirely.
5. **Entry confirmation vote**: the model is queried a few more times. 2 out of 3 independent model calls must agree on the current course of action for it to occur.
6. **Unanimity boost**: if we have 3 out of 3 model agreements AND a catalyst flag, double the trade size and start the ratchet mechanism, i.e., set our cu
7. **Volatility-scaled brackets**: profit-stop of 0.6x, stop-loss of 0.7, each multiplied by current volatility with a fee-viability gate that refuses entries whose take-profit cannot clear round-trip fees.
8. **Exits**: we abandon a trade under hard stops, or if the ratchet mechanism fires, or due a single contrary model opinion with confidence level 0.65 (one contrary opinion was the safer play and led to better results than, say, two according to counterfactual analyses). Timeout-based exits were implemented early on and removed later (a 1-hour timeout to sell just led to lots of unnecessary bleeding).
9. **Safety guards**: a daily loss-breaker of $5 a day, the ability to hold only one position at a time, hard equity floors before all trading stops completely, and stop-out re-entry cooldowns (i.e., don't enter a trade for a certain amount of time if the last one was a loss. No tilting!).

# Some conclusions:

# Anatomy

src/bot/
  main.py                 # strategy loop, voting, boosted gate
  execution.py            # order placement, brackets, ratchet, breaker, invariants
  state.py                # BotState (__slots__), persisted day anchor
  config.py               # every knob, each with the date and reason it changed
scripts/
  check_rank.py           # scoring-API rank + per-metric percentile decomposition
  analyze_journal.py      # win-rate by category over the decision journal
  bracket_replay.py       # counterfactual replay: real entries vs real candles
docs/experiments.md       # every experiment: pre-registration, cap, verdict
tests/                    # 129 tests, one regression test per incident
src/data/decisions.jsonl  # the dataset (~3k records)

# Status
The competition phase ended August 21, 2026. The bot was deliberately frozen for the final week (with entries disabled, exits and safety rails live) once the boosted cohort review killed the last remaining thesis; under the competition's massive emphasis on Sharpe-weighted scoring (which comprised 40% of the total score), NOT trading strictly dominated trading without edge. The service is now stopped. RIP. 
