""" Bot skeleton. Uses three event loops on one event loop via asyncio. 
Run using: python3 -m bot.main (from src/) """

import asyncio
import json
import logging

from ai.client import ask_llm
from ai.parsing import parse_llm_decision
from bot.config import (
    EXECUTION_ENABLED,
    SOFT_HALT_EQUITY,
    HARD_FLATTEN_EQUITY,
    HEARTBEAT_INTERVAL,
    RISK_INTERVAL,
    STRATEGY_INTERVAL,
    SYMBOL
)
from bot.state import BotState
from broker.rapidx import (
    get_equity, 
    get_open_positions,
    get_ticker
)

log = logging.getLogger("bot")

def setup_logging() -> None:
    fmt = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt)
    file_handler = logging.FileHandler("bot.log")
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
            log.warning("startup: ADOPTING %d existing open position(s): %s", len(positions), json.dumps(positions))
        log.info("startup complete: %s", state.summary())

    except Exception:
        log.exception("startup reconciliation failed. starting blind and retrying loops")
    
async def risk_monitor(state: BotState) -> None:
    while True:
        try:
            equity = await asyncio.to_thread(get_equity)
            state.update_equity(equity)
            positions = await asyncio.to_thread(get_open_positions)
            state.update_positions(positions)

            if equity < HARD_FLATTEN_EQUITY and not state.halted:
                state.halted = True
                state.halt_reason = f"equity {equity} < hard limit {HARD_FLATTEN_EQUITY}"
                log.critical("HARD LIMIT BREACHED: %s", state.halt_reason)
                if EXECUTION_ENABLED:
                    log.critical("flattening everything")
                    # TODO: cancel all orders and close all positions here
        except Exception as e:
            log.warning("risk cycle faild (%s) - equity age now %.0fs", e, state.equity_age())
            
        await asyncio.sleep(RISK_INTERVAL)

def build_prompt(ticker: dict, state: BotState) -> str:
    return f"""You are the decision engine of a crypto trading bot.

    Current market data for BTC perpetual:
    - last price : {ticker['lastPrice']}
    - 24hr change : {ticker['priceChangePercent']}%
    - 24hr high/low : {ticker['highPrice']} / {ticker['lowPrice']}

    Our account: equity {state.equity}, {len(state.open_positions)} open position(s). 
    RULES: We are eliminated if we ever lose 20% of the account. USE CAUTION!

    Reply with ONLY a JSON object, no other text:
    {{"action": "LONG" | "SHORT" | "FLAT", "confidence": 0.0-1.0, "reasoning": "one sentence"}}"""

async def strategy_loop(state: BotState) -> None:
    while True:
        try:
            if state.halted:
                log.info("strategy: halted (%s). observing only", state.halt_reason)
            else:
                ticker = await asyncio.to_thread(get_ticker, SYMBOL)
                prompt = build_prompt(ticker, state)
                raw = await asyncio.to_thread(ask_llm, prompt)
                decision = parse_llm_decision(raw)
                if decision is None:
                    log.warning("strategy: unparseable AI reply, skipping cycle: %r", raw)
                else:
                    state.update_decision(decision)
                    log.info("strategy: decision=%s   conf=%f   reason=%s", decision['action'], decision['confidence'], decision['reasoning'])
                    if EXECUTION_ENABLED:
                        log.info("strategy: execution happens here")
                        # TODO: execution logic here
                    else:
                        log.info("strategy: EXECUTION DISABLED - LOG ONLY")
        except Exception:
            log.exception("strategy cycle failed. will retry next interval!")
        
        await asyncio.sleep(STRATEGY_INTERVAL)

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
