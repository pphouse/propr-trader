# Propr.xyz 自動売買 bot 戦略レビュー資料

このドキュメントは現在稼働中の取引 bot を他AIに評価してもらうためのサマリです。 全体像、 ロジック、 リスク管理、 実績、 既知の弱点を網羅。

---

## 1. 全体アーキテクチャ

```
ablenet VPS (Ubuntu 24.04, V2 プラン)
    └── cron */10 * * * *  (10分毎)
         └── ~/propr-trader/vps/run.sh
              ├── git pull (最新prompt取得)
              ├── source ~/.propr-env (secret読込)
              └── claude --print --dangerously-skip-permissions
                   └── prompt: 「autopilot/prompt.md を実行」
                        ├── Step 1: snapshot収集 (~/.propr-trader-history.json に追記)
                        ├── Step 2: WebSearch ニュース調査
                        ├── Step 3: 4軸判定
                        ├── Step 4: 発注 (propr.xyz REST API経由)
                        └── Step 5: markdown サマリ出力 → ~/autopilot.log
```

- **モデル**: claude-sonnet-4-6 (Pro/Max plan、 OAuth tokenでcloud利用、 API課金ゼロ)
- **1 cycle 所要**: 5〜7分 (snapshot + news + 判断 + 発注 + サマリ、 約19 turns)
- **取引所**: propr.xyz (Hyperliquid 上の prop firm)
- **アカウント**: $5,000 Starter 1-Step (paper account)

---

## 2. propr.xyz 1-Step Starter ルール (制約条件)

| 項目 | 値 |
|---|---|
| Profit Target | +$500 (残高 $5,500) で合格 → Funded Account |
| Daily Loss 上限 | -$150 (3% fixed、 触ったら永久 breach) |
| Max Drawdown floor | $4,700 (static、 6%、 触ったら永久 breach) |
| 時間制限 | なし |
| 最小取引日数 | なし (1取引でPass可) |
| Leverage | BTC/ETH 5x、 その他 crypto 2x、 株式/コモ 4x |
| Reset | breach 後リセット不可、 新規評価フィー必要 |
| Funded移行 | KYC後、 profit split 80%/20% (trader/Propr) |

**重要**: breach floor は static = 残高 $5,500 まで伸びても floor は$4,700固定。 つまり残高伸ばすほど安全圏拡大。

---

## 3. 4軸エントリー判定 (核心ロジック)

エントリーには **4軸のうち 3軸以上が同方向** + 短期軸/清算軸が逆方向でないこと、 が必要。

| 軸 | データソース | スコア化 |
|---|---|---|
| **A. マクロ方向** | Smart Money wallet (`0x7c93...`) のlong/short比 + WebSearch ニュース | +1 (long寄り) / -1 (short寄り) / 0 |
| **B. funding** | Hyperliquid funding_pct_per_hr + 1h前との差分 (`fund_chg_1h`) | abs ≥ 0.005% で方向 +/-1、 変化率で補強 |
| **C. 短期モメンタム** | 5m/15m candle (Hyperliquid `candleSnapshot`) → 直近5本平均 vs その前 + 2hレンジ位置 | momentum_pct +/-0.5% で方向 +/-1 |
| **D. OI動向** | OI 1h変化率 + 価格1h変化率 + 清算signal推定 | OI急変 + 価格動きで方向 +/-1 |

### 信頼度別サイズ

| 一致軸数 | 信頼度 | サイズ倍率 | base例 (BTC) |
|---|---|---|---|
| 4軸 | 90%+ | base × 2.0 | 0.04 |
| 3軸 | 75% | base × 1.5 | 0.03 |
| 2軸 | 60% | base × 1.0 | 0.02 |
| 1軸以下 | <50% | エントリー禁止 | — |

ただし **1ポジ最大想定損失 $40** を超えてはいけないので、 サイズ計算後に SL距離 × notional ≤ $40 で再キャップ。

### C軸/D軸が逆の場合の挙動 (重要)

