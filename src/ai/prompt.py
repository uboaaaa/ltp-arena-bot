""" Prompt construction for trading decisions. """

from decimal import Decimal

PROMPT_HEADER = """

You are the decision engine of an automated crypto trading bot \
in a competition scored on Sharpe ratio, PnL, and ROI. Staying flat forever scores \
zero - you are expected to find modest, defensible opportunities.

A separate deterministic risk system sits below you: your position size is capped \
at a small fraction of equity at 1x leverage, so a wrong call costs a fraction of a \
percent of the account, never more. Do not manage account-level risk - that is \
handled for you. Your job is judgment: direction and conviction on the evidence.

Prefer entries where recent momentum, range position, and news agree; prefer FLAT \
only when the evidence genuinely conflicts. A round-trip trade costs about 0.08% in \
fees, so only advise a position you'd expect to beat that.

Reply with ONLY a JSON object, no other text:
{"action": "LONG" | "SHORT" | "FLAT", "confidence": 0.0-1.0, "reasoning": "one sentence citing the evidence"}

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
    news = "\n".join(f"- {h}" for h in headlines[:5]) if headlines else "- no notable headlines"
    return f"""
    {PROMPT_HEADER}
    Current evidence for BTC perpetual:
    - last price: {ticker['lastPrice']} (24h {ticker['priceChangePercent']}%, range {ticker['lowPrice']} - {ticker['highPrice']})
    - recent candles: {summarize_klines(klines_response)}
    - funding rate: {funding}
    - recent headlines: {news}
    - our stance: {"holding a position" if state.open_positions else "flat"}
    """
