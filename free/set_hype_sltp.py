"""HYPE long positionにSLとTPを追加する。"""
import os, json, sys
import urllib.request, urllib.error
from ulid import ULID

API_KEY = open("/Users/naoto/propr/free/.env").read().strip().split("=", 1)[1]
BASE = "https://api.propr.xyz/v1"
ACCOUNT_ID = "urn:prp-account:xREXiJC2b4He"
POSITION_ID = "urn:prp-position:WMHnYkcJ65Nh"
QTY = "13.877324451845684152"

def post(path, body):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json", "User-Agent": "curl/8.4.0"},
        method="POST",
    )
    try:
        return json.loads(urllib.request.urlopen(req).read())
    except urllib.error.HTTPError as e:
        return {"_http_error": e.code, "_body": e.read().decode()}

sl = {
    "orders": [{
        "accountId": ACCOUNT_ID,
        "intentId": str(ULID()),
        "positionId": POSITION_ID,
        "exchange": "hyperliquid",
        "productType": "perp",
        "type": "stop_market",
        "side": "sell",
        "positionSide": "short",
        "asset": "HYPE",
        "base": "HYPE",
        "quote": "USDC",
        "quantity": QTY,
        "triggerPrice": "70.50",
        "reduceOnly": True,
        "closePosition": True,
        "timeInForce": "GTC",
    }]
}

tp = {
    "orders": [{
        "accountId": ACCOUNT_ID,
        "intentId": str(ULID()),
        "positionId": POSITION_ID,
        "exchange": "hyperliquid",
        "productType": "perp",
        "type": "take_profit_market",
        "side": "sell",
        "positionSide": "short",
        "asset": "HYPE",
        "base": "HYPE",
        "quote": "USDC",
        "quantity": QTY,
        "triggerPrice": "76.00",
        "reduceOnly": True,
        "closePosition": True,
        "timeInForce": "GTC",
    }]
}

print("=== Placing Stop Loss @ $70.50 ===")
print(json.dumps(post(f"/accounts/{ACCOUNT_ID}/orders", sl), indent=2))
print("\n=== Placing Take Profit @ $76.00 ===")
print(json.dumps(post(f"/accounts/{ACCOUNT_ID}/orders", tp), indent=2))
