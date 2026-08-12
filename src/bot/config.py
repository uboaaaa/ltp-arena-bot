""" All tunable parameters for the bot in one place """

from decimal import Decimal

SYMBOL = "BINANCE_PERP_BTC_USDT"
SYMBOLS = [SYMBOL, "BINANCE_PERP_ETH_USDT", "BINANCE_PERP_SOL_USDT"]  # scan list: one position at a time, rotate when flat

# --- intervals  ---
RISK_INTERVAL = 10
STRATEGY_INTERVAL = 300
HEARTBEAT_INTERVAL = 60

# --- risk thresholds (USDT equity) ---
SOFT_HALT_EQUITY = Decimal("850")  # 2026-08-07 user directive: use every trading day; breaker (-5/day) cannot reach this before phase end
HARD_FLATTEN_EQUITY = Decimal("825") # elimination insurance only (elimination at 800)

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
# MAX_POSITION_AGE removed 2026-08-05: time limits killed the runners the ratchet
# exists to ride (T.Anh evidence: multi-day holds are the one working method in
# this market). Positions end at the stop, the trail, or an exit vote - not a clock.
RATCHET_FLOOR_PCT = Decimal("0.08")        # once the ratchet arms, never exit below fees+slippage
BRACKET_COOLDOWN_SECONDS = 30
REQUIRE_CONFIRMATION = False

# --- execution ---
BASE_POSITION_FRACTION = Decimal("0.5")  # 2026-08-04 MAX THROTTLE: final legal setting, 2x leverage verified on all symbols
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
EXIT_VOTE_CALLS = 0     # review 2: lone exit signals were right 10/14; confirmation added delay, not accuracy
EXIT_VOTES_NEEDED = 1   # first qualifying exit opinion closes immediately

# --- audit tier-1 (2026-08-02, see docs/experiments.md) ---
DAILY_LOSS_LIMIT = Decimal("5.0")  # 2026-08-04: max throttle needs ~1 boosted stop + 1 base stop of room per day   # block new entries when ranking-day pnl (16:00 UTC anchor) is below -this
TREND_SCAN_INTERVAL = 150           # faster decision cadence while FLAT in a trending regime

# --- boosted-only endgame (2026-08-11): EV/trade = ~0 gross - 0.05 fees, so
# ordinary trades are a guaranteed drip (~-$2-4/day at full frequency). Only the
# unanimous+catalyst max-size ratchet trade carries the win condition - trade nothing else.
BOOSTED_ONLY = True

# --- unanimity sizing: unanimous 3-of-3 entry vote + catalyst doubles size ---
UNANIMITY_SIZE_MULT = Decimal("2")
CATALYST_VOTES_NEEDED = 2  # 2026-08-12: catalyst flag is noisy on stale headlines; any-1-of-3 let Aug 11 chain-fire 3 strikes on one trend episode (-$6.07)

# --- bot entry confirmation vote ---
ENTRY_VOTE_ENABLED = True
ENTRY_VOTE_CALLS = 2
ENTRY_VOTES_NEEDED = 2

# --- edge zone experiments (see experiment doc)
EDGE_ZONE_ENABLED = False # experiment closed 2026-08-01: trend-only pivot
EDGE_ZONE_PCT = Decimal("20") # outer band width, as percent of day's range