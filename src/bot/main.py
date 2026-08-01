""" Bot skeleton. Uses three event loops on one event loop via asyncio. 
Run using: python3 -m bot.main (from src/) """

import asyncio
import json
import logging
import time

# ai imports
from ai.client import ask_llm
from ai.parsing import parse_llm_decision
from ai.prompt import build_prompt

# bot imports
from bot.config import (
    EXECUTION_ENABLED,
    BRACKET_COOLDOWN_SECONDS,
    HARD_FLATTEN_EQUITY,
    HEARTBEAT_INTERVAL,
    RISK_INTERVAL,
    STRATEGY_INTERVAL,
    SYMBOL,
    EXIT_VOTE_CALLS,
    EXIT_VOTES_NEEDED,
    ENTRY_VOTE_ENABLED,
    ENTRY_VOTE_CALLS,
    ENTRY_VOTES_NEEDED,
    CONF_FLOOR,
    UNANIMITY_SIZE_MULT,
    TREND_SCAN_INTERVAL,
    CHOP_THRESHOLD_PCT
)
from bot.state import BotState
from bot.execution import (
    execute_decision,
    check_bracket,
    avg_hourly_range_pct,
    change_12h_pct,
    handle_bracket_exit,
    current_stance,
    should_call_exit_vote,
    count_exit_votes,
    handle_model_exit,
    ticker_range_position_pct,
    count_agreeing_votes
)
from bot import journal

# broker imports
from broker.rapidx import (
    get_equity, 
    get_open_positions,
    get_ticker,
    get_klines,
    get_funding_rate,
    cancel_all_orders,
    close_all_positions,
)

# feed imports
from feeds import sosovalue
from feeds.news import get_recent_headlines as ltp_headlines 

# other
from openai import RateLimitError
from logging.handlers import RotatingFileHandler

log = logging.getLogger("bot")

def setup_logging() -> None:
    fmt = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt)
    file_handler = RotatingFileHandler("bot.log", maxBytes=5_000_000, backupCount=3)
    file_handler.setFormatter(logging.Formatter(fmt))
    logging.getLogger().addHandler(file_handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)

async def startup_reconciliation(state: BotState) -> None:
    """ Reality check before acting (i.e., check what we're currently holding) """ 
    log.info("startup: querying existing state...")
    try:
        equity = await asyncio.to_thread(get_equity)
        state.update_equity(equity)
        positions = await asyncio.to_thread(get_open_positions)
        state.update_positions(positions)
        if positions:
            state.load_plan()
            if state.active_plan:
                log.info("startup: restored bracket plan: %s", state.active_plan)
            else:
                log.warning("startup: open position with NO saved plan. using default brackets")
        else:
            state.set_plan(None)
        log.info("startup complete: %s", state.summary())

    except Exception:
        log.exception("startup reconciliation failed. starting blind and retrying loops")
    
async def risk_monitor(state: BotState) -> None:
    while True:
        try:
            equity = await asyncio.to_thread(get_equity)
            state.update_equity(equity)
            ranking_day = (int(time.time()) - 57600) // 86400   # 16:00 UTC ranking-day boundary
            if state.ranking_day != ranking_day:
                state.ranking_day = ranking_day
                state.day_start_equity = equity
                log.info("ranking day rollover: anchor equity %s", equity)
            positions = await asyncio.to_thread(get_open_positions)
            state.update_positions(positions)

            trigger = None
            if time.time() - state.last_bracket_close_at > BRACKET_COOLDOWN_SECONDS:
                trigger = check_bracket(state)
            if trigger:
                reason, pnl_pct = trigger
                log.info("BRACKET %s at %+.3f%%", reason, pnl_pct)
                if EXECUTION_ENABLED:
                    try:
                        await asyncio.to_thread(handle_bracket_exit, state, trigger)
                    except Exception:
                        log.critical("BRACKET CLOSE FAILED (%s at %+.3f%%); POSITION UNPROTECTED! Retrying next cycle", reason, pnl_pct, exc_info=True)
        

            if equity < HARD_FLATTEN_EQUITY and not state.halted:
                state.halted = True
                state.halt_reason = f"equity {equity} < hard limit {HARD_FLATTEN_EQUITY}"
                log.critical("HARD LIMIT BREACHED: %s", state.halt_reason)
                if EXECUTION_ENABLED:
                    log.critical("flattening everything")
                    try:
                        await asyncio.to_thread(cancel_all_orders)
                        await asyncio.to_thread(close_all_positions)
                    except Exception:
                        log.exception("FLATTEN FAILED. INTERVENE MANUALLY")

        except Exception as e:
            log.warning("risk cycle failed (%s) - equity age now %.0fs", e, state.equity_age)
            
        await asyncio.sleep(RISK_INTERVAL)

