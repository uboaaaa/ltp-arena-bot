import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from broker.rapidx import get_ticker, get_portfolio_overview, get_equity
import json 

print('--ticker--')
t = get_ticker("BINANCE_PERP_BTC_USDT")
print(f"BTC last price: {t['lastPrice']} (24h change {t['priceChangePercent']}%)")

print('--portfolio--')
p = get_portfolio_overview()
print(json.dumps(p, indent=2))

print('--equity--')
e = get_equity()
print(f"Equity: {e} USDT")
