import hashlib
import hmac
import os
import time
import requests


def load_dotenv(path: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")) -> None:
    """Load KEY=VALUE pairs from a local .env file. Existing env vars take precedence."""
    if not os.path.isfile(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip().removeprefix("export ").strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


load_dotenv()

# ----------------- HARD SAFETY BOUNDS (OPEN SOURCE GUARDRAILS) -----------------
MAX_ALLOWED_NOTIONAL_USDT = 100.0  # Cannot execute orders exceeding $15
MAX_SLIPPAGE_PCT = 0.001          # 0.1% max price deviation collar
COOLDOWN_SECONDS = 60             # Strict rate throttle
ALLOWED_SYMBOLS = {"BTCUSDT", "ETHUSDT"}

LAST_ORDER_TIMESTAMP = 0.0

# USDⓈ-M Futures endpoints. Set BINANCE_ENV=demo to use Binance Demo Trading.
BASE_URLS = {
    "live": "https://fapi.binance.com",
    "demo": "https://demo-fapi.binance.com",
}


# Credential env vars per environment (demo keys are created inside Binance Demo Trading).
CREDENTIAL_VARS = {
    "live": ("BINANCE_API_KEY", "BINANCE_API_SECRET"),
    "demo": ("BINANCE_DEMO_API_KEY", "BINANCE_DEMO_API_SECRET"),
}


def get_env() -> str:
    env = os.getenv("BINANCE_ENV", "live").strip().lower()
    if env not in BASE_URLS:
        raise ValueError(f"Invalid BINANCE_ENV '{env}'. Use one of: {', '.join(BASE_URLS)}.")
    return env


def get_base_url() -> str:
    return BASE_URLS[get_env()]


def get_credentials() -> tuple[str, str]:
    key_var, secret_var = CREDENTIAL_VARS[get_env()]
    api_key, api_secret = os.getenv(key_var), os.getenv(secret_var)
    if not api_key or not api_secret:
        raise EnvironmentError(f"Missing local exchange credentials: set {key_var} and {secret_var}.")
    return api_key, api_secret

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

    api_key, api_secret = get_credentials()

    base_url = get_base_url()

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