```
例: A=BEAR (SM全shorts) + B=BEAR (funding +0.02%)  ← 2軸BEAR一致
    だが C=BULL (5m momentum +1.5%, range位置 80%) ← 短期反発中、 高値圏
    → エントリー禁止、 待つ
    
理由: 「短期反発に飲み込まれて即SLヒット」 のパターンを回避
      (2026-06-05 07:46 にこれで -$82 失った実例あり)
```

---

## 4. SL / TP / 既存ポジ調整

- **SL距離**: 1.5〜2.5% (5m足 High-Low幅の2倍を目安)
- **TP距離**: SL距離 × 2.0 (R:R 2.0)
- **必ず bracket order** (entry market + SL stop_market + TP take_profit_market)
- **既存ポジ調整**:
  - 含み益 +$10 → SL を建値+$2
  - 含み益 +$25 → SL を建値+$10
  - TP 50%達成 → TP引きつけ
  - SL 接近 (差5%以内) → 放置

---

## 5. リスク管理 (自主ブレーキ)

server側 breach の手前で自分から止まる:

| ブレーキ | 条件 | 効果 |
|---|---|---|
| 残高 ≤ $4,750 | breach floor $4,700 まで$50 | 新規エントリー禁止 |
| 当日 realized ≤ -$80 | daily loss上限 -$150 まで$70 | 新規エントリー禁止 |
| 同時ポジ ≥ 2 | 同時2ポジ上限 | 新規エントリー禁止 |

---

## 6. 銘柄ユニバース (focus list)

合計 18 crypto perp:

- **主要**: BTC, ETH, SOL, HYPE, LINK
- **拡張 alt** (24h vol ≥ $7M): ZEC, WLD, NEAR, XMR, XRP, ADA, BNB, AAVE, SUI, DOGE, AVAX, BCH, LTC

短期足取得は重い処理なので **上位8** (BTC, ETH, SOL, HYPE, LINK, ZEC, WLD, NEAR) のみで実施。
他は mkt + funding データのみ参照。

**未カバー** (将来検討):
- 株式perp (`MU-USDC` 等、 builder code subsystem)
- FX perp
- Pre-IPO perp
- 商品 perp (Gold, Oil)

これらを入れない理由:
- メイン universe の `metaAndAssetCtxs` で取得不可
- Smart Money軸 (`0x7c93...`ウォレット) が crypto only
- ニュース軸が別ジャンル (Fed/CPI/earnings) で再設計必要

---

## 7. データソース詳細

### Hyperliquid public API
- `metaAndAssetCtxs`: 全銘柄の mid/funding/OI/24h変化 (毎cycle 1回)
- `candleSnapshot`: 5m × 2h, 15m × 4h, 1h × 12h (8銘柄分、 毎cycle 24回)
- `clearinghouseState(user=0x7c93...)`: Smart Moneyウォレットの現在ポジ全銘柄分

### propr.xyz REST API
- `/accounts/{id}`: 残高、 unrealized P&L、 HWM
- `/positions?status=open`: アクティブポジ
- `/orders`: 全注文 (pending SL/TP含む)
- `/trades`: 約定履歴
- `POST /orders`: 発注 (bracket形式)
- `POST /orders/{id}/cancel`: キャンセル

### 履歴データ (Local)
- `~/.propr-trader-history.json`: snapshot ごとに OI/funding/mid を保存 (48h rolling)
- 過去 10m/1h/24h との比較で D軸 (OI変化、 清算signal) と B軸補強 (funding変化率) を実現

### WebSearch (Step 2)
- 毎cycle "Bitcoin OR Ethereum OR crypto news last 6 hours" で6時間以内のニュース取得
- Fed/CPI、 ETF flow、 whale動き、 規制、 hack/depeg を抽出
- A軸 (マクロ方向) の補強材料

---

## 8. Smart Money wallet について

`0x7c930969fcf3e5a5c78bcf2e1cefda3f53e3c8fd`

- 評価方法: `smart_money/scorer.py` で過去パフォーマンス、 勝率、 PnLなどから上位ウォレット選定 (実行は手動、 履歴は `smart_money/wallets_qualified.json` に保存)
- 2026-06-05時点で 102 positions 全部short = 強烈なbear posture
- 1ウォレットなので **強い指向性バイアスあり**、 「全銘柄short」 を基本姿勢にしてる相手
- これに従いすぎると上昇トレンドで全敗する弱点

