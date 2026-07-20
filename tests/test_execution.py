import time
from decimal import Decimal

from bot.config import SYMBOL
from bot.execution import (
    current_stance,
    decide_transition,
    conviction_multiplier,
    size_order,
    gate_check
)

# current stance checks

def test_stance_flat_when_empty():
    assert current_stance([]) == "FLAT"

def test_stance_long_on_positive_qty():
    assert current_stance([{"sym" : SYMBOL, "positionQty" : "0.001"}]) == "LONG"

def test_stance_short_on_negative_qty():
    assert current_stance([{"sym" : SYMBOL, "positionQty" : "-0.001"}]) == "SHORT"

def test_stance_flat_on_zero_qty():
    assert current_stance([{"sym" : SYMBOL, "positionQty" : 0}]) == "FLAT"

def test_stance_ignore_other_symbols():
    assert current_stance([{"sym": "BINANCE_PERP_ETH_USDT", "positionQty": "5"}]) == "FLAT"


# decide_transition checks

def test_transition_flat_flat_is_none():
    assert decide_transition("FLAT", "FLAT", 0.9) == "NONE"

def test_transition_matching_position_holds():
    assert decide_transition("LONG", "LONG", 0.9) == "HOLD"

def test_transition_flat_long_opens_long():
    assert decide_transition("FLAT", "LONG", 0.7) == "OPEN_LONG"

def test_transition_flat_short_opens_short():
    assert decide_transition("FLAT", "SHORT", 0.7) == "OPEN_SHORT"

def test_transition_long_flat_closes():
    assert decide_transition("LONG", "FLAT", 0.9) == "CLOSE"

def test_transition_reverse_only_on_high_conviction():
    assert decide_transition("LONG", "SHORT", 0.9) == "CLOSE_THEN_SHORT"

def test_transition_reversal_on_low_conviction_just_closes():
    assert decide_transition("LONG", "SHORT", 0.1) == "CLOSE"

def test_transition_short_to_long_reverses():
    assert decide_transition("SHORT", "LONG", 0.85) == "CLOSE_THEN_LONG"


# conviction mult

def test_conviction_below_floor_is_zero():
    assert conviction_multiplier(0.5) == Decimal("0")

def test_conviction_at_floor_is_half():
    assert conviction_multiplier(0.6) == Decimal("0.5")

def test_conviction_at_full_is_full():
    assert conviction_multiplier(0.8) == Decimal("1")

def test_conviction_above_full_is_full():
    assert conviction_multiplier(0.95) == Decimal("1")


# size order

def test_size_returns_none_without_conviction():
    assert size_order(Decimal("1000"), 0.5, Decimal("65000"), Decimal("0.001"), Decimal("50")) is None

def test_size_full_conviction_btc():
    # 1000 * 0.08 * 1.0 = 80 target
    # 80 / 65000 = 0.00123
    # snap up 0.00123 -> 0.002
    qty = size_order(Decimal("1000"), 0.9, Decimal("65000"), Decimal("0.001"), Decimal("50"))
    assert qty == Decimal("0.002")

def test_size_half_conviction_btc():
    # 1000 * 0.08 * 0.5 = 40 target
    # 40 / 65000 = 0.00062
    # snap up 0.00062 -> 0.001
    qty = size_order(Decimal("1000"), 0.7, Decimal("65000"), Decimal("0.001"), Decimal("50"))
    assert qty == Decimal("0.001")

def test_size_bump_up_to_min_notional():
    # target 40 < min_notional of 50. should bump up to 50, within cap
    qty = size_order(Decimal("1000"), 0.7, Decimal("1"), Decimal("1"), Decimal("50"))
    assert qty == Decimal("50")

def test_size_none_when_min_notional_exceeds_cap():
    # min_notional of 200 blows past the cap of 1000 * 0.08 * 1.5 = 120
    qty = size_order(Decimal("1000"), 0.7, Decimal("1"), Decimal("1"), Decimal("200"))
    assert qty is None


# gate check

class FakeState:
    """ Stripped-down version of BotState, used purely to test gate_check """
    def __init__(self, halted=False, halt_reason=None, equity=Decimal("1000"), equity_age=1.0, last_entry_at=0.0, last_write_at=0.0):
        self.halted = halted
        self.halt_reason = halt_reason
        self.equity = equity
        self.equity_age = equity_age
        self.last_entry_at = last_entry_at
        self.last_write_at = last_write_at
    

def test_gate_clear_when_all_ok():
    assert gate_check(FakeState(), "OPEN_LONG") == []

def test_gate_blocks_when_halted():
    reasons = gate_check(FakeState(halted=True, halt_reason="foo"), "OPEN_LONG")
    assert any("halted" in r for r in reasons)

def test_gate_blocks_on_stale_equity():
    reasons = gate_check(FakeState(equity_age=99), "OPEN_LONG")
    assert any("stale" in r for r in reasons)

def test_gate_soft_halt_blocks_opening():
    reasons = gate_check(FakeState(equity=Decimal("900")), "OPEN_LONG")
    assert any("soft halt" in r for r in reasons)

def test_gate_soft_halt_still_allows_closing():
    reasons = gate_check(FakeState(equity=Decimal("900")), "CLOSE") == []

def test_gate_blocks_reentry_within_min_hold():
    reasons = gate_check(FakeState(last_entry_at=time.time()), "OPEN_LONG")
    assert any("min hold" for r in reasons)

def test_gate_enforces_write_spacing():
    reasons = gate_check(FakeState(last_write_at=time.time()), "CLOSE")
    assert any("write spacing" for r in reasons)