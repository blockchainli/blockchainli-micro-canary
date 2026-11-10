import hashlib
import hmac
import os
import time
import requests

# ----------------- HARD SAFETY BOUNDS (OPEN SOURCE GUARDRAILS) -----------------
MAX_ALLOWED_NOTIONAL_USDT = 15.0  # Cannot execute orders exceeding $15
MAX_SLIPPAGE_PCT = 0.001          # 0.1% max price deviation collar
COOLDOWN_SECONDS = 60             # Strict rate throttle
ALLOWED_SYMBOLS = {"BTCUSDT", "ETHUSDT"}

LAST_ORDER_TIMESTAMP = 0.0

def generate_client_order_id(symbol: str, action: str) -> str:
    """Deterministic hash preventing duplicate exchange-side executions."""
    window = int(time.time() // 60)
    raw = f"canary:{symbol}:{action}:{window}".encode()
    return f"x-canary-{hashlib.sha256(raw).hexdigest()[:16]}"

def execute_canary_order(symbol: str, action: str, target_usdt: float):
    global LAST_ORDER_TIMESTAMP

    # 1. Check Anti-Spam Cooldown
    now = time.time()
    if now - LAST_ORDER_TIMESTAMP < COOLDOWN_SECONDS:
        raise RuntimeError(f"Rate limited: Must wait {int(COOLDOWN_SECONDS - (now - LAST_ORDER_TIMESTAMP))}s between trades.")

    # 2. Check Symbol & Sizing Guardrails
    if symbol not in ALLOWED_SYMBOLS:
        raise ValueError(f"Symbol {symbol} not in approved safety whitelist.")
    
    if target_usdt > MAX_ALLOWED_NOTIONAL_USDT:
        raise ValueError(f"Requested ${target_usdt} exceeds maximum safety ceiling of ${MAX_ALLOWED_NOTIONAL_USDT}.")

    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    if not api_key or not api_secret:
        raise EnvironmentError("Missing local exchange credentials.")

    base_url = "https://fapi.binance.com"  # USDⓈ-M Futures (or Testnet)

    # 3. Read Order Book for Slippage Collar
    book = requests.get(f"{base_url}/fapi/v1/ticker/bookTicker?symbol={symbol}").json()
    best_price = float(book["askPrice"] if action == "BUY" else book["bidPrice"])

    # Calculate Marketable Limit bounds (IOC)
    if action == "BUY":
        limit_price = round(best_price * (1 + MAX_SLIPPAGE_PCT), 2)
    else:
        limit_price = round(best_price * (1 - MAX_SLIPPAGE_PCT), 2)

    quantity = round(target_usdt / best_price, 3)
    client_order_id = generate_client_order_id(symbol, action)

    # 4. Dispatch Signed REST Call to Exchange
    params = {
        "symbol": symbol,
        "side": action,
        "type": "LIMIT",
        "timeInForce": "IOC",  # Fill immediately within limit or cancel
        "quantity": quantity,
        "price": limit_price,
        "newClientOrderId": client_order_id,
        "timestamp": int(time.time() * 1000),
    }

    query_str = "&".join([f"{k}={v}" for k, v in params.items()])
    signature = hmac.new(api_secret.encode(), query_str.encode(), hashlib.sha256).hexdigest()
    params["signature"] = signature

    headers = {"X-MBX-APIKEY": api_key}
    res = requests.post(f"{base_url}/fapi/v1/order", params=params, headers=headers)
    
    LAST_ORDER_TIMESTAMP = time.time()
    return res.json()