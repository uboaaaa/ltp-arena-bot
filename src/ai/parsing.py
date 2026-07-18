""" Turn LLM replies into validated decision dicts. Every AI response passes through parse_llm_decision(). Usable decisions come back as dicts, else None"""

import json 

ALLOWED_ACTIONS = {"LONG", "SHORT", "FLAT"}

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

    if action not in ALLOWED_ACTIONS:
        return None
    if not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
        return None
    if not isinstance(reasoning, str) or not reasoning.strip():
        return None
    
    return {"action" : action, "confidence" : float(confidence), "reasoning" : reasoning}