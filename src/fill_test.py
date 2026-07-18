""" Position lifecycle test: buy small -> inspect position -> close -> confirm flat """

import json
import time 
from decimal import Decimal

from broker.rapidx import (
    get_ticker,
    get_symbol_info,
    get_positions,
    get_open_positions,
    get_portfolio_overview,
    close_position,
    new_client_order_id,
    place_order,
    query_order,
    snap_down,
    snap_up
)

SYMBOL  = "BINANCE_PERP_BTC_USDT"

info = get_symbol_info(SYMBOL)
tick = Decimal(str(info['tickSize']))
lot = Decimal(str(info['lotSize']))
min_notional = Decimal(str(info['minNotional']))

print("---BEFORE: portfolio---")
before = get_portfolio_overview()
print(f"Equity={before['equity']}   available={before['availableMargin']}")

# --- marketable buy; cap price 0.2% above last, snapped down to grid ---
last = Decimal(str(get_ticker(SYMBOL)['lastPrice']))
cap_price = snap_down(last * Decimal('1.002'), tick)
quantity = snap_up(min_notional / cap_price, lot)

order_id = new_client_order_id("fill")
order = {
    "symbol" : SYMBOL,
    "side" : "BUY",
    "positionSide" : "LONG",
    "orderType" : "LIMIT",
    "price" : str(cap_price),
    "quantity" : str(quantity),
    "maxNotional" : str(cap_price * quantity),
    "clientOrderId" : order_id
}
print(f"\n--- buying {quantity} @ cap {cap_price} (last={last})")
print(json.dumps(place_order(order), indent=2))

# --- poll until reaching terminal(ish) state ---
for _ in range(10):
    time.sleep(2)
    state = query_order(order_id)['data']
    print(f"orderState={state['orderState']}   filled={state['executedQty']}   @ avg {state['executedAvgPrice']}")
    if state['orderState'] in ("FILLED", "CANCELLED", "REJECTED", "EXPIRED"):
        break

print("\n---position---")
print(json.dumps(get_positions(), indent=2))

print("\n---portfolio while holding---")
mid = get_portfolio_overview()
print(f'equity={mid['equity']}   available={mid['availableMargin']}   upnl={mid['upnl']}')

# --- observe rate/write limits, then close position
time.sleep(10)
print("\n---closing position---")
print(json.dumps(close_position(SYMBOL, max_notional="100"), indent=2))

for _ in range(10):
    time.sleep(2)
    if not get_open_positions():
        print("Position closed. Currently flat.")
        break
    print("Position still open. Polling....")

print("\n---AFTER: portfolio ---")
after = get_portfolio_overview()
print(f"Equity={after['equity']}   available={after['availableMargin']}")
print(f"Total lifecycle cost: {Decimal(before['equity']) - Decimal(after['equity'])} USDT")