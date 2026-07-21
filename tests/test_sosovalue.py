import time

from feeds.sosovalue import clean_text, _symbols_of, _format


# clean_text

def test_clean_text_strips_html_tags():
    assert clean_text('<span style="color:#F00">Bitcoin</span> up 5%') == "Bitcoin up 5%"

def test_clean_text_strips_br_and_img():
    assert clean_text('News here<br><img src="x.jpg">') == "News here"

def test_clean_text_unescapes_entities():
    assert clean_text("AT&amp;T files &lt;doc&gt;") == "AT&T files <doc>"

def test_clean_text_collapses_whitespace():
    assert clean_text("too    many\n\n spaces") == "too many spaces"

def test_clean_text_empty():
    assert clean_text("") == ""
    assert clean_text(None) == ""


# _symbols_of

def test_symbols_uppercased():
    item = {"matched_currencies": [{"symbol": "btc"}, {"symbol": "Eth"}]}
    assert _symbols_of(item) == ["BTC", "ETH"]

def test_symbols_missing_key():
    assert _symbols_of({}) == []

def test_symbols_null_list():
    assert _symbols_of({"matched_currencies": None}) == []

def test_symbols_plain_strings():
    # tolerate the currency list being bare strings rather than dicts
    assert _symbols_of({"matched_currencies": ["btc", "sol"]}) == ["BTC", "SOL"]


# _format

def test_format_uses_title_with_tag_and_age():
    now = int(time.time() * 1000)
    item = {"title": "Bitcoin breaks out",
            "release_time": now - 30 * 60_000,
            "matched_currencies": [{"symbol": "btc"}]}
    line = _format(item, now)
    assert line.startswith("30m ago [BTC]: Bitcoin breaks out")

def test_format_falls_back_to_content_when_no_title():
    now = int(time.time() * 1000)
    item = {"title": "", "content": "<p>Some body text</p>", "release_time": now}
    line = _format(item, now)
    assert "Some body text" in line

def test_format_returns_none_when_no_text():
    now = int(time.time() * 1000)
    assert _format({"title": "", "content": ""}, now) is None

def test_format_handles_bad_release_time():
    now = int(time.time() * 1000)
    line = _format({"title": "x", "release_time": "not-a-number"}, now)
    assert line.startswith("0m ago")

def test_format_no_currencies_has_no_tag():
    now = int(time.time() * 1000)
    line = _format({"title": "Macro news", "release_time": now}, now)
    assert "[" not in line
