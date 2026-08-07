"""End-to-end dry run of the LIVE trade path with mocked broker calls.

Exercises: chop backstop pass-through, gates, derive_brackets override,
sizing, _open (place -> poll -> fill -> set_plan), and the bracket close
trigger - the exact code that runs at 3am. No network, no real orders.
"""


from decimal import Decimal
import pytest
import bot.execution as ex
import bot.state as state_mod


def _mk_state(tmp_path, monkeypatch):
    monkeypatch.setattr(state_mod, "PLAN_PATH", str(tmp_path / "plan.json"))
    s = state_mod.BotState()
    s.update_equity(Decimal("1000"))
    s.update_positions([])
    return s


def _mock_broker(monkeypatch, fill_side):
    calls = {"placed": [], "queries": 0}

    monkeypatch.setattr(ex, "get_symbol_info", lambda sym: {
        "tickSize": "0.10", "lotSize": "0.001", "minNotional": "50"})
    monkeypatch.setattr(ex, "get_ticker", lambda sym: {"lastPrice": "66000.00"})

    def fake_place(order):
        calls["placed"].append(order)
        return {"orderId": "1", "clientOrderId": order["clientOrderId"]}
    monkeypatch.setattr(ex, "place_order", fake_place)

    def fake_query(coid):
        calls["queries"] += 1
        return {"data": {"orderState": "FILLED", "executedQty": "0.001",
                         "executedAvgPrice": "66005.0", "clientOrderId": coid}}
    monkeypatch.setattr(ex, "query_order", fake_query)
    monkeypatch.setattr(ex.time, "sleep", lambda s: None)   # no real waiting
    return calls


DECISION_LONG = {"action": "LONG", "confidence": 0.72, "reasoning": "dry run",
                 "take_profit_pct": Decimal("0.6"), "stop_loss_pct": Decimal("0.4")}


def test_full_open_path_long(tmp_path, monkeypatch):
    state = _mk_state(tmp_path, monkeypatch)
    calls = _mock_broker(monkeypatch, "BUY")
    summary = ex.execute_decision(state, dict(DECISION_LONG), "d-dry-1",
                                  vol_pct=Decimal("0.5"), chg_12h=Decimal("1.2"))
    # a real order was "placed" with sane fields
    assert len(calls["placed"]) == 1
    order = calls["placed"][0]
    assert order["side"] == "BUY"
    assert Decimal(order["quantity"]) >= Decimal("0.001")
    assert Decimal(order["price"]) > Decimal("66000")      # marketable buy cap
    # volatility-derived brackets overrode the model's 0.6/0.4
    eb = summary["effective_brackets"]
    assert Decimal(eb["tp"]) == Decimal("0.3")             # 0.5 * 0.6
    assert Decimal(eb["sl"]) == Decimal("0.35")            # 0.5 * 0.7
    # plan persisted with the EFFECTIVE brackets and decision id
    assert state.active_plan["decision_id"] == "d-dry-1"
    assert state.active_plan["tp_pct"] == Decimal("0.3")
    assert state.active_plan["side"] == "LONG"
    assert state.last_entry_at > 0
    fresh = state_mod.BotState()
    fresh.load_plan()
    assert fresh.active_plan["decision_id"] == "d-dry-1"   # survived "restart"


def test_full_open_path_short(tmp_path, monkeypatch):
    state = _mk_state(tmp_path, monkeypatch)
    calls = _mock_broker(monkeypatch, "SELL")
    decision = dict(DECISION_LONG, action="SHORT")
    ex.execute_decision(state, decision, "d-dry-2",
                        vol_pct=Decimal("0.5"), chg_12h=Decimal("-1.2"))
    order = calls["placed"][0]
    assert order["side"] == "SELL"
    assert order["positionSide"] == "SHORT"
    assert Decimal(order["price"]) < Decimal("66000")      # marketable sell floor
    assert state.active_plan["side"] == "SHORT"


