"""propr API共通ライブラリ。"""
import json
import os
import urllib.request, urllib.error
from decimal import Decimal
from pathlib import Path
from ulid import ULID


def _load_api_key():
    # 1) 環境変数優先 (routine cloud / cron systemd 等)
    key = os.environ.get("PROPR_API_KEY") or os.environ.get("PERPR_API_KEY")
    if key:
        return key.strip()
    # 2) フォールバック: ローカル .env ファイル (repo root or free/ 配下を探す)
    for candidate in [
        Path(__file__).parent / ".env",
        Path(__file__).parent.parent / ".env",
        Path("/Users/naoto/propr/free/.env"),
    ]:
        if candidate.exists():
            line = candidate.read_text().strip().split("\n")[0]
            return line.split("=", 1)[1].strip()
    raise RuntimeError(
        "PROPR_API_KEY not found. Set env var PROPR_API_KEY=pk_live_..."
        " or place .env file with PROPR_API_KEY=... near api.py"
    )


API_KEY = _load_api_key()
BASE = "https://api.propr.xyz/v1"
ACCOUNT_ID = os.environ.get("PROPR_ACCOUNT_ID", "urn:prp-account:xREXiJC2b4He")
HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json",
    "User-Agent": "curl/8.4.0",
}

def request(method, path, body=None, params=None):
    url = f"{BASE}{path}"
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode(params)
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        return urllib.request.urlopen(req).read().decode()
    except urllib.error.HTTPError as e:
        return json.dumps({"_http": e.code, "_body": e.read().decode()})

def get(path, **params):
    return json.loads(request("GET", path, params=params or None))

def post(path, body):
    return json.loads(request("POST", path, body=body))

def put(path, body):
    return json.loads(request("PUT", path, body=body))

def hl_prices(symbols=None):
    """Hyperliquid mid prices."""
    req = urllib.request.Request(
        "https://api.hyperliquid.xyz/info",
        data=json.dumps({"type": "allMids"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    r = json.loads(urllib.request.urlopen(req).read())
    if symbols:
        return {s: Decimal(r[s]) for s in symbols if s in r}
    return r

def place(orders):
    """orders: list of dicts. Auto-fills boilerplate."""
    body_orders = []
    for o in orders:
        full = {
            "accountId": ACCOUNT_ID,
            "intentId": str(ULID()),
            "exchange": "hyperliquid",
            "productType": "perp",
            "quote": "USDC",
            "timeInForce": "GTC",
            **o,
        }
        full.setdefault("base", full["asset"])
        body_orders.append(full)
    body = {"orders": body_orders}
    if len(body_orders) > 1:
        body["orderGroupId"] = str(ULID())
    return post(f"/accounts/{ACCOUNT_ID}/orders", body)

def positions(status="open"):
    return get(f"/accounts/{ACCOUNT_ID}/positions", status=status)

def open_orders():
    return get(f"/accounts/{ACCOUNT_ID}/orders", status="open")

def account():
    r = get("/challenge-attempts", status="active")
    return r["data"][0]["account"]
