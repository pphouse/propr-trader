"""Hyperliquid 過去データ取得 + ローカル cache.

データ:
- candleSnapshot: 1h 足で最大5000本 (≈208日)
- fundingHistory: 1h 単位、 24h以上遡れる (制約は要確認)

cache: backtest/cache/{asset}_{interval}_{kind}.json
"""
import json
import time
import urllib.request
from pathlib import Path

CACHE_DIR = Path(__file__).parent / 'cache'
CACHE_DIR.mkdir(exist_ok=True)
HL_INFO = 'https://api.hyperliquid.xyz/info'


def hl(payload):
    req = urllib.request.Request(HL_INFO,
        data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def fetch_candles(asset, interval, hours_back, use_cache=True):
    """Hyperliquid candleSnapshot. 1 リクエスト最大 5000 本。"""
    cache_path = CACHE_DIR / f'{asset}_{interval}_{hours_back}h_candles.json'
    if use_cache and cache_path.exists():
        return json.loads(cache_path.read_text())

    now_ms = int(time.time() * 1000)
    start_ms = now_ms - hours_back * 3600 * 1000
    r = hl({'type': 'candleSnapshot',
            'req': {'coin': asset, 'interval': interval,
                    'startTime': start_ms, 'endTime': now_ms}})
    if not r:
        return []
    cache_path.write_text(json.dumps(r))
    return r


def fetch_funding_history(asset, hours_back, use_cache=True):
    """fundingHistory: 1h ごとの funding rate。 startTime 指定可能。"""
    cache_path = CACHE_DIR / f'{asset}_funding_{hours_back}h.json'
    if use_cache and cache_path.exists():
        return json.loads(cache_path.read_text())

    now_ms = int(time.time() * 1000)
    start_ms = now_ms - hours_back * 3600 * 1000
    # fundingHistory は 1リクエストの上限がドキュメント明記なし、 大きめ取得を試す
    # 必要ならページング
    all_records = []
    cursor = start_ms
    pages = 0
    while True:
        r = hl({'type': 'fundingHistory', 'coin': asset,
                'startTime': cursor, 'endTime': now_ms})
        if not r:
            break
        all_records.extend(r)
        pages += 1
        if len(r) < 500:  # ページ末端
            break
        if pages > 20:
            break
        last_t = max(rec['time'] for rec in r)
        if last_t <= cursor:
            break
        cursor = last_t + 1
        time.sleep(0.2)
    # dedup
    seen = set()
    uniq = []
    for rec in sorted(all_records, key=lambda x: x['time']):
        if rec['time'] in seen:
            continue
        seen.add(rec['time'])
        uniq.append(rec)
    cache_path.write_text(json.dumps(uniq))
    return uniq


def fetch_all(assets, hours_back=5000, candle_interval='1h'):
    """全銘柄分の candle + funding を一括取得。"""
    out = {}
    for a in assets:
        print(f'  [{a}] candles...', end=' ', flush=True)
        candles = fetch_candles(a, candle_interval, hours_back)
        print(f'{len(candles)} bars', end=' ')
        print(f'funding...', end=' ', flush=True)
        funding = fetch_funding_history(a, hours_back)
        print(f'{len(funding)} records')
        out[a] = {'candles': candles, 'funding': funding}
        time.sleep(0.5)
    return out


if __name__ == '__main__':
    # スモークテスト
    assets = ['BTC', 'ETH', 'SOL', 'HYPE', 'LINK', 'ZEC', 'WLD', 'NEAR']
    print(f'Fetching 1h candles + funding for {len(assets)} assets, 5000 hours (~208 days)...')
    data = fetch_all(assets, hours_back=5000, candle_interval='1h')
    print()
    print('Summary:')
    for a, d in data.items():
        candles = d['candles']
        funding = d['funding']
        if candles:
            first_t = candles[0]['t']
            last_t = candles[-1]['t']
            days = (last_t - first_t) / (1000 * 86400)
            print(f'  {a:6} candles={len(candles)} ({days:.1f}d) funding={len(funding)}')
