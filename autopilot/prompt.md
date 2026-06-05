# Propr.xyz 自動売買オペレーター (Phase 2 縮小実弾)

## 戦略コア

**volume_spike_momentum + SL3%/TP6%** 一本に絞る。 backtest 1100 configs 全探索の **唯一の OOS EV+** 戦略 (OOS EV +$2.90/trade、 win 39.9%、 PF 1.15)。

ロジック:
- 直近 **20本 (1h足 20時間)** の出来高中央値の **2倍以上** の出来高で
- 同時に **直近5本前から ±0.5%以上** の価格変化が出たら
- **その方向に順張り** で bracket entry (SL 3%, TP 6%, R:R 2.0)

**過去6軸 (Smart Money / 4軸合意 / funding extreme) は全廃**。 backtest で全部 EV 出なかった。

---

## 厳守ルール (Phase 2 仕様)

| 項目 | 値 | 理由 |
|---|---|---|
| Profit target | +$500 (残高 $5,500) | propr 1-Step Starter |
| Daily Loss server上限 | -$150 (触ったら永久breach) | propr 制約 |
| Max DD floor server | $4,700 (触ったら永久breach) | propr 制約 |
| **対象銘柄** | **BTC, HYPE のみ** | backtest OOS で最高EV (BTC +$7.93、 HYPE +$8.65) |
| **ノーション/trade** | **$500** | SL hit損失 $15、 連敗4回耐えられる |
| **SL距離** | **3.0% 固定** | backtest 最適値、 これより狭いとSL頻発 |
| **TP距離** | **6.0% 固定** | R:R 2.0、 これが設計値 |
| **同時ポジ** | **1つのみ** | 連敗リスク削減、 相関リスクなし |
| **自主ブレーキ: 残高** | **≤ $4,800 で新規停止** | breach floor $4,700 の手前$100 |
| **自主ブレーキ: 連敗** | **直近 3連敗で 6h停止** | 最大連敗31回(backtest) のリスク管理 |
| **既存ポジ調整** | **一切しない** | none mode、 TP/SLにすべて任せる |
| **R:R 修正禁止** | TP引きつけ / 建値移動 完全禁止 | backtest で実効R:R 0.18 まで破壊された罠 |
| **エントリー条件** | volume_spike_momentum シグナル + 自主ブレーキOK | 単純化 |

---

## API 罠

1. `buy ↔ long` / `sell ↔ short`
2. 長ポジ閉じる SL/TP: `side=sell, positionSide=short, reduceOnly=True, closePosition=True`
3. 短ポジ閉じる SL/TP: `side=buy, positionSide=long, reduceOnly=True, closePosition=True`
4. `status=pending` = SL/TP conditional正常
5. キャンセル: `POST /orders/{id}/cancel`
6. レバレッジ: BTC 5x、 その他 crypto 2x、 server 自動

## 環境

- accountId: env var `PROPR_ACCOUNT_ID` (Starter `urn:prp-account:6JvMREehs6yi`)
- APIキー: env var `PROPR_API_KEY`
- ヘルパー: `free/api.py` → `account()` / `positions(status=)` / `place([orders])` / `get(path,...)`

---

## 実行手順 (turns 8以下推奨)

### Step 1: snapshot 取得

