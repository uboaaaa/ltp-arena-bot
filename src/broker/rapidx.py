"""
RapidX CLI Wrapper.
All interactions with the trading platform go through run_command()
"""

import json
import subprocess

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
    """ Account summary: equity, balances, margin """
    return run_command("portfolio", "overview")

