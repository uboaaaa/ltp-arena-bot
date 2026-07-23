from decimal import Decimal

import bot.state as state_mod


def _plan():
    return {"tp_pct": Decimal("0.5"), "sl_pct": Decimal("0.3"),
            "decision_id": "d-test", "opened_at": 123.0, "side": "LONG"}


def test_plan_survives_a_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(state_mod, "PLAN_PATH", str(tmp_path / "plan.json"))
    s1 = state_mod.BotState()
    s1.set_plan(_plan())
    s2 = state_mod.BotState()          # simulates the restarted process
    s2.load_plan()
    assert s2.active_plan["tp_pct"] == Decimal("0.5")
    assert s2.active_plan["decision_id"] == "d-test"
    assert s2.active_plan["opened_at"] == 123.0


def test_clearing_plan_removes_the_file(tmp_path, monkeypatch):
    monkeypatch.setattr(state_mod, "PLAN_PATH", str(tmp_path / "plan.json"))
    s1 = state_mod.BotState()
    s1.set_plan(_plan())
    s1.set_plan(None)
    s2 = state_mod.BotState()
    s2.load_plan()
    assert s2.active_plan is None


def test_load_with_no_file_is_harmless(tmp_path, monkeypatch):
    monkeypatch.setattr(state_mod, "PLAN_PATH", str(tmp_path / "nope.json"))
    s = state_mod.BotState()
    s.load_plan()
    assert s.active_plan is None