""" Decision-prompt test for the AI gateway """

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

import json 
import os
import time 
from openai import OpenAI

from broker.rapidx import get_ticker
from ai.parsing import parse_llm_decision  

client = OpenAI(
    api_key=os.environ["AI_API_KEY"],
    base_url="https://ai.ltp-contest.com/v1",
    timeout=300,
)

ticker = get_ticker("BINANCE_PERP_BTC_USDT")

prompt = f""" You are the decision engine of a crypto trading bot.

Current market data for BTC perpetual:
- last price : {ticker['lastPrice']}
- 24hr change : {ticker['priceChangePercent']}%
- 24hr high/low : {ticker['highPrice']} / {ticker['lowPrice']}

Our account: 1000 USDT equity, no open position. 
RULES: We are eliminated if we ever lose 20% of the account. USE CAUTION.

Reply with ONLY a JSON object, no other text:
{{"action": "LONG" | "SHORT" | "FLAT", "confidence": 0.0-1.0, "reasoning": "one sentence"}}"""

start = time.time()
response = client.chat.completions.create(
    model="MiniMax-M3",
    messages=[{"role": "user", "content": prompt}],
    max_tokens=8000
)
elapsed = time.time() - start

raw = response.choices[0].message.content
print(f'Elapsed: {elapsed:.1f}s')
print(f'usage: {response.usage}')
print(f'raw reply:\n{raw}')

decision = parse_llm_decision(raw)
if decision is None:
    print(f"REPLY UNPARSEABLE. Skip LLM decision this cycle: \n{raw!r}")
else:
    print(f"Parsed OK: {decision}")