async def strategy_loop(state: BotState) -> None:
    while True:
        sleep_for = STRATEGY_INTERVAL
        try:
            if state.halted:
                log.info("strategy: halted (%s). observing only", state.halt_reason)
            else:
                ticker = await asyncio.to_thread(get_ticker, SYMBOL)
                klines = await asyncio.to_thread(get_klines, SYMBOL)
                klines_5m = await asyncio.to_thread(get_klines, SYMBOL, "5m", 12)
                range_pos = ticker_range_position_pct(ticker)
                vol_pct = avg_hourly_range_pct(klines)
                chg_12h = change_12h_pct(klines)
                funding = await asyncio.to_thread(get_funding_rate, SYMBOL)

                try:
                    headlines = await asyncio.to_thread(sosovalue.get_recent_headlines)
                    if not headlines:
                        headlines = await asyncio.to_thread(ltp_headlines)
                except Exception:
                    log.warning("news fetch failed. continuing without headlines.", exc_info=True)
                    headlines = []

                if (chg_12h is not None and abs(chg_12h) >= CHOP_THRESHOLD_PCT
                        and current_stance(state.open_positions) == "FLAT"):
                    sleep_for = TREND_SCAN_INTERVAL   # scan faster while flat in a trending market
                prompt = build_prompt(ticker, klines, funding, headlines, state, klines_5m)
                raw = await asyncio.to_thread(ask_llm, prompt)
                decision = parse_llm_decision(raw)
                decision_id = f"d-{int(time.time() * 1000)}"

                entry = {
                    "decision_id" : decision_id,
                    "equity" : str(state.equity),
                    "prompt" : prompt,
                    "raw_reply" : raw,
                    "decision" : decision,
                    "execution" : None,
                }

                if decision is None:
                    log.warning("strategy: unparseable AI reply, skipping cycle: %r", raw)
                else:
                    state.update_decision(decision)
                    log.info("strategy: decision=%s   conf=%f   reason=%s", decision['action'], decision['confidence'], decision['reasoning'])
                    stance = current_stance(state.open_positions)
                    if EXECUTION_ENABLED and should_call_exit_vote(stance, decision):
                        votes = [decision]
                        for _ in range(EXIT_VOTE_CALLS):
                            extra = parse_llm_decision(await asyncio.to_thread(ask_llm, prompt))
                            if extra:
                                votes.append(extra)
                        tally = count_exit_votes(stance, votes)
                        if tally >= EXIT_VOTES_NEEDED:
                            log.info("MODEL EXIT vote passed (%d of %d): closing %s", tally, len(votes), stance)
                            entry["execution"] = await asyncio.to_thread(handle_model_exit, state, votes)
                        else:
                            log.info("Model exit vote failed (%d of %d): holding", tally, len(votes))
                            entry["execution"] = {"transition" : "VOTE_HOLD", "votes_for_exit" : tally}
                    
                    elif (EXECUTION_ENABLED and ENTRY_VOTE_ENABLED
                            and stance == "FLAT"
                            and decision["action"] in ("LONG", "SHORT")
                            and float(decision["confidence"]) >= CONF_FLOOR):
                        votes = [decision]
                        for _ in range(ENTRY_VOTE_CALLS):
                            extra = parse_llm_decision(await asyncio.to_thread(ask_llm, prompt))
                            if extra:
                                votes.append(extra)
                        tally = count_agreeing_votes(decision["action"], votes)
                        entry["entry_votes"] = [{"action" : v.get("action"), "confidence" : v.get("confidence"), "catalyst" : v.get("catalyst")} for v in votes]
                        if tally >= ENTRY_VOTES_NEEDED:
                            boost = UNANIMITY_SIZE_MULT if (tally == 3 and len(votes) == 3 and any(v.get("catalyst") is True for v in votes)) else None
                            log.info("ENTRY vote passed (%d of %d): proceeding with %s%s", tally, len(votes), decision["action"], " [UNANIMITY BOOST]" if boost else "")
                            if boost:
                                result = await asyncio.to_thread(execute_decision, state, decision, decision_id, vol_pct, chg_12h, range_pos, boost)
                            else:
                                result = await asyncio.to_thread(execute_decision, state, decision, decision_id, vol_pct, chg_12h, range_pos)
                            entry["execution"] = result
                            log.info("execution summary: %s", json.dumps(result, default=str))
                        else:
                            log.info("ENTRY vote failed (%d of %d): skipping %s", tally, len(votes), decision["action"])
                            entry["execution"] = {"transition" : "ENTRY_VOTE_FAIL", "votes_for" : tally}

                    elif EXECUTION_ENABLED:
                        result = await asyncio.to_thread(execute_decision, state, decision, decision_id, vol_pct, chg_12h, range_pos)
                        entry["execution"] = result
                        log.info("execution summary: %s", json.dumps(result, default=str))
                    else:
                        log.info("strategy: EXECUTION DISABLED - LOG ONLY")
                
                journal.record(entry)

        except RateLimitError:
            sleep_for = 1800
            log.warning("AI budget exhausted (HTTP 429). Backing off for %ds", sleep_for)

        except Exception:
            log.exception("strategy cycle failed. will retry next interval!")
        
        await asyncio.sleep(sleep_for)

async def heartbeat(state: BotState) -> None:
    while True:
        log.info("heartbeat: %s", state.summary())
        await asyncio.sleep(HEARTBEAT_INTERVAL)

async def main() -> None:
    setup_logging()
    log.info("=== BOT STARTING (EXECUTION_ENABLED=%s) ===", EXECUTION_ENABLED)
    state = BotState()
    await startup_reconciliation(state)
    try:
        await asyncio.gather(
            risk_monitor(state),
            strategy_loop(state),
            heartbeat(state),
        )
    finally:
        log.info("=== bot stopping: %s ===", state.summary())
        if state.open_positions:
            log.critical("STOPPING WITH %d OPEN POSITION(S). Handle manually!", len(state.open_positions))

if __name__=="__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nshutdown requested")
