"""
RapidX CLI Wrapper.
All interactions with the trading platform go through run_command()
"""

import json
import subprocess
import secrets
import time
from decimal import Decimal, ROUND_DOWN, ROUND_UP 

class RapidXError(Exception):
    """
    Platform returns ok=false (i.e., a real, explainable failure)
    """

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code} : {message}")
    
def run_command(*args: str, timeout: int = 30) -> dict:
    """
    Run a RapidX CLI command and return the 'data' part of its response
    Eg: 
        run_command("market", "get-ticker", "--input", '{"symbol" : "BINANCE_PERP_BTC_USDT"}')
    """
    cmd = ["rapidx", *args, "--json"]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout
    )

    if not result.stdout.strip():
        raise RuntimeError(
            f"RapidX produced no output (exit code {result.returncode})."
            f"stderr: {result.stderr.strip()}"
        )

    envelope = json.loads(result.stdout)

    if not envelope.get("ok"):
        raise RapidXError(
            code=envelope.get("code", "UNKNOWN"),
            message=envelope.get("message", "no message")
        )
    
    return envelope.get("data", {})

def get_ticker(symbol: str) -> dict:
    """ Current price and 24h stats for a given symbol """
    return run_command("market", "get-ticker", "--input", json.dumps({"symbol" : symbol}))

def get_portfolio_overview() -> dict:
    """ Account summary for Binance portfolio: equity, balances, margin """
    response = run_command("portfolio", "overview")

    rows = response.get("data", [])
    for row in rows:
        if row.get("exchangeType") == "BINANCE":
            return row
    
    raise RuntimeError(f"No Binance portfolio row found in overview response: {response!r}")

def get_equity() -> Decimal:
    return Decimal(get_portfolio_overview()["equity"])

def new_client_order_id(prefix: str = "bot") -> str:
    """ Unique sortable order ID; prefix + millisecond timestamp + random hex suffix """
    millis = int(time.time() * 1000)
    suffix = secrets.token_hex(2)
    return f"{prefix}-{millis}-{suffix}"

def get_symbol_info(symbol: str) -> dict:
    """ Trading rules for a symbol: minNotional, lotSize, tickSize, contractSize """
    response = run_command("market", "get-symbol-info", "--input", json.dumps({"symbol" : symbol}))
    return response["data"][symbol]

def place_order_preview(order: dict) -> dict:
    """ Validate an order without placing it. Returns previewId and submitToken """
    return run_command("order", "place-preview", "--input", json.dumps(order))

def place_order_submit(order: dict, preview: dict) -> dict:
    """ Submit a previously previewed order """
    submission = {
        **order,
        "previewId" : preview["previewId"],
        "continueConsentId" : preview["confirmation"]["submitToken"]
    }
    return run_command("order", "place", "--input", json.dumps(submission))

def place_order(order: dict) -> dict:
    """ Combined order-placing flow: first preview, then submit. Returns the submit response """
    preview = place_order_preview(order)
    return place_order_submit(order, preview)

def query_order(client_order_id: str) -> dict:
    """ Current state of an order (status, filled quantity, etc.)"""
    return run_command("order", "query", "--input", json.dumps({"clientOrderId" : client_order_id}))

def cancel_order(client_order_id: str) -> dict:
    """ Cancel an open order. Follows the same structure as writing, i.e., preview + submit. """
    cancel_input = {"clientOrderId" : client_order_id}
    preview = run_command("order", "cancel-preview", "--input", json.dumps(cancel_input))
    submission = {
        **cancel_input,
        "previewId" : preview["previewId"],
        "continueConsentId" : preview["confirmation"]["submitToken"]
    }
    return run_command("order", "cancel", "--input", json.dumps(submission))

def snap_down(value : Decimal, step : Decimal) -> Decimal:
    """ Largest multiple of step that is <= value (e.g, price onto tickSize) """
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step

def snap_up(value : Decimal, step : Decimal) -> Decimal:
    """ Smallest multiple of step that >= value (e.g., qty up to lotSize) """
    return (value / step).to_integral_value(rounding=ROUND_UP) * step

def get_positions() -> list:
    """ FOR DIAGNOSIS / TESTING. All open positions (empty list when flat) """
    response = run_command("position", "query")
    return response.get("data", [])

def get_open_positions() -> list:
    """ FOR TRADING. Get positions with nonzero quantity (i.e., truly open exposure) """
    rows = run_command("position", "query").get("data", [])
    return [r for r in rows if Decimal(str(r.get("positionQty", "0"))) != 0] 

def close_position(symbol: str, max_notional: str) -> dict:
    """ Close the open position on a symbol.
    max_notional: safety cap in USDT. Set a bit above position's value """
    preview = run_command("trade", "preview", "--input", json.dumps({
        "targetCapabilityId" : "position.close",
        "symbol" : symbol,
        "reduceOnly" : True,
        "maxNotional" : max_notional
    }))
    submission = {
        "symbol" : symbol,
        "reduceOnly" : True,
        "maxNotional" : max_notional,
        "previewId" : preview["previewId"],
        "continueConsentId" : preview["confirmation"]["submitToken"]
    }
    return run_command("position", "close", "--input", json.dumps(submission))


