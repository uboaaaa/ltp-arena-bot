""" Prompt construction for trading decisions. """

import time
from decimal import Decimal

PROMPT_HEADER = """You are the decision engine of an automated crypto trading bot in a \
competition scored on risk-adjusted return (Sharpe), profit, and ROI. The bot is trend-only. In a \
qualifying trend you are expected to position when the evidence leans; FLAT is the correct \
professional call whenever there is no qualifying trend - a forced trade in noise only pays fees.

A deterministic execution layer below you owns sizing and account-level risk. A new position is \
about a quarter of account equity in notional at 1x leverage, and a stopped-out trade typically \
costs a fraction of a percent of the account. Do not manage account-level risk - that is handled \
for you. Your job is judgment: direction, and honest reasoning for it.

The regime rule is strict and mechanically enforced. If the 12h change is under 0.8 percent in \
absolute terms, the market is rangebound and NO new position will open no matter what you output; \
the correct call there is FLAT. If the 12h change is at or above 0.8 percent, the market is \
trending, and only entries in the trend direction can execute: LONG only when the 12h change is \
positive, SHORT only when it is negative. A counter-trend entry is discarded downstream, so never \
spend conviction on one. These gates govern NEW entries only - when you are already holding a \
position, your call matters in every direction, as described next.

Confidence is a gate, not a size dial - it does not scale position size. An entry call below 0.6 \
takes no position; at 0.6 or above it takes the standard full position. While holding a position: \
agreeing with the held direction keeps it open; if you believe the position should be closed, say \
FLAT with confidence 0.65 or higher, which triggers an exit review; an opposite-direction call at \
0.8 or above attempts an immediate close-and-reverse, which executes only if the 12h trend has \
actually flipped to match the new direction.

The 5-minute closes reveal moves that began within the last hour, before they appear in hourly \
candles. In a qualifying trend a fresh 5-minute move can justify an earlier entry or confirm \
continuation; in a rangebound market 5-minute fluctuations are noise and cannot create a tradable \
regime on their own.

When headlines are provided, weigh them explicitly. A concrete catalyst - a regulatory decision, \
large fund flows, a major liquidation, a notable whale move - can justify a directional view that \
price action alone would not support, and can also argue against one. Say in your reasoning how \
the news affected your call, including when you judged it irrelevant. Set catalyst to true only \
when a specific headline materially drove your directional choice, not when the news was merely \
present.

When you choose LONG or SHORT you must still provide take_profit_pct and stop_loss_pct, but they \
are advisory: the live exit brackets are derived from measured volatility (take profit about 0.6x \
and stop loss about 0.7x the recent average hourly range), and your values are used only as a \
fallback when volatility data is missing, so keep them sensible for the setup you describe. Two \
hard constraints should shape which trades you propose: every position is force-closed after about 1 hour \
old, so only take setups you expect to resolve fast, and round-trip fees cost about \
0.05 percent, so the expected move must be worth meaningfully more than that.

Base your decision only on the evidence provided below. Do not treat any missing or unavailable \
data as a reason to avoid trading.

Reply with ONLY a JSON object, no other text:
{"action": "LONG" | "SHORT" | "FLAT", "confidence": 0.0-1.0, "take_profit_pct": 0.6, "stop_loss_pct": 0.4, "reasoning": "one sentence citing the evidence", "catalyst": true | false}
"""

def summarize_klines(klines_response) -> str:
    """ Turn raw kline response into one line of trend description """
    candles = klines_response.get("candles", []) if isinstance(klines_response, dict) else klines_response
    if not candles:
        return "no recent candle data available"
    # each candle is a positional array; [openTime, open, high, low, close, volume]
    closes = [Decimal(c[4]) for c in candles]
    highs = [Decimal(c[2]) for c in candles]
    lows = [Decimal(c[3]) for c in candles]
    change_full = ( (closes[-1] - closes[0]) / closes[0] ) * 100
    last3 = ( (closes[-1] - closes[-4]) / closes[-4] ) * 100 if len(closes) >= 4 else change_full
    return (
        f"{len(candles)}h change {change_full:+.2f}%, last 3h {last3:+.2f}%,"
        f"range {min(lows)} - {max(highs)}, hourly closes: " + " ".join(f"{c:.0f}" for c in closes)
    )

def summarize_recent_5m(klines_response) -> str:
    """ The last hour at 5 minute resolution. Need this to see what hourly candle summaries can't show """
    candles = klines_response.get("candles", []) if isinstance(klines_response, dict) else klines_response
    if not candles:
        return "no recent 5-minute data available"
    closes = [Decimal(c[4]) for c in candles]
    change = (closes[-1] - closes[0]) / closes[0] * 100
    return (
        f"last 60 min change {change:+.2f}%, 5-minute closes: "
        + " ".join(f"{c:.0f}" for c in closes)
    )
def build_prompt(ticker: dict, klines_response, funding_rows, headlines, state, klines_5m=None, symbol_name="BTC") -> str:
    """ assembles full decision prompt from collated market data """
    funding = funding_rows[0]["fundingRate"] if funding_rows else "unknown"
    evidence = [
        f"- last price: {ticker["lastPrice"]} (24h {ticker["priceChangePercent"]}%)",
        f"- range: {ticker['lowPrice']} - {ticker['highPrice']}",
        f"- recent candles: {summarize_klines(klines_response)}",
        f"- funding rate: {funding}"
    ]
    if headlines:
        news = "\n".join(f" - {h}" for h in headlines[:5])
        evidence.append(f"- recent headlines:\n{news}")
    if klines_5m:
        evidence.append(f"- {summarize_recent_5m(klines_5m)}")

    evidence.append(f"- our stance: {describe_stance(state)}")
    return f"{PROMPT_HEADER}\nCurrent evidence for {symbol_name} perpetual:\n" + "\n".join(evidence)

def describe_stance(state) -> str:
    """ One-liner explaining the position we're holding to the model so it doesn't have to guess. Positive PnL means trade is winning for longs and shorts alike """
    try:
        row = next((r for r in state.open_positions if Decimal(str(r.get("positionQty", "0"))) != 0), None)
        if row is None:
            return "flat"
        
        qty = Decimal(str(row["positionQty"]))
        side = "LONG" if qty > 0 else "SHORT"
        line = f"holding a {side}"
        avg = Decimal(str(row.get("avgPrice", "0")))
        mark = Decimal(str(row.get("markPrice", "0")))
        if avg > 0 and mark > 0:
            direction = Decimal("1") if qty > 0 else Decimal("-1")
            pnl_pct = ((mark - avg) / avg) * Decimal("100") * direction
            line += f" opened at {avg}, currently {pnl_pct:+.2f}%"
        plan = state.active_plan or {}
        opened_at = float(plan.get("opened_at") or 0)
        if opened_at:
            line += f", held for {(time.time() - opened_at) / 60:.0f} minutes"
        return line
    
    except Exception:
        return "holding a position" if state.open_positions else "flat"
    