def test_bracket_fires_on_the_position_we_just_opened(tmp_path, monkeypatch):
    state = _mk_state(tmp_path, monkeypatch)
    _mock_broker(monkeypatch, "BUY")
    ex.execute_decision(state, dict(DECISION_LONG), "d-dry-3",
                        vol_pct=Decimal("0.5"), chg_12h=Decimal("1.2"))
    # simulate the risk monitor's view: position exists, price ran to target
    state.update_positions([{
        "sym": ex.SYMBOL, "positionQty": "0.001",
        "avgPrice": "66005.0", "markPrice": "66280.0"}])   # +0.416% >= tp 0.4
    trigger = ex.check_bracket(state)
    assert trigger is not None
    reason, pnl = trigger
    assert reason == "take_profit"
    assert pnl > Decimal("0.4")


def test_chop_backstop_still_blocks_weak_entries(tmp_path, monkeypatch):
    state = _mk_state(tmp_path, monkeypatch)
    calls = _mock_broker(monkeypatch, "BUY")
    weak = dict(DECISION_LONG, confidence=0.62)
    summary = ex.execute_decision(state, weak, "d-dry-4",
                                  vol_pct=Decimal("0.5"), chg_12h=Decimal("0.3"))
    assert calls["placed"] == []                            # nothing traded
    assert any("chop backstop" in g for g in summary["gate"])


# handle_bracket_exit() tests

def _mk_plan_state(tmp_path, monkeypatch):
    s = _mk_state(tmp_path, monkeypatch)
    s.set_plan({"tp_pct": Decimal("0.4"), "sl_pct": Decimal("0.35"),
                "decision_id": "d-test-1", "opened_at": 123.0, "side": "LONG"})
    return s


def test_bracket_exit_take_profit_happy_path(tmp_path, monkeypatch):
    state = _mk_plan_state(tmp_path, monkeypatch)
    closed, records = [], []
    monkeypatch.setattr(ex, "close_position", lambda sym, mn: closed.append(sym) or {"ok": True})
    monkeypatch.setattr(ex.journal, "record", records.append)
    ex.handle_bracket_exit(state, ("take_profit", Decimal("0.41")))
    assert closed == ["BINANCE_PERP_BTC_USDT"]
    assert records[0]["event"] == "bracket_exit"
    assert records[0]["decision_id"] == "d-test-1"
    assert state.active_plan is None
    assert state.last_bracket_close_at > 0
    assert state.last_stop_at == 0.0          # winning exits arm NO stop cooldown


def test_bracket_exit_stop_loss_arms_cooldown(tmp_path, monkeypatch):
    state = _mk_plan_state(tmp_path, monkeypatch)
    monkeypatch.setattr(ex, "close_position", lambda sym, mn: {"ok": True})
    monkeypatch.setattr(ex.journal, "record", lambda r: None)
    ex.handle_bracket_exit(state, ("stop_loss", Decimal("-0.35")))
    assert state.last_stop_at > 0             # revenge-trading brake engaged


def test_bracket_exit_close_failure_preserves_state(tmp_path, monkeypatch):
    state = _mk_plan_state(tmp_path, monkeypatch)
    records = []
    def boom(sym, mn):
        raise RuntimeError("exchange down")
    monkeypatch.setattr(ex, "close_position", boom)
    monkeypatch.setattr(ex.journal, "record", records.append)
    with pytest.raises(RuntimeError):
        ex.handle_bracket_exit(state, ("stop_loss", Decimal("-0.35")))
    assert records == []                      # nothing journaled for a close that never happened
    assert state.active_plan is not None      # plan kept, so the next cycle retries
    assert state.last_bracket_close_at == 0.0


# weak-exit vote tests

def test_no_vote_when_flat():
    assert not ex.should_call_exit_vote("FLAT", {"action": "LONG", "confidence": 0.9})

