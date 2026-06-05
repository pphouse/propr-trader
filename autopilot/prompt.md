# Propr.xyz 自動売買オペレーター — Multi-Strategy Phase 2.5

## 戦略コア

**銘柄別に最適化された 7つの戦略を並走** (1100 configs × 8 assets backtest結果)。 各銘柄に専用の entry signal、 SL/TP、 出口条件。

backtest 統合結果:
- **EV/trade +$3.38** (208日 OOS、 7 assets × 3 pos 並列、 連敗ストッパー)
- **maxDD $189** (残高 $5,000 に対して 4%、 breach floor まで超余裕)
- 推定 75日で profit target +$500 達成

## 銘柄別戦略テーブル (これが全て)

| 銘柄 | 戦略 | パラメータ | SL% | TP% | R:R | OOS EV |
|---|---|---|---|---|---|---|
| **BTC** | funding_extreme (逆張り) | threshold=0.002%/hr | 2.0 | 6.0 | 3.0 | +$15.75 |
| **ETH** | ema_cross | fast=20, slow=50 | 3.0 | 6.0 | 2.0 | +$5.25 |
| **SOL** | ema_cross | fast=8, slow=21 | 3.0 | 6.0 | 2.0 | +$9.29 |
| **HYPE** | funding_momentum (同方向) | lb=5, mom≥1.0%, fund≥0.002 | 3.0 | 6.0 | 2.0 | +$15.24 |
| **LINK** | RSI extreme (逆張り) | p=7, OB=70, OS=30 | 3.0 | 6.0 | 2.0 | +$1.39 |
| **ZEC** | funding_followthrough (順張り) | lb=5, mom≥0.5%, fund≥0.001 | 3.0 | 6.0 | 2.0 | +$10.54 |
| **WLD** | volume_spike_momentum | vl=5, vm≥2.0x, ml=5, mom≥0.5 | 4.0 | 4.0 | 1.0 | +$8.08 |
| **NEAR** | volume_spike_momentum | vl=10, vm≥3.0x, ml=5, mom≥0.5 | 4.0 | 4.0 | 1.0 | +$3.88 |

**SL/TP は銘柄別に違う** (BTC は R:R 3.0、 WLD/NEAR は R:R 1.0)。 これは backtest で各銘柄の値動き特性に最適化された結果、 統一しない。

---

## 厳守ルール

| 項目 | 値 | 理由 |
|---|---|---|
| Profit target | +$500 (残高 $5,500) | propr 1-Step Starter |
| Server Daily Loss上限 | -$150 | propr 永久breach |
| Server Max DD floor | $4,700 | propr 永久breach |
| **ノーション/trade** | **$500** 固定 | SL hit損失 = $10-20、 リスク管理 |
| **同時アクティブポジ** | **最大3つ** | backtest最適、 3pos でEV最大化 |
| **方向別 notional 制限** | 同方向 ≤ $1,500 | 相関リスク管理 (3×$500) |
| **自主ブレーキ: 残高** | ≤ $4,800 | breach floor $100 手前 |
| **自主ブレーキ: 当日累積** | ≤ -$100 | server breach -$150 の 手前 $50 |
| **自主ブレーキ: 連敗** | 直近 3連敗 → 6h停止 | backtest最大連敗 31 → 6h cooldown |
| **既存ポジ調整** | **完全に何もしない** | TP/SL固定、 建値移動禁止 (実効R:R 1.79→0.18破壊) |

---

## API 罠

1. `buy ↔ long` / `sell ↔ short`
2. SL/TP は `side` を反対、 `reduceOnly=True closePosition=True`
3. `status=pending` = conditional 正常
4. レバレッジ: BTC/ETH 5x、 他crypto 2x (server自動)

## 環境

- accountId: env var `PROPR_ACCOUNT_ID` (`urn:prp-account:6JvMREehs6yi`)
- APIキー: env var `PROPR_API_KEY`
- ヘルパー: `free/api.py`

---

## 実行手順 (turns 10以下)

### Step 1: snapshot 取得 (全銘柄シグナル評価)

