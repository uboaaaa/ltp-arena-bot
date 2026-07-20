"""
Converts LLM decisions into orders. All functions here are either logic or orchestration-related vis-a-vis the broker. The model itself never handles orders directly.
main.py calls execute_decision via asyncio.to_thread
"""

import json
import logging
import time
from decimal import Decimal

from bot.config import (
    BASE_POSITION_FRACTION,
    CONF_FLOOR,
    CONF_FULL,
    MAX_EQUITY_AGE,
    MIN_HOLD_SECONDS,
    SOFT_HALT_EQUITY,
    SYMBOL,
    WRITE_SPACING
)

from broker.rapidx import (
    get_symbol_info,
    get_ticker,
    new_client_order_id,
    place_order,
    query_order,
    close_position,
    snap_down,
    snap_up
)

log = logging.getLogger("bot.execution")

TERMINAL_STATES = ("FILLED", "CANCELLED", "REJECTED", "EXPIRED")

# --- logic ---
def current_stance(open_positions: list) -> str:
    """ 'LONG', 'SHORT', or 'FLAT' from live position rows (NET mode: signed qty). """
    for row in open_positions:
        if row.get("sym") == SYMBOL:
            qty = Decimal(str(row.get("positionQty", "0")))
            if qty > 0:
                return "LONG"
            if qty < 0:
                return "SHORT"
    return "FLAT"

def decide_transition(stance: str, action: str, confidence: float) -> str:
    """ Returns one of: (OPEN_LONG, OPEN_SHORT, CLOSE, CLOSE_THEN_SHORT, CLOSE_THEN_LONG, HOLD, NONE) """
    if action == stance:
        return "HOLD" if stance != "FLAT" else "NONE"
    if stance == "FLAT":
        return {"LONG": "OPEN_LONG", "SHORT": "OPEN_SHORT"}[action]
    if action == "FLAT": # if we hold a position and the advice differs, close it
        return "CLOSE"
    reverse = "CLOSE_THEN_SHORT" if action == "SHORT" else "CLOSE_THEN_LONG" # reverse on high conviction, otherwise just get flat
    return reverse if confidence >= CONF_FULL else "CLOSE"

def conviction_multiplier(confidence: float) -> Decimal:
    """ if less than floor, return 0 (i.e., do not trade). if between floor and full, return half mult. if beyond full, return full mult. """
    if confidence < CONF_FLOOR:
        return Decimal("0")
    if confidence < CONF_FULL:
        return Decimal("0.5")
    return Decimal("1")

def size_order(equity: Decimal, confidence: float, price: Decimal, lot: Decimal, min_notional: Decimal) -> Decimal | None:
    """ Quantity for a new position. Return none if quantity is small or we have no conviction """
    mult = conviction_multiplier(confidence)
    if mult == 0:
        return None
    target_notional = equity * BASE_POSITION_FRACTION * mult
    qty = snap_up(target_notional / price, lot)
    if qty * price < min_notional:
        qty = snap_up(min_notional / price, lot) # bump up to venue minimum
        if qty * price > equity * BASE_POSITION_FRACTION * Decimal("1.5"):
            return None # if we blow past our cap, do NOT trade
    return qty

def gate_check(state, transition: str) -> list[str]:
    """ Return a list of possible failure reasons. If no failure list, we're good to trade """
    reasons = []
    if state.halted:
        reasons.append(f"halted: {state.halt_reason}")
    if state.equity is None or state.equity_age > MAX_EQUITY_AGE:
        reasons.append(f"equity stale. age: ({state.equity_age:.0f}s)")
    elif state.equity < SOFT_HALT_EQUITY and transition.startswith(("OPEN", "CLOSE_THEN")):
        reasons.append(f"equity {state.equity} is below soft halt threshold {SOFT_HALT_EQUITY}")
    
    if transition.startswith(("OPEN", "CLOSE_THEN")):
        held = time.time() - state.last_entry_at
        if state.last_entry_at and held < MIN_HOLD_SECONDS:
            reasons.append(f"min hold: entered {held:.0f}s ago")
    since_write = time.time() - state.last_write_at
    if state.last_write_at and since_write < WRITE_SPACING:
        reasons.append(f"write spacing: last write {since_write:.1f}s ago")
    
    return reasons

