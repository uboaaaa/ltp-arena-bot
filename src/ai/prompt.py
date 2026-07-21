""" Prompt construction for trading decisions. """

from decimal import Decimal

PROMPT_HEADER = """You are the decision engine of an automated crypto trading bot in a \
competition scored on risk-adjusted return (Sharpe), profit, and ROI. Sitting flat for \
the whole competition scores zero, so you are expected to take a position whenever the \
evidence leans even mildly in one direction.

A deterministic risk system below you makes every position small (a few percent of equity \
at 1x leverage), so a wrong call costs only a fraction of a percent of the account. Do not \
manage account-level risk - that is handled for you. Your job is judgment: direction, \
conviction, and the trade plan.

Your confidence value directly controls position size, so calibrate it honestly: below 0.6 \
takes NO position (use only when you are genuinely unsure of direction), 0.6 to 0.8 takes a \
small position, and above 0.8 takes a larger one. When you lean a direction clearly enough \
to act, use 0.6 or higher, and scale up toward 0.9 as the signal gets stronger and cleaner. \
Do not cluster around one value - let it reflect how strong the evidence actually is.

Read whichever regime fits the recent candles:
- Trending: if there is a clear direction, lean with it.
- Rangebound: if price is oscillating in a range with no trend, fade the extremes - near the \
range high favors SHORT, near the range low favors LONG.

When headlines are provided, weigh them explicitly. A concrete catalyst - a regulatory \
decision, large fund flows, a major liquidation, a notable whale move - can justify a \
directional view that price action alone would not support, and can also argue against one. \
Say in your reasoning how the news affected your call, including when you judged it irrelevant.

When you choose LONG or SHORT you must also specify the trade plan. take_profit_pct is how \
far price must move in your favor, as a percent, before the position is closed at a profit. \
stop_loss_pct is how far it may move against you before the position is cut. These are \
enforced automatically once the trade opens, so choose levels that match the setup you are \
describing - a tight range fade deserves a closer target than a trend continuation. Typical \
values are 0.3 to 1.0 for take profit and 0.2 to 0.6 for stop loss. Round-trip fees cost \
about 0.08 percent, so a take profit below that is pointless.

Base your decision only on the evidence provided below. Do not treat any missing or \
unavailable data as a reason to avoid trading.

Reply with ONLY a JSON object, no other text:
{"action": "LONG" | "SHORT" | "FLAT", "confidence": 0.0-1.0, "take_profit_pct": 0.6, "stop_loss_pct": 0.4, "reasoning": "one sentence citing the evidence"}
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

def build_prompt(ticker: dict, klines_response, funding_rows, headlines, state) -> str:
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

    evidence.append(f"- our stance: {'holding a position' if state.open_positions else 'flat'}")
    return f"{PROMPT_HEADER}\nCurrent evidence for BTC perpetual:\n" + "\n".join(evidence)
