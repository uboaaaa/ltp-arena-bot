"""
Full order lifecycle test: preview -> place -> query -> cancel
This order test is unfillable by design, and is a post-only limit buy priced far below the market.
"""

import json
import time
from decimal import Decimal, ROUND_DOWN

from broker.rapidx import (
    get_symbol_info,
    get_ticker,
    new_client_order_id,
    place_order,
    query_order,
    cancel_order,
    snap_down,
    snap_up
)

SYMBOL = "BINANCE_PERP_BTC_USDT"

#--- 1. get trading rules for this symbol ---
info = get_symbol_info(SYMBOL)
print('---symbol info---')
print(json.dumps(info, indent=2))

tick_size = Decimal(str(info["tickSize"]))
lot_size = Decimal(str(info["lotSize"]))
min_notional = Decimal(str(info["minNotional"]))

#--- 2. compute valid order ---
last_price = Decimal(str(get_ticker(SYMBOL)["lastPrice"]))
raw_price = last_price * Decimal("0.80")
price = snap_down(raw_price, tick_size)

raw_quantity = min_notional / price
quantity = snap_up(raw_quantity, lot_size)

notional = price * quantity
print(f'\nmarket={last_price}  our price={price}  qty={quantity}  notional={notional}')
assert notional >= min_notional, "Sizing bug: falling below min_notional"

#--- 3. place valid order ---
order_id = new_client_order_id("test")
order = {
    "symbol" : SYMBOL,
    "side" : "BUY",
    "positionSide" : "LONG",
    "orderType" : "LIMIT",
    "price" : str(price),
    "quantity" : str(quantity),
    "maxNotional" : str(notional),
    "clientOrderId" : order_id,
    "postOnly" : True,
}
print(f"\n---PLACING ORDER: {order_id}---")
result = place_order(order)
print(json.dumps(result, indent=2))

#--- 4. confirm order is resting in the book ---
time.sleep(2)
print('\n---querying---')
state = query_order(order_id)
print(json.dumps(state, indent=2))

#--- 5. cancel order (while observing 1 write per 5s limit)---
time.sleep(5)
print('\n---cancelling---')
cancelled = cancel_order(order_id)
print(json.dumps(cancelled, indent=2))

#--- 6. confirm order cancellation---
time.sleep(2)
print('\n---final state of order---')
final = query_order(order_id)
print(json.dumps(final, indent=2))

