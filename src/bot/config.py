""" All tunable parameters for the bot in one place """

from decimal import Decimal

SYMBOL = "BINANCE_PERP_BTC_USDT"

# --- intervals  ---
RISK_INTERVAL = 10
STRATEGY_INTERVAL = 600
HEARTBEAT_INTERVAL = 60

# --- risk thresholds (USDT equity) ---
SOFT_HALT_EQUITY = Decimal("920")
HARD_FLATTEN_EQUITY = Decimal("900")

# --- master switch ---
EXECUTION_ENABLED = False # "True" means orders actually execute. will turn to True during competition period

# --- AI ---
AI_MODEL = "MiniMax-M3"
AI_BASE_URL = "https://ai.ltp-contest.com/v1"
AI_TIMEOUT = 300
AI_MAX_TOKENS = 8000

# --- AI trading bounds ---
MIN_TP_PCT = Decimal("0.15")
MAX_TP_PCT = Decimal("3.0")
MIN_SL_PCT = Decimal("0.15")
MAX_SL_PCT = Decimal("1.5")
DEFAULT_TP_PCT = Decimal("0.6")
DEFAULT_SL_PCT = Decimal("0.4")
MAX_POSITION_AGE_SECONDS = 4 * 3600
REQUIRE_CONFIRMATION = True

# --- execution ---
BASE_POSITION_FRACTION = Decimal("0.08")
CONF_FLOOR = 0.6
CONF_FULL = 0.8
MIN_HOLD_SECONDS = 900
MAX_EQUITY_AGE = 30
WRITE_SPACING = 6