def test_no_vote_below_threshold():
    assert not ex.should_call_exit_vote("LONG", {"action": "FLAT", "confidence": 0.64})

def test_vote_at_threshold():
    assert ex.should_call_exit_vote("LONG", {"action": "FLAT", "confidence": 0.65})

def test_strong_reversal_keeps_existing_path():
    assert not ex.should_call_exit_vote("LONG", {"action": "SHORT", "confidence": 0.85})

def test_agreement_is_not_an_exit():
    assert not ex.should_call_exit_vote("LONG", {"action": "LONG", "confidence": 0.9})

def test_count_exit_votes_mixed():
    votes = [{"action": "FLAT"}, {"action": "LONG"}, {"action": "SHORT"}]
    assert ex.count_exit_votes("LONG", votes) == 2

def test_model_exit_happy_path(tmp_path, monkeypatch):
    state = _mk_plan_state(tmp_path, monkeypatch)
    state.update_positions([{"sym": "BINANCE_PERP_BTC_USDT", "positionQty": "0.001",
                             "avgPrice": "64000", "markPrice": "63900"}])
    closed, records = [], []
    monkeypatch.setattr(ex, "close_position", lambda sym, mn: closed.append(sym) or {"ok": True})
    monkeypatch.setattr(ex.journal, "record", records.append)
    votes = [{"action": "FLAT", "confidence": 0.7, "reasoning": "a"},
             {"action": "FLAT", "confidence": 0.5, "reasoning": "b"},
             {"action": "SHORT", "confidence": 0.6, "reasoning": "c"}]
    ex.handle_model_exit(state, votes)
    assert closed == ["BINANCE_PERP_BTC_USDT"]
    assert records[0]["event"] == "model_exit"
    assert len(records[0]["votes"]) == 3
    assert records[0]["pnl_pct"].startswith("-0.15")   # (63900-64000)/64000, long
    assert state.active_plan is None
    assert state.last_stop_at == 0.0                   # voluntary exits are not punished
    assert state.last_bracket_close_at > 0

def test_model_exit_close_failure_preserves_state(tmp_path, monkeypatch):
    state = _mk_plan_state(tmp_path, monkeypatch)
    records = []
    def boom(sym, mn):
        raise RuntimeError("exchange down")
    monkeypatch.setattr(ex, "close_position", boom)
    monkeypatch.setattr(ex.journal, "record", records.append)
    with pytest.raises(RuntimeError):
        ex.handle_model_exit(state, [{"action": "FLAT", "confidence": 0.7}])
    assert records == []
    assert state.active_plan is not None


# edge-zone tests
def test_edge_zone_fade_boundaries():
    assert ex.is_edge_zone_fade("LONG", Decimal("20"))
    assert not ex.is_edge_zone_fade("LONG", Decimal("21"))
    assert ex.is_edge_zone_fade("SHORT", Decimal("80"))
    assert not ex.is_edge_zone_fade("SHORT", Decimal("79"))
    assert not ex.is_edge_zone_fade("LONG", Decimal("85"))    # chasing the high
    assert not ex.is_edge_zone_fade("SHORT", Decimal("15"))   # chasing the low
    assert not ex.is_edge_zone_fade("FLAT", Decimal("10"))
    assert not ex.is_edge_zone_fade("LONG", None)

def test_range_position_normal_and_degenerate():
    t = {"lastPrice": "64500", "lowPrice": "64000", "highPrice": "65000"}
    assert ex.ticker_range_position_pct(t) == Decimal("50")
    flat_day = {"lastPrice": "64000", "lowPrice": "64000", "highPrice": "64000"}
    assert ex.ticker_range_position_pct(flat_day) is None
    assert ex.ticker_range_position_pct({}) is None

DECISION_FADE_SHORT = {"action": "SHORT", "confidence": 0.65, "reasoning": "fade test",
                       "take_profit_pct": Decimal("0.6"), "stop_loss_pct": Decimal("0.4")}

