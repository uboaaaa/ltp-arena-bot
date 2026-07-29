""" All tunable parameters for the bot in one place """

from decimal import Decimal

SYMBOL = "BINANCE_PERP_BTC_USDT"

# --- intervals  ---
RISK_INTERVAL = 10
STRATEGY_INTERVAL = 300
HEARTBEAT_INTERVAL = 60

# --- risk thresholds (USDT equity) ---
SOFT_HALT_EQUITY = Decimal("965")
HARD_FLATTEN_EQUITY = Decimal("955")

# --- master switch ---
EXECUTION_ENABLED = True # "True" means orders actually execute. will turn to True during competition period

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
BRACKET_COOLDOWN_SECONDS = 30
REQUIRE_CONFIRMATION = False

# --- execution ---
BASE_POSITION_FRACTION = Decimal("0.08")
CONF_FLOOR = 0.6
CONF_FULL = 0.8
MIN_HOLD_SECONDS = 900
MAX_EQUITY_AGE = 30
WRITE_SPACING = 6

# --- volatility-derived bracket params ---
VOL_SL_MULT = Decimal("0.7") # replay-tuned 2026-07-28: kept all winners, halved losses; cliff below 0.5
VOL_TP_MULT = Decimal("0.8")
STOP_COOLDOWN_SECONDS = 2700
CHOP_THRESHOLD_PCT = Decimal("0.8") # within 12 hrs, changes below this value indicate rangebound market
CHOP_CONF_FLOOR = 0.7 # minimum confidence to open a position during a chop

# --- bot exit confidence
EXIT_CONF = 0.65
EXIT_VOTE_CALLS = 2
EXIT_VOTES_NEEDED = 2