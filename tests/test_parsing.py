from ai.parsing import parse_llm_decision

CLEAN = '{"action": "FLAT", "confidence": 0.85, "reasoning": "choppy market"}'
FENCED = '```json\n{"action": "FLAT", "confidence": 0.5, "reasoning": "no edge"}\n```'
CHATTY = 'Here is my analysis:\n{"action": "LONG", "confidence": 0.6, "reasoning": "momentum"}\nGood luck!'

def test_cleaned_json_parses():
    d = parse_llm_decision(CLEAN)
    assert d == {"action": "FLAT", "confidence": 0.85, "reasoning": "choppy market", "catalyst": False}

def test_markdown_fenced_json_parse():
    assert parse_llm_decision(FENCED)["action"] == "FLAT"

def test_chatty_json_parse():
    assert parse_llm_decision(CHATTY)["action"] == "LONG"

def test_garbage_json_parse():
    assert parse_llm_decision("Sorryyy I cannot fulfill this request.") is None

def test_empty_returns_none():
    assert parse_llm_decision("") is None

def test_invalid_action_rejected():
    assert parse_llm_decision('{"action": "HODL", "confidence": 0.9, "reasoning": "foo"}') is None

def test_out_of_range_conf_rejected():
    assert parse_llm_decision('{"action": "SHORT", "confidence": 1.7, "reasoning": "foo"}') is None

def test_missing_reasoning_reject():
    assert parse_llm_decision('{"action": "SHORT", "confidence": 0.5}') is None

def test_extra_keys_stripped():
    d = parse_llm_decision('{"action": "FLAT", "confidence": 0.85, "reasoning": "choppy market", "leverage": 5}')
    assert "leverage" not in d

# catalyst tag

def test_catalyst_string_true_coerces():
    raw = '{"action": "FLAT", "confidence": 0.7, "reasoning": "x", "catalyst": "true"}'
    assert parse_llm_decision(raw)["catalyst"] is True

def test_catalyst_string_false_coerces():
    raw = '{"action": "FLAT", "confidence": 0.7, "reasoning": "x", "catalyst": "false"}'
    assert parse_llm_decision(raw)["catalyst"] is False

def test_catalyst_ambiguous_string_defaults_false():
    raw = '{"action": "FLAT", "confidence": 0.7, "reasoning": "x", "catalyst": "yes"}'
    assert parse_llm_decision(raw)["catalyst"] is False