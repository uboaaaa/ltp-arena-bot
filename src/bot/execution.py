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
    DEFAULT_SL_PCT,
    DEFAULT_TP_PCT,
    MAX_EQUITY_AGE,
    MAX_POSITION_AGE_SECONDS,
    MIN_HOLD_SECONDS,
    REQUIRE_CONFIRMATION,
    SOFT_HALT_EQUITY,
    SYMBOL,
    WRITE_SPACING,
    VOL_SL_MULT,
    VOL_TP_MULT,
    STOP_COOLDOWN_SECONDS,
    CHOP_THRESHOLD_PCT,
    CHOP_CONF_FLOOR,
    MIN_TP_PCT,
    MAX_TP_PCT,
    MIN_SL_PCT,
    MAX_SL_PCT
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
    """ When a position is open, bracket owns the exit. Only strong opposite signal overrides it, and all weak disagreements are ignored as noise """
    if stance == "FLAT":
        if action == "FLAT":
            return "NONE"
        return "OPEN_LONG" if action == "LONG" else "OPEN_SHORT"
    if action == stance:
        return "HOLD"
    if action != "FLAT" and confidence >= CONF_FULL:
        return "CLOSE_THEN_SHORT" if action =="SHORT" else "CLOSE_THEN_LONG"
    return "HOLD"

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
        since_stop = time.time() - state.last_stop_at
        if state.last_stop_at and since_stop < STOP_COOLDOWN_SECONDS:
            reasons.append(f"stop cooldown: stopped out {since_stop:.0f}s ago")

    since_write = time.time() - state.last_write_at
    if state.last_write_at and since_write < WRITE_SPACING:
        reasons.append(f"write spacing: last write {since_write:.1f}s ago")
    
    return reasons

def check_bracket(state) -> tuple[str, Decimal] | None:
    """ Return (trigger, pnl_pct) if the open position has hit its plan """
    rows = [r for r in state.open_positions if r.get('sym') == SYMBOL]
    if not rows:
        return None
    row = rows[0]
    qty = Decimal(str(row.get("positionQty", "0")))
    avg = Decimal(str(row.get("avgPrice", "0")))
    mark = Decimal(str(row.get("markPrice", "0")))
    if qty == 0 or avg <= 0 or mark <= 0:
        return None
    
    direction = Decimal("1") if qty > 0 else Decimal("-1")
    pnl_pct = (mark - avg) / avg * Decimal("100") * direction

    plan = state.active_plan or {}
    tp = plan.get("tp_pct", DEFAULT_TP_PCT)
    sl = plan.get("sl_pct", DEFAULT_SL_PCT)
    opened_at = plan.get("opened_at", 0.0)

    if pnl_pct >= tp:
        return ("take_profit", pnl_pct)
    if pnl_pct <= -sl:
        return ("stop_loss", pnl_pct)
    if opened_at and time.time() - opened_at > MAX_POSITION_AGE_SECONDS:
        return ("max_age", pnl_pct)
    
    return None

def avg_hourly_range_pct(klines_response) -> Decimal | None:
    """ Avg high-low span per candle, as a % of price """ 
    candles = klines_response.get("candles", []) if isinstance(klines_response, dict) else klines_response
    if not candles:
        return None
    ranges = [(Decimal(str(c[2])) - Decimal(str(c[3]))) / Decimal(str(c[4])) * 100 for c in candles]
    return sum(ranges) / len(ranges)

def change_12h_pct(klines_response) -> Decimal | None:
    """ Signed close-to-close change within the fetched window """
    candles = klines_response.get("candles", []) if isinstance(klines_response, dict) else klines_response
    if len(candles) < 2:
        return None
    first, last = Decimal(str(candles[0][4])), Decimal(str(candles[-1][4]))
    return ((last - first) / first) * 100

def derive_brackets(vol_pct, model_tp: Decimal, model_sl: Decimal) -> tuple[Decimal, Decimal]:
    """ Geomnetry from measured volatility. Model values only if no data """
    if not vol_pct or vol_pct <= 0:
        return model_tp, model_sl
    tp = min(max(vol_pct * VOL_TP_MULT, MIN_TP_PCT), MAX_TP_PCT)
    sl = min(max(vol_pct * VOL_SL_MULT, MIN_SL_PCT), MAX_SL_PCT)
    return tp, sl

