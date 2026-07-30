import time
from ai.prompt import (
    build_prompt,
    describe_stance,
    summarize_recent_5m
)

class FakeState:
    def __init__(self, open_positions=None, active_plan=None):
        self.open_positions = open_positions or []
        self.active_plan = active_plan

def test_flat_when_no_positions():
    assert describe_stance(FakeState()) == "flat"

def test_flat_when_only_zero_qty_rows():
    assert describe_stance(FakeState([{"positionQty": "0"}])) == "flat"

def test_long_reports_side_pnl_and_age():
    row = {"positionQty": "0.001", "avgPrice": "65000", "markPrice": "65130"}
    plan = {"opened_at": time.time() - 1800}
    text = describe_stance(FakeState([row], plan))
    assert "LONG" in text
    assert "+0.20%" in text
    assert "30 minutes" in text

def test_short_pnl_is_positive_when_winning():
    row = {"positionQty": "-0.001", "avgPrice": "65000", "markPrice": "64870"}
    text = describe_stance(FakeState([row]))
    assert "SHORT" in text
    assert "+0.20%" in text

def test_degrades_gracefully_on_missing_prices():
    text = describe_stance(FakeState([{"positionQty": "0.001"}]))
    assert "LONG" in text

def test_never_raises_on_garbage_row():
    text = describe_stance(FakeState([{"positionQty": "not-a-number"}]))
    assert text in ("flat", "holding a position")

# 5m klines 
def test_summarize_5m_computes_change():
    candles = [[0, "0", "0", "0", "64000", "0"], [0, "0", "0", "0", "64320", "0"]]
    text = summarize_recent_5m(candles)
    assert "last 60 min change +0.50%" in text
    assert "5-minute closes" in text

def test_summarize_5m_empty_degrades():
    assert "no recent 5-minute data" in summarize_recent_5m([])

def test_build_prompt_omits_5m_when_absent():
    ticker = {"lastPrice": "64500", "priceChangePercent": "-1.0",
              "lowPrice": "64000", "highPrice": "65000"}
    klines = [[0, "0", "0", "0", "64400", "0"], [0, "0", "0", "0", "64500", "0"]]
    five_m = [[0, "0", "0", "0", "64450", "0"], [0, "0", "0", "0", "64500", "0"]]
    with_5m = build_prompt(ticker, klines, [], [], FakeState(), klines_5m=five_m)
    without = build_prompt(ticker, klines, [], [], FakeState())
    assert "last 60 min change" in with_5m
    assert "last 60 min change" not in without