```bash
cd free && python3 << 'PY'
import sys, json, urllib.request, time, os
from datetime import datetime, timezone
sys.path.insert(0, '.')
import api

# ----- propr account -----
acc = api.account()
pos_open = [p for p in api.positions(status='open')['data'] if float(p['quantity']) != 0]
orders = api.get('/accounts/' + api.ACCOUNT_ID + '/orders', limit=30)['data']
trades = api.get('/accounts/' + api.ACCOUNT_ID + '/trades', limit=50)['data']

def hl(payload):
    req = urllib.request.Request('https://api.hyperliquid.xyz/info',
        data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())

# ----- 銘柄別戦略 spec -----
ASSET_STRATEGY = {
    'BTC':  {'type': 'funding_extreme',       'threshold_pct_per_hr': 0.002, 'sl': 2.0, 'tp': 6.0},
    'ETH':  {'type': 'ema_cross',             'fast': 20, 'slow': 50,         'sl': 3.0, 'tp': 6.0},
    'SOL':  {'type': 'ema_cross',             'fast': 8,  'slow': 21,         'sl': 3.0, 'tp': 6.0},
    'HYPE': {'type': 'funding_momentum',      'lookback': 5, 'mom_th': 1.0, 'fund_th': 0.002, 'sl': 3.0, 'tp': 6.0},
    'LINK': {'type': 'rsi',                   'period': 7, 'ob': 70, 'os': 30, 'sl': 3.0, 'tp': 6.0},
    'ZEC':  {'type': 'funding_followthrough', 'lookback': 5, 'mom_th': 0.5, 'fund_th': 0.001, 'sl': 3.0, 'tp': 6.0},
    'WLD':  {'type': 'volume_spike_momentum', 'vol_lb': 5,  'vol_mult': 2.0, 'mom_lb': 5, 'mom_th': 0.5, 'sl': 4.0, 'tp': 4.0},
    'NEAR': {'type': 'volume_spike_momentum', 'vol_lb': 10, 'vol_mult': 3.0, 'mom_lb': 5, 'mom_th': 0.5, 'sl': 4.0, 'tp': 4.0},
}

# 各銘柄の最新bar 計算
now_ms = int(time.time() * 1000)
strategy_signals = {}
mkt_meta = hl({'type':'metaAndAssetCtxs'})
universe_idx = {u['name']: i for i, u in enumerate(mkt_meta[0]['universe'])}

for asset, spec in ASSET_STRATEGY.items():
    try:
        # 共通: 1h candle 最大 60本 取得 (EMA50対応のため余裕)
        cs = hl({'type':'candleSnapshot', 'req':{'coin':asset, 'interval':'1h',
                  'startTime': now_ms - 70*3600*1000, 'endTime': now_ms}})
        if not cs or len(cs) < 50:
            strategy_signals[asset] = {'error': 'not enough candles'}
            continue
        closes = [float(c['c']) for c in cs]
        vols   = [float(c['v']) for c in cs]
        cur_close = closes[-1]
        
        # 現在 funding (asset ctx から)
        ctx_idx = universe_idx.get(asset)
        funding_now = float(mkt_meta[1][ctx_idx].get('funding', 0)) * 100 if ctx_idx is not None else 0  # %/hr
        
        signal = None
        details = {'cur_close': cur_close, 'funding_now_pct': round(funding_now, 4)}
        
        if spec['type'] == 'funding_extreme':
            if funding_now >= spec['threshold_pct_per_hr']:
                signal = 'short'
            elif funding_now <= -spec['threshold_pct_per_hr']:
                signal = 'long'
            details['threshold'] = spec['threshold_pct_per_hr']
        
        elif spec['type'] == 'ema_cross':
            def ema(vals, n):
                k = 2/(n+1); e=vals[0]; out=[e]
                for v in vals[1:]: e = v*k + e*(1-k); out.append(e)
                return out
            ef = ema(closes, spec['fast'])
            es = ema(closes, spec['slow'])
            # 直前との符号変化でクロス検出
            diff_cur = ef[-1] - es[-1]
            diff_prev = ef[-2] - es[-2]
            if diff_cur > 0 and diff_prev <= 0:
                signal = 'long'
            elif diff_cur < 0 and diff_prev >= 0:
                signal = 'short'
            details['ema_fast'] = round(ef[-1], 2)
            details['ema_slow'] = round(es[-1], 2)
            details['cross_diff'] = round(diff_cur, 2)
        
        elif spec['type'] == 'funding_momentum':
            mom_pct = (cur_close / closes[-1-spec['lookback']] - 1) * 100 if len(closes) > spec['lookback'] else 0
            mom_side = 'long' if mom_pct >= spec['mom_th'] else ('short' if mom_pct <= -spec['mom_th'] else None)
            fund_side = 'short' if funding_now >= spec['fund_th'] else ('long' if funding_now <= -spec['fund_th'] else None)
            if mom_side and fund_side and mom_side == fund_side:
                signal = mom_side
            details['mom_pct'] = round(mom_pct, 3)
            details['mom_th'] = spec['mom_th']; details['fund_th'] = spec['fund_th']
        
        elif spec['type'] == 'funding_followthrough':
            mom_pct = (cur_close / closes[-1-spec['lookback']] - 1) * 100 if len(closes) > spec['lookback'] else 0
            if funding_now >= spec['fund_th'] and mom_pct >= spec['mom_th']:
                signal = 'long'
            elif funding_now <= -spec['fund_th'] and mom_pct <= -spec['mom_th']:
                signal = 'short'
            details['mom_pct'] = round(mom_pct, 3)
        
        elif spec['type'] == 'rsi':
            period = spec['period']
            if len(closes) < period + 2:
                strategy_signals[asset] = {'error': 'rsi needs more candles'}
                continue
            gains, losses = [], []
            for i in range(1, len(closes)):
                d = closes[i]-closes[i-1]
                gains.append(max(d, 0)); losses.append(max(-d, 0))
            avg_g = sum(gains[:period])/period
            avg_l = sum(losses[:period])/period
            for i in range(period, len(gains)):
                avg_g = (avg_g*(period-1) + gains[i])/period
                avg_l = (avg_l*(period-1) + losses[i])/period
            rs = avg_g/avg_l if avg_l > 0 else 100
            rsi = 100 - 100/(1+rs)
            if rsi >= spec['ob']:
                signal = 'short'
            elif rsi <= spec['os']:
                signal = 'long'
            details['rsi'] = round(rsi, 1)
        
        elif spec['type'] == 'volume_spike_momentum':
            vol_window = vols[-(spec['vol_lb']+1):-1]
            med_vol = sorted(vol_window)[len(vol_window)//2] if vol_window else 0
            cur_vol = vols[-1]
            vol_mult = cur_vol / med_vol if med_vol > 0 else 0
            mom_pct = (cur_close / closes[-1-spec['mom_lb']] - 1) * 100 if len(closes) > spec['mom_lb'] else 0
            if vol_mult >= spec['vol_mult'] and abs(mom_pct) >= spec['mom_th']:
                signal = 'long' if mom_pct > 0 else 'short'
            details['vol_mult'] = round(vol_mult, 2)
            details['mom_pct'] = round(mom_pct, 3)
        
        strategy_signals[asset] = {
            'strategy': spec['type'],
            'signal': signal,
            'sl_pct': spec['sl'], 'tp_pct': spec['tp'],
            **details,
        }
    except Exception as e:
        strategy_signals[asset] = {'error': str(e)[:60]}

# ----- 連敗カウント + 自主ブレーキ -----
today = datetime.utcnow().date().isoformat()
realized_today = sum(float(t['realizedPnl']) for t in trades if t.get('executedAt','')[:10] == today)
closed = [t for t in trades if float(t.get('realizedPnl', 0)) != 0]
closed_sorted = sorted(closed, key=lambda x: x['executedAt'])
last_n = closed_sorted[-10:]
recent_consec_losses = 0
for t in reversed(last_n):
    if float(t['realizedPnl']) < 0:
        recent_consec_losses += 1
    else:
        break
hours_since_3rd_loss = None
if recent_consec_losses >= 3:
    last_loss_at = last_n[-1]['executedAt']
    hours_since_3rd_loss = (datetime.now(timezone.utc) - datetime.fromisoformat(last_loss_at.replace('Z','+00:00'))).total_seconds() / 3600

# 方向別 notional
long_total = sum(float(p['quantity']) * float(p['markPrice']) for p in pos_open if p['positionSide']=='long')
short_total = sum(float(p['quantity']) * float(p['markPrice']) for p in pos_open if p['positionSide']=='short')

mb = float(acc['marginBalance'])
snapshot = {
    'now_utc': datetime.now(timezone.utc).isoformat(),
    'account': {
        'marginBalance': mb,
        'equity': round(mb + float(acc['totalUnrealizedPnl']), 2),
        'distance_to_breach': round(mb + float(acc['totalUnrealizedPnl']) - 4700, 2),
        'realized_today': round(realized_today, 4),
    },
    'self_brakes': {
        'balance_too_low': mb <= 4800,
        'daily_loss_too_close_to_breach': realized_today <= -100,
        'consecutive_losses_recent': recent_consec_losses,
        'loss_streak_stopper_active': recent_consec_losses >= 3 and (hours_since_3rd_loss is None or hours_since_3rd_loss < 6),
        'hours_since_3rd_loss': round(hours_since_3rd_loss, 2) if hours_since_3rd_loss is not None else None,
        'open_position_count': len(pos_open),
        'long_notional': round(long_total, 2),
        'short_notional': round(short_total, 2),
        'open_position_assets': [p['asset'] for p in pos_open],
    },
    'positions_open': [{'asset':p['asset'],'side':p['positionSide'],'qty':p['quantity'],
                        'entry':p['entryPrice'],'mark':p['markPrice'],'uPnL':p['unrealizedPnl']}
                       for p in pos_open],
    'pending_protective_orders': [{'asset':o['asset'],'type':o['type'],'trigger':o['triggerPrice'],
                                   'qty':o['quantity'],'orderId':o['orderId']}
                                  for o in orders if o['status']=='pending'],
    'recent_trades_5': [{'asset':t['asset'],'type':t['type'],'side':t['side'],
                         'price':t['price'],'pnl':t['realizedPnl'],
                         'at':t['executedAt'][:19]} for t in trades[:5]],
    'strategy_signals': strategy_signals,
}
with open('/tmp/propr_current.json','w') as f:
    json.dump(snapshot, f, indent=2, default=str)

print(f'snapshot ok eq=${snapshot["account"]["equity"]:.2f} pos={len(pos_open)}')
print(f'brakes: balLow={snapshot["self_brakes"]["balance_too_low"]} dailyClose={snapshot["self_brakes"]["daily_loss_too_close_to_breach"]} streakStop={snapshot["self_brakes"]["loss_streak_stopper_active"]}')
print(f'signals:')
for a, sig in strategy_signals.items():
    if 'error' in sig:
        print(f'  {a}: ERROR {sig["error"]}')
    else:
        print(f'  {a:5} [{sig["strategy"]:25}] signal={sig["signal"]}')
PY
```