# --- orchestration (run via to_thread)---
def _wait_terminal(client_order_id: str, tries: int=10) -> dict:
    for _ in range(tries):
        time.sleep(2)
        order_state = query_order(client_order_id)["data"]
        if order_state.get("orderState") in TERMINAL_STATES:
            return order_state
    return order_state

def _open(side, qty, price_cap, state, decision, decision_id) -> dict:
    order = {
        "symbol" : SYMBOL,
        "side" : side,
        "positionSide" : "LONG" if side == "BUY" else "SHORT",
        "orderType" : "LIMIT",
        "price" : str(price_cap),
        "quantity" : str(qty),
        "maxNotional" : str((price_cap * qty * Decimal("1.05")).quantize(Decimal("0.01"))),
        "clientOrderId" : new_client_order_id("live"),
    }
    log.info("EXECUTE open %s: %s", side, json.dumps(order))
    place_order(order)
    state.last_write_at = time.time()
    result = _wait_terminal(order["clientOrderId"])
    if result.get("orderState") == "FILLED":
        state.last_entry_at = time.time()
        state.set_plan({
            "tp_pct" : decision["take_profit_pct"],
            "sl_pct" : decision["stop_loss_pct"],
            "decision_id" : decision_id,
            "opened_at" : time.time(),
            "side" : "LONG" if side=="BUY" else "SHORT",
        })
    log.info("EXECUTE result: state=%s  filled=%s  avg=%s", result.get("orderState"), result.get("executedQty"), result.get("executedAvgPrice"))
    return result

def execute_decision(state, decision: dict, decision_id, vol_pct=None, chg_12h=None) -> dict:
    """ FULL PIPELINE: stance -> transition -> gate -> orders.
    Retuns summary dict for reasoning logs """
    summary = {"decision" : decision, "transition" : None, "gate" : [], "orders" : []}
    stance = current_stance(state.open_positions)
    transition = decide_transition(stance, decision["action"], decision["confidence"])
    summary["transition"] = f"{stance} -> {transition}"
    log.info("EXECUTE transition: %s (conf %.2f)", summary["transition"], decision["confidence"])

    if transition in ("NONE", "HOLD"):
        return summary
    
    if transition.startswith(("OPEN", "CLOSE_THEN")) and chg_12h is not None:
        if abs(chg_12h) < CHOP_THRESHOLD_PCT and decision["confidence"] < CHOP_CONF_FLOOR:
            reason = (f"chop backstop: |12h change| {abs(chg_12h):.2f}% < "
                      f"{CHOP_THRESHOLD_PCT}% and conf {decision['confidence']:.2f} < {CHOP_CONF_FLOOR}")
            summary['gate'] = [reason]
            log.info("EXECUTE gated: %s", reason)
            return summary

    proposed = decision["action"]
    if transition.startswith(("OPEN", "CLOSE_THEN")) and REQUIRE_CONFIRMATION:
        if state.pending_signal != proposed:
            state.pending_signal = proposed
            reason = f"awaiting confirmation: {proposed} seen once, need two consecutive"
            summary["gate"] = [reason]
            log.info("EXECUTE debounced: %s", reason)
            return summary
            
    state.pending_signal = proposed
    
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
        state.set_plan(None)
        state.last_write_at = time.time()
        time.sleep(WRITE_SPACING)

    eff_tp, eff_sl = derive_brackets(vol_pct, decision["take_profit_pct"], decision["stop_loss_pct"])
    if (eff_tp, eff_sl) != (decision["take_profit_pct"], decision["stop_loss_pct"]):
        log.info("EXECUTE brackets: model %s/%s -> volatility-derived %s/%s", decision["take_profit_pct"], decision["stop_loss_pct"], eff_tp, eff_sl)
    decision = {**decision, "take_profit_pct" : eff_tp, "stop_loss_pct" : eff_sl}
    summary["effective_brackets"] = {"tp" : str(eff_tp), "sl" : str(eff_sl)} 
    
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
                "result" : _open("BUY", qty, cap, state, decision, decision_id)
            })
        else:
            cap = snap_up(last * Decimal("0.998"), tick)
            summary["orders"].append({
                "type" : "open_short",
                "result" : _open("SELL", qty, cap, state, decision, decision_id)
            })

    return summary