# --- orchestration (run via to_thread)---
def _wait_terminal(client_order_id: str, tries: int=10) -> dict:
    for _ in range(tries):
        time.sleep(2)
        order_state = query_order(client_order_id)["data"]
        if order_state.get("orderState") in TERMINAL_STATES:
            return order_state
    return order_state

def _open(side: str, qty: Decimal, price_cap: Decimal, state) -> dict:
    order = {
        "symbol" : SYMBOL,
        "side" : side,
        "positionSide" : "LONG" if side == "BUY" else "SHORT",
        "orderType" : "LIMIT",
        "price" : str(price_cap),
        "quantity" : str(qty),
        "maxNotional" : str(price_cap * qty),
        "clientOrderId" : new_client_order_id("live"),
    }
    log.info("EXECUTE open %s: %s", side, json.dumps(order))
    place_order(order)
    state.last_write_at = time.time()
    result = _wait_terminal(order["clientOrderId"])
    if result.get("orderState") == "FILLED":
        state.last_entry_at = time.time()
    log.info("EXECUTE result: state=%s  filled=%s  avg=%s", result.get("orderState"), result.get("executedQty"), result.get("executedAvgPrice"))
    return result

def execute_decision(state, decision: dict) -> dict:
    """ FULL PIPELINE: stance -> transition -> gate -> orders.
    Retuns summary dict for reasoning logs """
    summary = {"decision" : decision, "transition" : None, "gate" : [], "orders" : []}
    stance = current_stance(state.open_positions)
    transition = decide_transition(stance, decision["action"], decision["confidence"])
    summary["transition"] = f"{stance} -> {transition}"
    log.info("EXECUTE transition: %s (conf %.2f)", summary["transition"], decision["confidence"])
    if transition in ("NONE", "HOLD"):
        return summary
    
    reasons = gate_check(state, transition)
    summary["gate"] = reasons
    if reasons:
        log.info("EXECUTE gated: %s", "; ".join(reasons))
        return summary
    
    info = get_symbol_info(SYMBOL)
    tick = Decimal(str(info["tickSize"]))
    lot = Decimal(str(info["lotSize"]))
    min_notional = Decimal(str(info["minNotional"]))
    last = Decimal(str(get_ticker(SYMBOL)["lastPrice"]))

    if transition in ("CLOSE", "CLOSE_THEN_LONG", "CLOSE_THEN_SHORT"):
        cap = str(state.equity or Decimal("1000"))
        log.info("EXECUTE close position (maxNotional cap %s)", cap)
        summary["orders"].append({
            "type" : "close",
            "result" : close_position(SYMBOL, cap)
        })
        state.last_write_at = time.time()
        time.sleep(WRITE_SPACING)
    
    if transition in ("OPEN_LONG", "CLOSE_THEN_LONG", "OPEN_SHORT", "CLOSE_THEN_SHORT"):
        qty = size_order(state.equity, decision["confidence"], last, lot, min_notional)
        if qty is None:
            summary["gate"].append("sizing returned None (low conviction or min-notional conflict)")
            log.info("EXECUTE skipped: %s", summary["gate"][-1])
            return summary
        if transition.endswith("LONG"):
            cap = snap_down(last * Decimal("1.002"), tick)
            summary["orders"].append({
                "type" : "open_long",
                "result" : _open("BUY", qty, cap, state)
            })
        else:
            cap = snap_up(last * Decimal("0.998"), tick)
            summary["orders"].append({
                "type" : "open_short",
                "result" : _open("SELL", qty, cap, state)
            })

    return summary