### Step 2: 判断ロジック (機械的)

`Read /tmp/propr_current.json` で snapshot 確認。

**エントリー条件 (各 asset で評価)**:
1. `self_brakes.balance_too_low == false`
2. `self_brakes.daily_loss_too_close_to_breach == false`
3. `self_brakes.loss_streak_stopper_active == false`
4. `self_brakes.open_position_count < 3`
5. **その asset の `strategy_signals[asset].signal` が 'long' or 'short'**
6. **その asset で既にポジ持ってない** (重複entry防止: `self_brakes.open_position_assets` 確認)
7. **方向別 notional制限**: signal が long なら `long_notional + 500 <= 1500`、 short も同様

→ 全てクリアした最初の銘柄に entry (複数同時にシグナル出る場合は table上位順: BTC, ETH, SOL, HYPE, LINK, ZEC, WLD, NEAR)

### Step 3: 執行

```python
import sys; sys.path.insert(0, "free")
import api

# 例: snapshot から取ってきた asset/signal/spec
ASSET, SIDE = 'BTC', 'short'  # snapshot.strategy_signals から
PRICE = ...  # snapshot.strategy_signals[ASSET].cur_close
SL_PCT, TP_PCT = ..., ...  # snapshot.strategy_signals[ASSET].sl_pct/tp_pct
NOTIONAL = 500

qty = round(NOTIONAL / PRICE, 4 if ASSET == 'BTC' else (3 if ASSET in {'ETH','SOL','HYPE','BCH','LTC','XMR','AAVE'} else 1))
if SIDE == 'long':
    sl_price = round(PRICE * (1 - SL_PCT/100), 4)
    tp_price = round(PRICE * (1 + TP_PCT/100), 4)
    es, cs_ = 'buy', 'sell'; ep, cp = 'long', 'short'
else:
    sl_price = round(PRICE * (1 + SL_PCT/100), 4)
    tp_price = round(PRICE * (1 - TP_PCT/100), 4)
    es, cs_ = 'sell', 'buy'; ep, cp = 'short', 'long'

api.place([
  {"asset":ASSET,"type":"market","side":es,"positionSide":ep,
   "timeInForce":"IOC","quantity":str(qty),"reduceOnly":False},
  {"asset":ASSET,"type":"stop_market","side":cs_,"positionSide":cp,
   "quantity":str(qty),"triggerPrice":str(sl_price),"reduceOnly":True,"closePosition":True},
  {"asset":ASSET,"type":"take_profit_market","side":cs_,"positionSide":cp,
   "quantity":str(qty),"triggerPrice":str(tp_price),"reduceOnly":True,"closePosition":True},
])
```

