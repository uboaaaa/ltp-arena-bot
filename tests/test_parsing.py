from ai.parsing import extract_json_block, parse_llm_decision

CLEAN = '{"action": "FLAT", "confidence": 0.85, "reasoning": "choppy market"}'
FENCED = '```json\n{"action": "FLAT", "confidence": 0.5, "reasoning": "no edge"}\n```'
CHATTY = 'Here is my analysis:\n{"action": "LONG", "confidence": 0.6, "reasoning": "momentum"}\nGood luck!'

def test_cleaned_json_parses():
    d = parse_llm_decision(CLEAN)
    assert d == {"action": "FLAT", "confidence": 0.85, "reasoning": "choppy market"}

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