def test_edge_zone_allows_fade_short_at_range_top(tmp_path, monkeypatch):
    state = _mk_state(tmp_path, monkeypatch)
    calls = _mock_broker(monkeypatch, "SELL")
    monkeypatch.setattr(ex, "EDGE_ZONE_ENABLED", True)
    summary = ex.execute_decision(state, dict(DECISION_FADE_SHORT), "d-ez-1",
                                  vol_pct=Decimal("0.5"), chg_12h=Decimal("0.3"),
                                  range_pos=Decimal("85"))
    assert len(calls["placed"]) == 1          # the trade actually happens
    assert calls["placed"][0]["side"] == "SELL"
    assert summary["edge_zone"] == "85"       # and carries its category stamp
    assert summary["gate"] == []

def test_edge_zone_flag_off_still_gates(tmp_path, monkeypatch):
    state = _mk_state(tmp_path, monkeypatch)
    calls = _mock_broker(monkeypatch, "SELL")
    monkeypatch.setattr(ex, "EDGE_ZONE_ENABLED", False)
    summary = ex.execute_decision(state, dict(DECISION_FADE_SHORT), "d-ez-2",
                                  vol_pct=Decimal("0.5"), chg_12h=Decimal("0.3"),
                                  range_pos=Decimal("85"))
    assert calls["placed"] == []
    assert any("chop backstop" in g for g in summary["gate"])

def test_edge_zone_requires_conf_floor(tmp_path, monkeypatch):
    state = _mk_state(tmp_path, monkeypatch)
    calls = _mock_broker(monkeypatch, "SELL")
    monkeypatch.setattr(ex, "EDGE_ZONE_ENABLED", True)
    weak = dict(DECISION_FADE_SHORT, confidence=0.55)
    summary = ex.execute_decision(state, weak, "d-ez-3",
                                  vol_pct=Decimal("0.5"), chg_12h=Decimal("0.3"),
                                  range_pos=Decimal("85"))
    assert calls["placed"] == []
    assert any("chop backstop" in g for g in summary["gate"])

def test_edge_zone_mid_range_still_gated(tmp_path, monkeypatch):
    state = _mk_state(tmp_path, monkeypatch)
    calls = _mock_broker(monkeypatch, "SELL")
    monkeypatch.setattr(ex, "EDGE_ZONE_ENABLED", True)
    ex.execute_decision(state, dict(DECISION_FADE_SHORT), "d-ez-4",
                                  vol_pct=Decimal("0.5"), chg_12h=Decimal("0.3"),
                                  range_pos=Decimal("50"))
    assert calls["placed"] == []

def test_edge_zone_chase_still_gated(tmp_path, monkeypatch):
    state = _mk_state(tmp_path, monkeypatch)
    calls = _mock_broker(monkeypatch, "BUY")
    monkeypatch.setattr(ex, "EDGE_ZONE_ENABLED", True)
    chase = {"action": "LONG", "confidence": 0.65, "reasoning": "chase test",
             "take_profit_pct": Decimal("0.6"), "stop_loss_pct": Decimal("0.4")}
    ex.execute_decision(state, chase, "d-ez-5",
                                  vol_pct=Decimal("0.5"), chg_12h=Decimal("0.3"),
                                  range_pos=Decimal("85"))    # buying at the top
    assert calls["placed"] == []

# entry-vote tests

def test_count_agreeing_votes_unanimous():
    votes = [{"action": "LONG"}, {"action": "LONG"}, {"action": "LONG"}]
    assert ex.count_agreeing_votes("LONG", votes) == 3

def test_count_agreeing_votes_split():
    votes = [{"action": "LONG"}, {"action": "SHORT"}, {"action": "FLAT"}]
    assert ex.count_agreeing_votes("LONG", votes) == 1

