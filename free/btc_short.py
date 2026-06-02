"""BTC short エントリー + SL/TP を bracket order で発注。"""
import api
from decimal import Decimal

# 現在価格確認
prices = api.hl_prices(["BTC"])
btc = prices["BTC"]
print(f"BTC mid: ${btc}")

# サイズ: マージン$400, 5xレバ -> notional $2000
# qty = 2000 / btc_price, 小数点3桁丸め
qty = (Decimal("2000") / btc).quantize(Decimal("0.001"))
print(f"size: {qty} BTC (notional ~${qty*btc:.0f}, margin ~${qty*btc/5:.0f})")

# SL/TP価格 (entry想定 = 現在のmid)
sl = (btc * Decimal("1.0165")).quantize(Decimal("0.5"))  # +1.65%
tp = (btc * Decimal("0.957")).quantize(Decimal("0.5"))   # -4.3%

print(f"SL: ${sl} (loss ~${(sl-btc)*qty:.2f})")
print(f"TP: ${tp} (profit ~${(btc-tp)*qty:.2f})")

# bracket order: entry + SL + TP を同じ orderGroupIdで送る
# entry: sell market (short open)
# SL: stop_market buy (close short = buy+long方向ラベル)
# TP: take_profit_market buy
orders = [
    {
        "asset": "BTC",
        "type": "market",
        "side": "sell",
        "positionSide": "short",
        "timeInForce": "IOC",
        "quantity": str(qty),
        "reduceOnly": False,
        "closePosition": False,
    },
    {
        "asset": "BTC",
        "type": "stop_market",
        "side": "buy",
        "positionSide": "long",
        "quantity": str(qty),
        "triggerPrice": str(sl),
        "reduceOnly": True,
        "closePosition": True,
    },
    {
        "asset": "BTC",
        "type": "take_profit_market",
        "side": "buy",
        "positionSide": "long",
        "quantity": str(qty),
        "triggerPrice": str(tp),
        "reduceOnly": True,
        "closePosition": True,
    },
]

import json
r = api.place(orders)
print(json.dumps(r, indent=2))
