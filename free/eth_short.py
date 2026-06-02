"""ETH short bracket order (notional $1500, 5xレバ, margin $300)."""
import api, json
from decimal import Decimal

prices = api.hl_prices(["ETH"])
eth = prices["ETH"]
print(f"ETH mid: ${eth}")

qty = (Decimal("1500") / eth).quantize(Decimal("0.01"))
print(f"size: {qty} ETH (notional ~${qty*eth:.0f}, margin ~${qty*eth/5:.0f})")

sl = (eth * Decimal("1.0175")).quantize(Decimal("0.1"))
tp = (eth * Decimal("0.952")).quantize(Decimal("0.1"))
print(f"SL: ${sl} (loss ~${(sl-eth)*qty:.2f})")
print(f"TP: ${tp} (profit ~${(eth-tp)*qty:.2f})")

orders = [
    {
        "asset": "ETH",
        "type": "market",
        "side": "sell",
        "positionSide": "short",
        "timeInForce": "IOC",
        "quantity": str(qty),
        "reduceOnly": False,
    },
    {
        "asset": "ETH",
        "type": "stop_market",
        "side": "buy",
        "positionSide": "long",
        "quantity": str(qty),
        "triggerPrice": str(sl),
        "reduceOnly": True,
        "closePosition": True,
    },
    {
        "asset": "ETH",
        "type": "take_profit_market",
        "side": "buy",
        "positionSide": "long",
        "quantity": str(qty),
        "triggerPrice": str(tp),
        "reduceOnly": True,
        "closePosition": True,
    },
]
r = api.place(orders)
print(json.dumps(r, indent=2)[:1500])
