import time
import json
import os
import logging 
from decimal import Decimal

PLAN_PATH = os.path.join("data", "active_plan.json")

class BotState:
    __slots__ = (
    "equity", "equity_updated_at", "open_positions", "positions_updated_at",
    "last_decision", "last_decision_at", "last_entry_at", "last_write_at",
    "last_bracket_close_at", "last_stop_at", "halted", "halt_reason",
    "pending_signal", "active_plan", "ranking_day", "day_start_equity",
    )
    
    def __init__(self):
        self.equity: Decimal | None = None
        self.equity_updated_at: float = 0.0
        self.open_positions: list = []
        self.positions_updated_at: float = 0.0
        self.last_decision: dict | None = None
        self.last_decision_at: float = 0.0
        self.last_entry_at: float = 0.0
        self.last_write_at: float = 0.0
        self.last_bracket_close_at: float = 0.0
        self.last_stop_at: float = 0.0
        self.halted: bool = False
        self.halt_reason: str | None = None
        self.pending_signal: str | None = None
        self.ranking_day: int | None = None
        self.day_start_equity: Decimal | None = None
        self.active_plan: dict | None = None
    
    def update_equity(self, equity: Decimal) -> None:
        self.equity = equity
        self.equity_updated_at = time.time()
    
    def update_positions(self, positions: list) -> None:
        self.open_positions = positions
        self.positions_updated_at = time.time()
    
    def update_decision(self, decision: dict) -> None:
        self.last_decision = decision
        self.last_decision_at = time.time()
    
    @property
    def equity_age(self) -> float:
        """ Seconds since equity was last read successfully """
        return time.time() - self.equity_updated_at
    
    def summary(self) -> str:
        """ One line status for heartbeat """
        action = self.last_decision["action"] if self.last_decision else "none"
        return (
            f"equity={self.equity} (age {self.equity_age:.0f}s)"
            f"\npositions={len(self.open_positions)}"
            f"\nlast_decision={action}"
            f"\nhalted={self.halted}"
        )
    
    def set_plan(self, plan: dict | None) -> None:
        """ Set the active trade plan and mirror it to disk so brackets and decision_ids survive a restart """
        self.active_plan = plan
        try:
            os.makedirs("data", exist_ok=True)
            if plan is None:
                if os.path.exists(PLAN_PATH):
                    os.remove(PLAN_PATH)
            else:
                with open(PLAN_PATH, "w") as f:
                    json.dump({k: str(v) for k, v in plan.items()}, f)
        
        except Exception:
            logging.getLogger("bot.state").exception("failed to persist plan")
    
    def load_plan(self) -> None:
        """ Restore a persisted plan after bot restart. Never raises """
        try:
            if os.path.exists(PLAN_PATH):
                with open(PLAN_PATH) as f:
                    raw = json.load(f)
                self.active_plan = {
                    "tp_pct" : Decimal(raw["tp_pct"]),
                    "sl_pct" : Decimal(raw["sl_pct"]),
                    "decision_id" : raw.get("decision_id"),
                    "opened_at" : float(raw.get("opened_at", 0)),
                    "side" : raw.get("side")
                }
        except Exception:
            logging.getLogger("bot.state").exception("failed to load persisted plan")