def test_count_agreeing_votes_flat_dissent_is_not_agreement():
    votes = [{"action": "LONG"}, {"action": "FLAT"}, {"action": "FLAT"}]
    assert ex.count_agreeing_votes("LONG", votes) == 1

def test_count_agreeing_votes_tolerates_unparsed_none():
    votes = [{"action": "SHORT"}, None, {"action": "SHORT"}]
    assert ex.count_agreeing_votes("SHORT", votes) == 2


# unanimity sizing tests

def test_size_mult_doubles_quantity(tmp_path, monkeypatch):
    state = _mk_state(tmp_path, monkeypatch)
    calls = _mock_broker(monkeypatch, "BUY")
    ex.execute_decision(state, dict(DECISION_LONG), "d-boost-1",
                        vol_pct=Decimal("0.5"), chg_12h=Decimal("1.2"),
                        size_mult=Decimal("2"))
    # max throttle: 1000 * 0.5 = 500 notional -> 0.008 lots, x2 boost = 0.016
    assert Decimal(calls["placed"][0]["quantity"]) == Decimal("0.016")

def test_default_size_unchanged(tmp_path, monkeypatch):
    state = _mk_state(tmp_path, monkeypatch)
    calls = _mock_broker(monkeypatch, "BUY")
    summary = ex.execute_decision(state, dict(DECISION_LONG), "d-boost-2",
                                  vol_pct=Decimal("0.5"), chg_12h=Decimal("1.2"))
    assert Decimal(calls["placed"][0]["quantity"]) == Decimal("0.008")
    assert "size_mult" not in summary


# fee-viability gate + boosted max-age tests

def test_low_volatility_entry_refused(tmp_path, monkeypatch):
    state = _mk_state(tmp_path, monkeypatch)
    calls = _mock_broker(monkeypatch, "BUY")
    summary = ex.execute_decision(state, dict(DECISION_LONG), "d-lowvol",
                                  vol_pct=Decimal("0.2"), chg_12h=Decimal("1.2"))
    assert calls["placed"] == []
    assert any("fee-viable" in g for g in summary["gate"])

def _boosted_state(tmp_path, monkeypatch, mark, peak=None, armed=False):
    import time as _t
    state = _mk_state(tmp_path, monkeypatch)
    state.update_positions([{"sym": "BINANCE_PERP_BTC_USDT", "positionQty": "0.002",
                             "avgPrice": "64000", "markPrice": mark}])
    plan = {"tp_pct": Decimal("0.30"), "sl_pct": Decimal("0.35"),
            "opened_at": _t.time() - 60, "side": "LONG", "boosted": True,
            "ratchet_armed": armed}
    if peak is not None:
        plan["peak_pnl"] = Decimal(peak)
    state.set_plan(plan)
    return state

def test_boosted_no_fixed_take_profit(tmp_path, monkeypatch):
    state = _boosted_state(tmp_path, monkeypatch, "64256")   # +0.40% > tp 0.30
    assert ex.check_bracket(state) is None                    # does NOT bank - ratchet arms
    assert state.active_plan["ratchet_armed"] is True

def test_ratchet_trails_peak(tmp_path, monkeypatch):
    state = _boosted_state(tmp_path, monkeypatch, "64320", peak="0.90", armed=True)  # +0.50 <= 0.90-0.35
    trigger = ex.check_bracket(state)
    assert trigger is not None and trigger[0] == "trail_stop"

def test_ratchet_floor_locks_fees(tmp_path, monkeypatch):
    state = _boosted_state(tmp_path, monkeypatch, "64032", peak="0.32", armed=True)  # +0.05 < floor 0.08
    trigger = ex.check_bracket(state)
    assert trigger is not None and trigger[0] == "trail_stop"

def test_boosted_pre_arm_stop_still_works(tmp_path, monkeypatch):
    state = _boosted_state(tmp_path, monkeypatch, "63740")   # -0.41% below sl
    trigger = ex.check_bracket(state)
    assert trigger is not None and trigger[0] == "stop_loss"