---

## 9. 過去実績

### Free Trial $5,000 (2026-06-02 〜 06-05)
- **23勝 / 2敗 (92% win rate)**、 NET +$546 (+10.9%)、 3日で合格
- 勝ち平均 $14.64 / 負け平均 $26.95 (R:R 0.54x、 勝率に依存する脆い構造)
- 全部 short が当たった (期間中マーケットが一方向にベア)
- 唯一の long (HYPE) は -$17.52 で負け
- → **戦略が正しかった部分** = Smart Money 追従、 bracket遵守、 ニュース整合
- → **運だった部分** = 市況が3日間一方向、 92%は持続不可能 (実運用では 55-60% 想定)

### Starter $5,000 開始 (2026-06-05 16:13 JST 〜)
- 開始30分で -1.74% (BTC + ETH short が即SL hit)
- マクロBEAR で entry したが直前の5m momentum +1.66% / 高値圏 を見ていなかった
- → これを受けて prompt を「4軸一致」 「C軸/D軸 逆方向なら待つ」 に書き換え
- 現在 cron 再開、 履歴データ蓄積中 (B/D軸は1時間後から完全稼働)

---

## 10. 既知の弱点

1. **小サンプル問題**: 過去実績25 trades は統計的有意性なし
2. **Smart Money依存**: 1ウォレットの偏ったbias、 そのウォレットが大損する局面もある
3. **C軸の momentum 計算**: 単純な平均比較で、 RSI/MACD のような技術指標は未使用
4. **Volume軸なし**: D軸でvolume spike は取ってるが、 trend全体での volume profile は見てない
5. **板読みなし**: bid/ask imbalance は時間軸不一致で外したが、 短期ブレイク予兆を逃す可能性
6. **長期トレンド軸なし**: 4h/Daily 足は見てない、 大きなトレンド転換 (週単位) を察知できない
7. **相関考慮なし**: BTC short + ETH short + SOL short は実質1ポジ (相関0.85+)
8. **ニュース効果遅延**: WebSearch 結果は人類が記事を書いてからbot到達まで30分以上、 即時性なし
9. **Funding cycle 効果未考慮**: funding 8時間ごとに切り替わるので、 直前のpositioningで動く特性を捉えてない
10. **execution slippage 無視**: market注文IOC使用、 流動性薄銘柄で予想以上のslippageあり得る

---

## 11. 評価してほしいポイント

1. **4軸ロジックは過剰設計か?** (3軸でも十分か、 5軸目あるべきか)
2. **信頼度→サイズマッピングは妥当か?** (リニアでなくlog scaleの方が良いか)
3. **R:R 2.0 は妥当か?** (1.5の方が回転率上がって期待値高い可能性)
4. **Smart Money 1ウォレット依存** の解消方法 (複数ウォレット平均? 別の手法?)
5. **板読み / orderflow を入れるべきか** (我々は不要と判断したが、 別意見ほしい)
6. **breach管理の自主ブレーキ閾値** ($4,750/-$80) は緩い or 厳しい?
7. **alt-crypto 18銘柄は多すぎ?** Claudeの判断負荷を考えると絞る方が良い?
8. **prompt 全体の構造** で見落としや無駄ロジックは?
9. **過去実績の評価**: 92% win rate を信頼すべきか、 単なる市況ボーナスか
10. **次の改善ポイント** で何を優先すべきか

---

## 12. 参考リンク (リポジトリ構造)

- prompt 全文: `autopilot/prompt.md`
- API ヘルパー: `free/api.py`
- VPS スクリプト: `vps/run.sh`, `vps/bootstrap.sh`
- Smart Money scorer: `smart_money/scorer.py` + `wallets_qualified.json`
- propr.xyz rules: https://www.propr.xyz/rules
- Hyperliquid docs: https://hyperliquid.gitbook.io/hyperliquid-docs

---

*最終更新: 2026-06-05 (Starter $5,000 1-Step 評価中)*
