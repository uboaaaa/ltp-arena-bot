"""End-to-end dry run of the LIVE trade path with mocked broker calls.

Exercises: chop backstop pass-through, gates, derive_brackets override,
sizing, _open (place -> poll -> fill -> set_plan), and the bracket close
trigger - the exact code that runs at 3am. No network, no real orders.
"""


from decimal import Decimal

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
    assert Decimal(eb["tp"]) == Decimal("0.4")             # 0.5 * 0.8
    assert Decimal(eb["sl"]) == Decimal("0.65")            # 0.5 * 1.3
    # plan persisted with the EFFECTIVE brackets and decision id
    assert state.active_plan["decision_id"] == "d-dry-1"
    assert state.active_plan["tp_pct"] == Decimal("0.4")
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