# symbol rotation tests

def test_current_stance_filters_by_symbol():
    rows = [{"sym": "BINANCE_PERP_ETH_USDT", "positionQty": "0.01"}]
    assert ex.current_stance(rows, "BINANCE_PERP_ETH_USDT") == "LONG"
    assert ex.current_stance(rows) == "FLAT"                      # default = BTC, unaffected

def test_check_bracket_uses_plan_symbol(tmp_path, monkeypatch):
    import time as _t
    state = _mk_state(tmp_path, monkeypatch)
    state.update_positions([{"sym": "BINANCE_PERP_ETH_USDT", "positionQty": "0.01",
                             "avgPrice": "1900", "markPrice": "1880"}])
    state.set_plan({"tp_pct": Decimal("0.5"), "sl_pct": Decimal("0.5"),
                    "opened_at": _t.time() - 60, "side": "LONG",
                    "symbol": "BINANCE_PERP_ETH_USDT"})
    trigger = ex.check_bracket(state)                               # -1.05% < -0.5% sl
    assert trigger is not None and trigger[0] == "stop_loss"

def test_execute_decision_stamps_symbol(tmp_path, monkeypatch):
    state = _mk_state(tmp_path, monkeypatch)
    calls = _mock_broker(monkeypatch, "BUY")
    ex.execute_decision(state, dict(DECISION_LONG), "d-eth-1",
                        vol_pct=Decimal("0.5"), chg_12h=Decimal("1.2"),
                        symbol="BINANCE_PERP_ETH_USDT")
    assert calls["placed"][0]["symbol"] == "BINANCE_PERP_ETH_USDT"
    assert state.active_plan["symbol"] == "BINANCE_PERP_ETH_USDT"


# one-position invariant tests (regression: ETH/SOL positions stacked, 2026-08-07)

SOL_SYM = "BINANCE_PERP_SOL_USDT"

def test_holding_sol_blocks_second_sol_entry(tmp_path, monkeypatch):
    state = _mk_state(tmp_path, monkeypatch)
    calls = _mock_broker(monkeypatch, "BUY")
    state.update_positions([{"sym": SOL_SYM, "positionQty": "6.6",
                             "avgPrice": "73.5", "markPrice": "73.6"}])
    summary = ex.execute_decision(state, dict(DECISION_LONG), "d-stack-1",
                                  vol_pct=Decimal("0.5"), chg_12h=Decimal("1.2"),
                                  symbol=SOL_SYM)
    assert calls["placed"] == []                 # stance is LONG for SOL -> HOLD, no stacking
    assert summary["transition"].startswith("LONG")

def test_holding_sol_blocks_entry_on_another_symbol(tmp_path, monkeypatch):
    state = _mk_state(tmp_path, monkeypatch)
    calls = _mock_broker(monkeypatch, "BUY")
    state.update_positions([{"sym": SOL_SYM, "positionQty": "6.6",
                             "avgPrice": "73.5", "markPrice": "73.6"}])
    summary = ex.execute_decision(state, dict(DECISION_LONG), "d-stack-2",
                                  vol_pct=Decimal("0.5"), chg_12h=Decimal("1.2"))
    assert calls["placed"] == []                 # BTC entry refused while SOL is open
    assert any("one-position invariant" in g for g in summary["gate"])

def test_flat_still_opens_normally(tmp_path, monkeypatch):
    state = _mk_state(tmp_path, monkeypatch)
    calls = _mock_broker(monkeypatch, "BUY")
    state.update_positions([{"sym": SOL_SYM, "positionQty": "0"}])   # qty 0 = not a position
    ex.execute_decision(state, dict(DECISION_LONG), "d-stack-3",
                        vol_pct=Decimal("0.5"), chg_12h=Decimal("1.2"), symbol=SOL_SYM)
    assert len(calls["placed"]) == 1
