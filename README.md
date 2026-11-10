# BLI Micro-Canary

**BLI Micro-Canary** is a lightweight, local-first trade execution script with hard-coded pre-trade safety guardrails for Binance USDⓈ-M Futures (`fapi.binance.com`). It is designed to act as a safe "canary" execution layer for testing webhook alerts or CLI trading signals with micro-sized notional limits, deterministic deduplication, and strict slippage protection—without exposing credentials to external servers or risking catastrophic order errors.

> Looking for institutional-grade automation, multi-exchange routing, dynamic portfolio sizing, and managed execution infrastructure? Check out the full platform at **[blockchainli.com](https://blockchainli.com)**.

---

## What the Project Does

The core module ([`canary_trader.py`](canary_trader.py)) provides a single-path execution pipeline (`execute_canary_order`) that intercepts incoming trade requests before they ever touch the exchange:

1. **Enforces Hard Pre-Trade Checks**: Validates that the request respects the anti-spam cooldown window, targets a whitelisted high-liquidity pair (`BTCUSDT`, `ETHUSDT`), and stays below the hard micro-notional ceiling (`$15.00 USDT`).
2. **Formats Orders Safely**: Queries the live top-of-book (`bookTicker`) to compute a marketable Immediate-or-Cancel (`IOC`) limit price bounded by a tight slippage collar, and generates a deterministic 1-minute bucketed `newClientOrderId` (`generate_client_order_id`) so duplicate triggers are rejected idempotently at the exchange level.
3. **Dispatches Direct Signed REST Calls**: Signs the payload locally using HMAC-SHA256 with your environment-supplied API keys and sends it directly to the Binance API.

---

## Architecture Flow

```text
Incoming Webhook / CLI Command
               │
               ▼
┌───────────────────────────────┐
│     Hard Pre-Trade Enclave    │
│  • Max notional cap (e.g. $15)│
│  • Cooldown timer (1 trade/5m)│
│  • Symbol whitelist check     │
└──────────────┬────────────────┘
               │ (Passes checks)
               ▼
┌───────────────────────────────┐
│       Order Formatter         │
│  • Deterministic order ID     │
│  • Marketable limit collar    │
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│     Direct Signed REST API    │  ──► Binance API
│     (Isolated Local Keys)     │
└───────────────────────────────┘
```

---

## Safety Guardrails & Limitations

By design, this open-source micro-canary enforces strict guardrails to protect accounts from misconfigured webhooks, runaway loops, or illiquid order books:

- **Hard Notional Cap (Micro-Sizing Only)**
  Enforces a hard ceiling on order value directly in the validation code (e.g., maximum trade size clamped at `$15.00 USDT` or `10%` of equity). If a webhook or CLI input sends `contracts: 10 BTC`, the script rejects it immediately before contacting the exchange.
- **Aggressive Cooldown Timers & Anti-Spam**
  Maintains an in-memory timestamp lock (e.g., minimum `60` to `300` seconds between order submissions per symbol). Even if an external TradingView alert misfires 50 times in a second, the script drops 49 of them.
- **Symbol Whitelist**
  Limits execution strictly to high-liquidity pairs (e.g., `BTCUSDT`, `ETHUSDT`) to prevent users from accidentally buying illiquid low-cap tokens where slippage is catastrophic.
- **Marketable Limit Collar (No Raw Market Orders)**
  Never submits naked `MARKET` orders. Forces the script to fetch the best ask/bid, calculate an Immediate-or-Cancel (`IOC`) limit price bounded by a maximum slippage cap (e.g., `0.05%`–`0.10%`), and reject if prices drift.
- **Local-Only Credentials**
  Requires users to supply their own local environment variables (`BINANCE_API_KEY`, `BINANCE_API_SECRET`). The script does not touch external third-party servers, has no phone-home telemetry, and handles credentials entirely in local system memory.

---

## Quick Start

### 1. Prerequisites

Install the `requests` library in your Python environment:

```bash
pip install requests
```

### 2. Set Local Credentials

Export your Binance API credentials in your local shell session:

```bash
export BINANCE_API_KEY="your_api_key_here"
export BINANCE_API_SECRET="your_api_secret_here"
```

### 3. Execute a Canary Order

```python
from canary_trader import execute_canary_order

# Submit a $10 USDT BUY order on BTCUSDT within safety bounds
response = execute_canary_order(
    symbol="BTCUSDT",
    action="BUY",
    target_usdt=10.0,
)
print(response)
```

---

## Full Platform

This repository is a minimal, self-contained micro-canary for local testing and verification. For production-scale signal execution, advanced risk management, multi-venue orchestration, and real-time analytics, visit **[blockchainli.com](https://blockchainli.com)**.