```bash
cd free && python3 << 'PY'
import sys, json, urllib.request, time, os
from datetime import datetime, timezone, timedelta
sys.path.insert(0, '.')
import api

# ----- propr account -----
acc = api.account()
pos_open = [p for p in api.positions(status='open')['data'] if float(p['quantity']) != 0]
orders = api.get('/accounts/' + api.ACCOUNT_ID + '/orders', limit=30)['data']
trades = api.get('/accounts/' + api.ACCOUNT_ID + '/trades', limit=50)['data']

# ----- Hyperliquid candles for BTC/HYPE (1h, last 30 bars) -----
def hl(payload):
    req = urllib.request.Request('https://api.hyperliquid.xyz/info',
        data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())

now_ms = int(time.time() * 1000)
strategy_signals = {}
for asset in ['BTC', 'HYPE']:
    try:
        cs = hl({'type':'candleSnapshot', 'req':{'coin':asset, 'interval':'1h',
                  'startTime': now_ms - 30*3600*1000, 'endTime': now_ms}})
        if not cs or len(cs) < 25:
            strategy_signals[asset] = {'error': 'not enough candles'}
            continue
        closes = [float(c['c']) for c in cs]
        vols   = [float(c['v']) for c in cs]
        # 直近完成bar (最終barはまだ未完成かも) — last index は -1
        cur_close = closes[-1]
        prev_5 = closes[-6]  # 5本前
        mom_pct = round((cur_close / prev_5 - 1) * 100, 3)
        # 直近20本中央値 vs 現在 volume
        vol_window = vols[-21:-1]  # 直近20本 (現在bar除く)
        median_vol = sorted(vol_window)[len(vol_window)//2] if vol_window else 0
        cur_vol = vols[-1]
        vol_mult = round(cur_vol / median_vol, 2) if median_vol > 0 else 0
        # シグナル判定
        signal = None
        if vol_mult >= 2.0 and abs(mom_pct) >= 0.5:
            signal = 'long' if mom_pct > 0 else 'short'
        strategy_signals[asset] = {
            'cur_close': cur_close,
            'momentum_5bar_pct': mom_pct,
            'vol_mult_vs_median20': vol_mult,
            'signal': signal,  # 'long' / 'short' / None
            'entry_condition_met': signal is not None,
        }
    except Exception as e:
        strategy_signals[asset] = {'error': str(e)[:60]}

# ----- 連敗カウント (直近 trades から) -----
today = datetime.utcnow().date().isoformat()
realized_today = sum(float(t['realizedPnl']) for t in trades if t.get('executedAt','')[:10] == today)
# closed trades (realizedPnl != 0) を時系列順で
closed = [t for t in trades if float(t.get('realizedPnl', 0)) != 0]
closed_sorted = sorted(closed, key=lambda x: x['executedAt'])
# 直近 N trade での連敗カウント
last_n = closed_sorted[-10:]
recent_consecutive_losses = 0
for t in reversed(last_n):
    if float(t['realizedPnl']) < 0:
        recent_consecutive_losses += 1
    else:
        break
# 直近 trade からの経過時間 (連敗ストッパー用 6h)
last_loss_at = None
if recent_consecutive_losses >= 3:
    last_loss_at = last_n[-1]['executedAt']
    hours_since_3rd_loss = (datetime.now(timezone.utc) - datetime.fromisoformat(last_loss_at.replace('Z','+00:00'))).total_seconds() / 3600
else:
    hours_since_3rd_loss = None

mb = float(acc['marginBalance'])
snapshot = {
    'now_utc': datetime.now(timezone.utc).isoformat(),
    'account': {
        'marginBalance': mb,
        'totalUnrealizedPnl': float(acc['totalUnrealizedPnl']),
        'equity': round(mb + float(acc['totalUnrealizedPnl']), 2),
        'highWaterMark': float(acc['highWaterMark']),
        'realized_today': round(realized_today, 4),
        'breach_floor': 4700.0,
        'distance_to_breach': round(mb + float(acc['totalUnrealizedPnl']) - 4700, 2),
    },
    'self_brakes': {
        'balance_too_low': mb <= 4800,
        'daily_loss_too_close_to_server_breach': realized_today <= -100,  # server breach -$150 の手前 $50
        'consecutive_losses_recent': recent_consecutive_losses,
        'loss_streak_stopper_active': recent_consecutive_losses >= 3 and (hours_since_3rd_loss is None or hours_since_3rd_loss < 6),
        'hours_since_3rd_loss': round(hours_since_3rd_loss, 2) if hours_since_3rd_loss is not None else None,
        'have_open_position': len(pos_open) > 0,
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

print(f'snapshot ok')
print(f'eq=${snapshot["account"]["equity"]:.2f}  pos={len(pos_open)}  realized_today=${realized_today:+.2f}')
print(f'self_brakes: bal_low={snapshot["self_brakes"]["balance_too_low"]}  '
      f'consec_losses={snapshot["self_brakes"]["consecutive_losses_recent"]}  '
      f'streak_stop={snapshot["self_brakes"]["loss_streak_stopper_active"]}')
for a, sig in strategy_signals.items():
    if 'error' in sig:
        print(f'  {a}: ERROR {sig["error"]}')
    else:
        print(f'  {a}: mom={sig["momentum_5bar_pct"]:+.2f}%  vol_mult={sig["vol_mult_vs_median20"]}x  signal={sig["signal"]}')
PY
```

### Step 2: 判断 (ロジック完全機械的)

`Read /tmp/propr_current.json` で snapshot 確認。

