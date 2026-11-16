from canary_trader import execute_canary_order

# Submit a $10 USDT BUY order on ETHUSDT within safety bounds
response = execute_canary_order(
    symbol="ETHUSDT",
    action="BUY",
    target_usdt=25.0,
)
print(response)