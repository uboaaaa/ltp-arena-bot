import time
from decimal import Decimal

from bot.config import (
    SYMBOL, 
    MAX_POSITION_AGE_SECONDS,
)

from bot.execution import (
    current_stance,
    decide_transition,
    conviction_multiplier,
    size_order,
    gate_check,
    check_bracket,
    execute_decision,
    derive_brackets,
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
# NOTE: policy changed - once a position is open its bracket owns the exit,
# so weak disagreement is now HOLD rather than CLOSE.

def test_transition_flat_flat_is_none():
    assert decide_transition("FLAT", "FLAT", 0.9) == "NONE"

def test_transition_matching_position_holds():
    assert decide_transition("LONG", "LONG", 0.9) == "HOLD"

def test_transition_flat_long_opens_long():
    assert decide_transition("FLAT", "LONG", 0.7) == "OPEN_LONG"

def test_transition_flat_short_opens_short():
    assert decide_transition("FLAT", "SHORT", 0.7) == "OPEN_SHORT"

def test_transition_flat_advice_while_holding_lets_bracket_work():
    assert decide_transition("LONG", "FLAT", 0.9) == "HOLD"

def test_transition_reverse_only_on_high_conviction():
    assert decide_transition("LONG", "SHORT", 0.9) == "CLOSE_THEN_SHORT"

def test_transition_weak_opposite_signal_is_ignored():
    assert decide_transition("LONG", "SHORT", 0.1) == "HOLD"

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
    # 1000 * 0.25 * 1.0 = 250 target
    # 250 / 65000 = 0.00384 -> snap up to 0.004
    qty = size_order(Decimal("1000"), 0.9, Decimal("65000"), Decimal("0.001"), Decimal("50"))
    assert qty == Decimal("0.004")

def test_size_half_conviction_btc():
    # 1000 * 0.25 * 0.5 = 125 target
    # 125 / 65000 = 0.00192 -> snap up to 0.002
    qty = size_order(Decimal("1000"), 0.7, Decimal("65000"), Decimal("0.001"), Decimal("50"))
    assert qty == Decimal("0.002")

def test_size_bump_up_to_min_notional(monkeypatch):
    # mechanism test at the original 0.08 fraction: target 40 < min_notional 50,
    # should bump up to 50, within the 1.5x cap
    import bot.execution as exmod
    monkeypatch.setattr(exmod, "BASE_POSITION_FRACTION", Decimal("0.08"))
    qty = size_order(Decimal("1000"), 0.7, Decimal("1"), Decimal("1"), Decimal("50"))
    assert qty == Decimal("50")

def test_size_none_when_min_notional_exceeds_cap(monkeypatch):
    # mechanism test at the original 0.08 fraction: min_notional 200 blows past
    # the cap of 1000 * 0.08 * 1.5 = 120 -> refuse to trade
    import bot.execution as exmod
    monkeypatch.setattr(exmod, "BASE_POSITION_FRACTION", Decimal("0.08"))
    qty = size_order(Decimal("1000"), 0.7, Decimal("1"), Decimal("1"), Decimal("200"))
    assert qty is None


# shared fake state

class FakeState:
    """ Stripped-down version of BotState for testing pure logic. """
    def __init__(self, halted=False, halt_reason=None, equity=Decimal("1000"),
                 equity_age=1.0, last_entry_at=0.0, last_write_at=0.0,
                 open_positions=None, active_plan=None, pending_signal=None, last_stop_at=0.0):
        self.halted = halted
        self.halt_reason = halt_reason
        self.equity = equity
        self.equity_age = equity_age
        self.last_entry_at = last_entry_at
        self.last_write_at = last_write_at
        self.open_positions = open_positions or []
        self.active_plan = active_plan
        self.pending_signal = pending_signal
        self.last_stop_at = last_stop_at


# gate check

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
    assert gate_check(FakeState(equity=Decimal("900")), "CLOSE") == []

def test_gate_blocks_reentry_within_min_hold():
    reasons = gate_check(FakeState(last_entry_at=time.time()), "OPEN_LONG")
    assert any("min hold" in r for r in reasons)

def test_gate_enforces_write_spacing():
    reasons = gate_check(FakeState(last_write_at=time.time()), "CLOSE")
    assert any("write spacing" in r for r in reasons)


# bracket checks
# plan: take profit at +0.6%, stop out at -0.4%

def _position(qty, avg, mark):
    return {"sym": SYMBOL, "positionQty": str(qty),
            "avgPrice": str(avg), "markPrice": str(mark)}

def _plan(opened_at=None):
    return {"tp_pct": Decimal("0.6"), "sl_pct": Decimal("0.4"),
            "decision_id": "d-test",
            "opened_at": opened_at if opened_at is not None else time.time()}

def test_bracket_none_when_flat():
    assert check_bracket(FakeState()) is None

def test_bracket_ignores_zero_qty_row():
    state = FakeState(open_positions=[_position("0", 65000, 66000)], active_plan=_plan())
    assert check_bracket(state) is None

def test_bracket_quiet_inside_the_range():
    # long from 65000, mark 65100 = +0.15%, inside both levels
    state = FakeState(open_positions=[_position("0.001", 65000, 65100)], active_plan=_plan())
    assert check_bracket(state) is None

def test_bracket_take_profit_on_long():
    # long from 65000, mark 65403 = +0.62% >= tp 0.6
    state = FakeState(open_positions=[_position("0.001", 65000, 65403)], active_plan=_plan())
    trigger, pnl_pct = check_bracket(state)
    assert trigger == "take_profit"
    assert pnl_pct > 0

def test_bracket_stop_loss_on_long():
    # long from 65000, mark 64700 = -0.46% <= -sl 0.4
    state = FakeState(open_positions=[_position("0.001", 65000, 64700)], active_plan=_plan())
    trigger, pnl_pct = check_bracket(state)
    assert trigger == "stop_loss"
    assert pnl_pct < 0

def test_bracket_take_profit_on_short():
    # SHORT from 65000, price FELL to 64600 -> the short is UP 0.62%
    state = FakeState(open_positions=[_position("-0.001", 65000, 64600)], active_plan=_plan())
    trigger, pnl_pct = check_bracket(state)
    assert trigger == "take_profit"
    assert pnl_pct > 0

def test_bracket_stop_loss_on_short():
    # SHORT from 65000, price ROSE to 65300 -> the short is DOWN 0.46%
    state = FakeState(open_positions=[_position("-0.001", 65000, 65300)], active_plan=_plan())
    trigger, pnl_pct = check_bracket(state)
    assert trigger == "stop_loss"
    assert pnl_pct < 0

def test_bracket_max_age_closes_a_quiet_position():
    old = _plan(opened_at=time.time() - (MAX_POSITION_AGE_SECONDS + 10))
    state = FakeState(open_positions=[_position("0.001", 65000, 65050)], active_plan=old)
    trigger, _ = check_bracket(state)
    assert trigger == "max_age"


# debounce
# these only exercise paths that return before any network call

DECISION = {"action": "LONG", "confidence": 0.7, "reasoning": "test",
            "take_profit_pct": Decimal("0.6"), "stop_loss_pct": Decimal("0.4")}

def test_debounce_first_signal_does_not_trade(monkeypatch):
    import bot.execution as ex
    monkeypatch.setattr(ex, "REQUIRE_CONFIRMATION", True)
    state = FakeState()
    summary = execute_decision(state, DECISION, "d-1")
    assert any("awaiting confirmation" in r for r in summary["gate"])
    assert summary["orders"] == []
    assert state.pending_signal == "LONG"

def test_debounce_second_matching_signal_clears_confirmation(monkeypatch):
    import bot.execution as ex
    monkeypatch.setattr(ex, "REQUIRE_CONFIRMATION", True)
    # halted so it stops at the risk gate instead of reaching the network
    state = FakeState(pending_signal="LONG", halted=True, halt_reason="test")
    summary = execute_decision(state, DECISION, "d-2")
    assert not any("awaiting confirmation" in r for r in summary["gate"])
    assert any("halted" in r for r in summary["gate"])

def test_debounce_opposite_signal_resets_the_pending_one(monkeypatch):
    import bot.execution as ex
    monkeypatch.setattr(ex, "REQUIRE_CONFIRMATION", True)
    state = FakeState(pending_signal="LONG")
    summary = execute_decision(state, dict(DECISION, action="SHORT"), "d-3")
    assert any("awaiting confirmation" in r for r in summary["gate"])
    assert state.pending_signal == "SHORT"


# volatility checks

def test_derived_brackets_from_volatility():
    tp, sl = derive_brackets(Decimal("0.5"), Decimal("0.6"), Decimal("0.4"))
    assert tp == Decimal("0.3")    # 0.5 * 0.6
    assert sl == Decimal("0.35")   # 0.5 * 0.7

def test_derived_brackets_fall_back_without_vol():
    assert derive_brackets(None, Decimal("0.6"), Decimal("0.4")) == (Decimal("0.6"), Decimal("0.4"))

def test_gate_blocks_entries_during_stop_cooldown():
    import time
    reasons = gate_check(FakeState(last_stop_at=time.time()), "OPEN_LONG")
    assert any("stop cooldown" in r for r in reasons)

def test_chop_backstop_gates_low_conviction():
    d = dict(DECISION, confidence=0.65)
    summary = execute_decision(FakeState(), d, "d-chop",
                               vol_pct=Decimal("0.5"), chg_12h=Decimal("0.3"))
    assert any("chop backstop" in r for r in summary["gate"])

def test_chop_backstop_gates_everything_in_trend_only_mode():
    # trend-only pivot 2026-08-01: CHOP_CONF_FLOOR is 1.01, so NO confidence
    # passes in a rangebound regime - even a 0.9-conviction call is refused
    d = dict(DECISION, confidence=0.9)
    summary = execute_decision(FakeState(), d, "d-chop2",
                               vol_pct=Decimal("0.5"), chg_12h=Decimal("0.3"))
    assert any("chop backstop" in r for r in summary["gate"])

def test_chop_backstop_mechanism_allows_conf_above_floor(monkeypatch):
    # the mechanism itself, tested at a reachable floor
    import bot.execution as exmod
    monkeypatch.setattr(exmod, "CHOP_CONF_FLOOR", 0.7)
    d = dict(DECISION, confidence=0.75)
    summary = execute_decision(FakeState(halted=True, halt_reason="test"), d, "d-chop3",
                               vol_pct=Decimal("0.5"), chg_12h=Decimal("0.3"))
    assert not any("chop backstop" in r for r in summary["gate"])