### Step 4: 出力サマリ

```markdown
### 📊 現状
- eq $X.XX  realized_today $X.XX  posOpen=X (long $X / short $X)
- self_brakes: balLow=X dailyClose=X streakStop=X consec=X

### 🧠 シグナル
- BTC [funding_extreme]: signal=short (funding +0.003%>0.002)
- ETH [ema_cross]: signal=None (no cross)
- SOL [ema_cross]: signal=long (fast>slow cross)
- HYPE [funding_momentum]: signal=None (mom+0.3<1.0)
- LINK [rsi]: signal=None (RSI 52)
- ZEC [funding_followthrough]: signal=short (mom-0.8, fund-0.005)
- WLD [volume_spike_momentum]: signal=None (vol 1.2x<2.0)
- NEAR [volume_spike_momentum]: signal=None (vol 0.8x)

### 🎯 判断
- BTC short entry (snapshot signal, no existing BTC pos, notional check OK)
- (SOL/ZEC も signal あるが、 既に3ポジ満杯/方向制限で見送り の場合は明示)

### 💼 実行結果
✅ BTC short 0.008 @ $62700, SL $63954 (2%), TP $58938 (6%, R:R 3.0) bracket OK
```

---

## やってはいけない (Phase 2.5 厳守)

- **建値移動 / TP引きつけ** (実効R:R 1.79→0.18 破壊の罠)
- **銘柄テーブル外の entry** (8銘柄以外は backtest未検証で EV不明)
- **同じ銘柄に同時2ポジ** (1銘柄1ポジ厳守)
- **3ポジ超え** (最大3、 backtest 最適)
- **同方向 notional $1,500 超え** (相関リスク)
- **戦略パラメータ独自変更** (table値を勝手に変えない)
- 自主ブレーキ無視
- git commit/push

---

## 根拠ドキュメント

- 銘柄別最適化: `backtest/results_asset_specific.json`
- 累積カーブ: `backtest/multi_strategy_curve.png`
- 全探索結果: `backtest/SEARCH_REPORT.md`
- 実装根拠の累積EV: 208日 OOS で +$1,393 (3pos)、 EV/t +$3.38、 maxDD $189

Funded Account 移行 / サイズ拡大は 最低3ヶ月 EV+ 実証後。
