import time 
from decimal import Decimal

class BotState:
    def __init__(self):
        self.equity: Decimal | None = None
        self.equity_updated_at: float = 0.0
        self.open_positions: list = []
        self.positions_updated_at: float = 0.0
        self.last_decision: dict | None = None
        self.last_decision_at: float = 0.0
        self.halted: bool = False
        self.halt_reason: str | None = None
    
    def update_equity(self, equity: Decimal) -> None:
        self.equity = equity
        self.equity_updated_at = time.time()
    
    def update_positions(self, positions: list) -> None:
        self.open_positions = positions
        self.positions_updated_at = time.time()
    
    def update_decision(self, decision: dict) -> None:
        self.last_decision = decision
        self.last_decision_at = time.time()
    
    def equity_age(self) -> float:
        """ Seconds since equity was last read successfully """
        return time.time() - self.equity_updated_at
    
    def summary(self) -> str:
        """ One line status for heartbeat """
        action = self.last_decision["action"] if self.last_decision else "none"
        return (
            f"equity={self.equity} (age {self.equity_age():.0f}s)"
            f"\npositions={len(self.open_positions)}"
            f"\nlast_decision={action}"
            f"\nhalted={self.halted}"
        )