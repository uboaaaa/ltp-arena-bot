""" Turn LLM replies into validated decision dicts. Every AI response passes through parse_llm_decision(). Usable decisions come back as dicts, else None"""

import json
from decimal import Decimal, InvalidOperation

from bot.config import (
    MIN_TP_PCT,
    MAX_TP_PCT,
    MIN_SL_PCT,
    MAX_SL_PCT,
    DEFAULT_TP_PCT,
    DEFAULT_SL_PCT
)

ALLOWED_ACTIONS = {"LONG", "SHORT", "FLAT"}

def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))

def _coerce_catalyst(value) -> bool:
    """ Model sometimes stringifies JSON scalars; accept the two unambiguous forms. """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text == "true":
            return True
        if text == "false":
            return False
    return False

def extract_json_block(raw: str) -> str | None:
    """ Pull the JSON object out of possibly-decorated model text """
    if not raw:
        return None 
    start = raw.find("{")
    end = raw.find("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return raw[start : end + 1]

def parse_llm_decision(raw: str) -> str | None:
    """ Extract, parse, and validate a trading decision from a model output """
    block = extract_json_block(raw)
    if block is None:
        return None
    
    try:
        decision = json.loads(block)
    except json.JSONDecodeError:
        return None
    
    if not isinstance(decision, dict):
        return None
    
    action = decision.get("action")
    confidence = decision.get("confidence")
    reasoning = decision.get("reasoning")
    catalyst = decision.get("catalyst")

    if action not in ALLOWED_ACTIONS:
        return None
    if not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
        return None
    if not isinstance(reasoning, str) or not reasoning.strip():
        return None
    result = {"action" : action, "confidence" : float(confidence), "reasoning" : reasoning,
              "catalyst" : _coerce_catalyst(catalyst)}
    
    if action != "FLAT":
        try:
            tp = Decimal(str(decision["take_profit_pct"]))
        except (KeyError, TypeError, InvalidOperation):
            tp = DEFAULT_TP_PCT
        try:
            sl = Decimal(str(decision["stop_loss_pct"]))
        except (KeyError, TypeError, InvalidOperation):
            sl = DEFAULT_SL_PCT
        result["take_profit_pct"] = _clamp(tp, MIN_TP_PCT, MAX_TP_PCT)
        result["stop_loss_pct"] = _clamp(sl, MIN_SL_PCT, MAX_SL_PCT)

    return result 