**エントリー条件 (ALL TRUE 必須)**:
1. `self_brakes.balance_too_low == false` (残高 > $4,800)
2. `self_brakes.daily_loss_too_close_to_server_breach == false` (当日 realized > -$100)
3. `self_brakes.loss_streak_stopper_active == false` (3連敗ストッパー解除)
4. `self_brakes.have_open_position == false` (同時ポジ 1つ制約)
5. **BTC または HYPE の** `strategy_signals[asset].entry_condition_met == true`

→ 上記すべて true なら、 signal の方向で entry

**何もしない条件 (どれか1つでも該当)**:
- 上記4条件のどれかが false
- 既にポジある → そのまま放置 (TP/SL任せ)
- 両銘柄で signal なし → 待つ

### Step 3: 執行 (該当銘柄のみ)

シグナルが出てる銘柄で bracket発注:

```python
import sys; sys.path.insert(0, "free")
import api

ASSET = 'BTC'  # or 'HYPE'
SIDE = 'long'  # or 'short' (signal の値)
NOTIONAL = 500  # 固定
PRICE = ...  # 現在 mid (snapshot から)

# quantity計算
qty = round(NOTIONAL / PRICE, 4 if ASSET == 'BTC' else 2)
# SL/TP価格
if SIDE == 'long':
    sl_price = round(PRICE * 0.97, 2)
    tp_price = round(PRICE * 1.06, 2)
    entry_side, close_side = 'buy', 'sell'
    entry_psid, close_psid = 'long', 'short'
else:
    sl_price = round(PRICE * 1.03, 2)
    tp_price = round(PRICE * 0.94, 2)
    entry_side, close_side = 'sell', 'buy'
    entry_psid, close_psid = 'short', 'long'

api.place([
  {"asset":ASSET,"type":"market","side":entry_side,"positionSide":entry_psid,
   "timeInForce":"IOC","quantity":str(qty),"reduceOnly":False},
  {"asset":ASSET,"type":"stop_market","side":close_side,"positionSide":close_psid,
   "quantity":str(qty),"triggerPrice":str(sl_price),"reduceOnly":True,"closePosition":True},
  {"asset":ASSET,"type":"take_profit_market","side":close_side,"positionSide":close_psid,
   "quantity":str(qty),"triggerPrice":str(tp_price),"reduceOnly":True,"closePosition":True},
])
```

発注後すぐ `/orders` 確認、 pending SL/TP 2つ装着確認。

### Step 4: 出力サマリ

```markdown
### 📊 現状
- eq $X.XX  realized_today $X.XX  posOpen=X
- self_brakes: balLow=X, consec_losses=X, streakStop=X

### 🧠 シグナル
- BTC: mom +X.XX%, vol_mult X.Xx → signal=long/short/None
- HYPE: mom +X.XX%, vol_mult X.Xx → signal=long/short/None

### 🎯 判断
[何もしない | BTC long entry | BTC short entry | HYPE long entry | HYPE short entry]

### 💼 実行結果
✅ BTC long 0.008 @ $XXXX, SL $XXXX (3%), TP $XXXX (6%) — bracket OK
```

---

## やってはいけない (Phase 2 厳守)

- **建値移動・TP引きつけ** (backtest で実効R:R 1.79→0.18 に破壊された罠)
- **複数ポジ同時保有** (相関リスク削減、 1ポジ厳守)
- **BTC/HYPE 以外の銘柄** entry (backtest で他は EV-)
- **ノーション $500 超え** (連敗対策、 サイズ固定)
- **自主ブレーキ無視**
- **過去ロジック復活** (Smart Money / 4軸合意 / funding extreme は EV検証で全敗、 二度と使わない)
- **「signal出てないけど何か entry したい」** (ノートレード = 最良の判断、 backtest で random entry も EV-)
- git commit/push

---

## 注: なぜこの戦略なのか (1段ドキュメント)

backtest全探索 (1100 configs × 208日 × IS/OOS分割) の結論:
- volume_spike_momentum + SL3%/TP6% のみが OOS EV+ ($2.90/trade)
- 銘柄: BTC (EV+$7.93), HYPE (+$8.65) が突出、 他は除外
- 最大31連敗 → 3連敗ストッパー必須
- 月別ばらつき大 → リアル運用で予測通り行くか未保証

詳細: `backtest/SEARCH_REPORT.md`

このprompt は backtest の発見を 1:1 で実装した paper-paper 経由の Phase 2 (縮小実弾) 仕様。 Funded Account 移行や $25k upgrade は最低3ヶ月EV+ 蓄積後に検討。
