# KNOWLEDGE — propr.xyz / Hyperliquid 実戦メモ

実際にAPIを叩いて分かった、ドキュメントに書いてないか・誤っている挙動。

---

## API の罠

### 1. Python urllib/requests は Cloudflareに弾かれる

デフォルトの User-Agent (例: `Python-urllib/3.x`) で POST/PUT を送ると `HTTP 403 error code 1010`。GETは時々通る。

**回避**: `User-Agent: curl/8.4.0` を必ずセット。`free/api.py` のHEADERSに組込済み。

### 2. `side` と `positionSide` は「ペアタグ」であって「アクション+ポジ方向」ではない

公式ドキュメントの例には `side=sell, positionSide=long` でlongポジを閉じるサンプルがあるが、これを送ると:

```
400 {"code":13096,"message":"order_side_must_align_with_position_side_buy_long_or_sell_short"}
```

**正しいペアリング**:
- `side=buy` ↔ `positionSide=long` (longを開く OR shortを閉じる)
- `side=sell` ↔ `positionSide=short` (shortを開く OR longを閉じる)

**実装パターン**:
| やりたいこと | side | positionSide | reduceOnly |
|---|---|---|---|
| ロング開く | buy | long | false |
| ロング閉じる(SL/TP) | sell | **short** | true |
| ショート開く | sell | short | false |
| ショート閉じる(SL/TP) | buy | **long** | true |

### 3. Conditional order は `pending` のまま、`open` ではない

`stop_market`, `take_profit_market` は trigger 発火まで `status: "pending"`。
`GET /orders?status=open` でフィルタすると見えない。SL/TP一覧が欲しい時は `status=pending` で取るか、status指定なしで全部取って自前でフィルタ。

### 4. Bracket order の組み方

`orders[]` に entry + SL + TP を入れて1リクエストで送れる。サーバ側で同じ `orderGroupId` が振られる(2件以上なら top-level に `orderGroupId` 明示推奨)。

このとき conditional 側に `positionId` は不要 — entry と同じグループに居ることで「エントリーが約定したらこのSL/TPを発火対象に紐付ける」と解釈される。

```python
# free/api.py の place() ヘルパが boilerplate を埋める
api.place([
  {"asset":"BTC","type":"market","side":"sell","positionSide":"short","timeInForce":"IOC","quantity":"0.03"},
  {"asset":"BTC","type":"stop_market","side":"buy","positionSide":"long","quantity":"0.03","triggerPrice":"68553","reduceOnly":True,"closePosition":True},
  {"asset":"BTC","type":"take_profit_market","side":"buy","positionSide":"long","quantity":"0.03","triggerPrice":"64540","reduceOnly":True,"closePosition":True},
])
```

### 5. `intentId` (ULID) は idempotency key

同じ intentId で2回送っても2重発注されない(2回目は最初のorderを返す)。リトライ安全。

### 6. `closePosition: true` の挙動

`reduceOnly: true` と組み合わせて使うと「現在のポジ全量をclose」になる。`quantity` を厳密に指定しなくても、ポジが部分減少していたら現在量で発動する(と思われる、要検証)。

### 7. Cancel は 201 を返す

200 ではなく 201。`200 or 201` 両方を成功扱いに。`400` は「既にfilled/cancelled/expired」なので無視してOK。

### 8. ページネーション `limit` の上限は 100

`/orders`, `/trades` 等で `limit=200` を渡すと `400 {"message":"Bad Request Exception"}`。サーバ側のhard cap は 100。それ以上欲しい場合は `offset` でページング。

---

## レバレッジ上限 (`GET /leverage-limits/effective`)

```json
{
  "defaults": {"crypto":2, "equity":4, "fx":4, "pre_ipo":4, "index":5, "commodity":5},
  "overrides": {"BTC":5, "ETH":5}
}
```

- BTC/ETH のみ 5x
- それ以外のcrypto(HYPE/SOL/AVAX等)は default 2x
- 株(`xyz:AAPL`等)・FXは 4x
- 商品(`xyz:GOLD`等)・指数は 5x

`PUT /accounts/{aid}/margin-config/{configId}` で変更。初期値は1xなので、毎アセット使う前に上げる必要あり。

---

## Hyperliquid 公開API(価格取得用)

proprのAPIには tickerエンドポイントが見当たらない(`markPrice` はポジション持って初めて分かる)。価格は Hyperliquid公開APIから取る:

```python
POST https://api.hyperliquid.xyz/info
Content-Type: application/json
Body: {"type":"allMids"}            → 全ペアの mid price
      {"type":"metaAndAssetCtxs"}   → 24h変動率、funding、OI、出来高
      {"type":"candleSnapshot","req":{"coin":"BTC","interval":"15m","startTime":...}}
```

---

## Free Trial Challenge ルール (server enforced)

| 項目 | 値 |
|---|---|
| 初期残高 | $5,000 USDC (paper) |
| 利益目標 | +10% ($500) で次フェーズへ |
| 日次最大損失 | -3% ($150) で即失敗 |
| 最大ドローダウン | -6% ($300, **static** = 初期残高基準) で即失敗 |
| 再挑戦回数 | 3回まで |
| 取引可能アセット | Hyperliquid 全universe(crypto perp + HIP-3 stock/commodity) |

> **HIP-3 assets は `xyz:` prefix 必須** — `xyz:AAPL`, `xyz:GOLD` 等。プレフィックスなしで指定すると `404 exchange_asset_not_found`。

---

## 市況観察ログ

### 2026-06-02 (entry時点)
- crypto全体が24h -5% 級の下落: BTC -5.94%, ETH -3.47%, SOL -5.16%, AVAX -5.36%
- **HYPE だけ -0.80%** とアウトパフォーム → 相対強度トレード材料
- funding は概ね +0.0013% (long 偏重)、HYPEのみ +0.0052% と高く、ロング過熱気味だが上昇継続中
