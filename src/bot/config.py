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
MAX_POSITION_AGE_SECONDS = 3600            # sweep 2026-08-02: 60-120min hold zone ran 9% winrate
MAX_POSITION_AGE_BOOSTED_SECONDS = 7200    # boosted trades keep a longer leash
BRACKET_COOLDOWN_SECONDS = 30
REQUIRE_CONFIRMATION = False

# --- execution ---
BASE_POSITION_FRACTION = Decimal("0.25") # 2026-08-01 size escalation: tournament variance play, see docs/experiments.md
CONF_FLOOR = 0.6
CONF_FULL = 0.8
MIN_HOLD_SECONDS = 900
MAX_EQUITY_AGE = 30
WRITE_SPACING = 6

# --- volatility-derived bracket params ---
VOL_SL_MULT = Decimal("0.7") # replay-tuned 2026-07-28: kept all winners, halved losses; cliff below 0.5
VOL_TP_MULT = Decimal("0.6")
STOP_COOLDOWN_SECONDS = 2700
CHOP_THRESHOLD_PCT = Decimal("0.8") # within 12 hrs, changes below this value indicate rangebound market
CHOP_CONF_FLOOR = 1.01 # trend-only mode 2026-08-01: unreachable bar = NO entries in rangebound regime (see docs/experiments.md)

# --- bot exit confidence ---
EXIT_CONF = 0.65
EXIT_VOTE_CALLS = 2
EXIT_VOTES_NEEDED = 2

# --- audit tier-1 (2026-08-02, see docs/experiments.md) ---
DAILY_LOSS_LIMIT = Decimal("1.5")   # block new entries when ranking-day pnl (16:00 UTC anchor) is below -this
TREND_SCAN_INTERVAL = 150           # faster decision cadence while FLAT in a trending regime

# --- unanimity sizing: unanimous 3-of-3 entry vote + catalyst doubles size ---
UNANIMITY_SIZE_MULT = Decimal("2")

# --- bot entry confirmation vote ---
ENTRY_VOTE_ENABLED = True
ENTRY_VOTE_CALLS = 2
ENTRY_VOTES_NEEDED = 2

# --- edge zone experiments (see experiment doc)
EDGE_ZONE_ENABLED = False # experiment closed 2026-08-01: trend-only pivot
EDGE_ZONE_PCT = Decimal("20") # outer band width, as percent of day's range