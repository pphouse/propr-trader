# STRATEGY (別枠) — スマートマネー追従シグナル

最終更新: 2026-06-02
状態: **設計フェーズ(未稼働)**

## 趣旨

既存戦略([STRATEGY.md](STRATEGY.md))はトレンドフォロー+相対強度ペア。これとは**独立した補完戦略**として、Hyperliquid上の「上手いトレーダー」のポジション挙動をシグナル化し、エントリー判断に賛同度(confidence boost)として加える。

参考資料: [free/compass_artifact_*.md](free/compass_artifact_wf-e791b145-abf1-4b9a-a443-3cfcec14c280_text_markdown.md) — Hyperliquidスマートマネー分析の実務リサーチ。本戦略はそこで提示された段階1〜4を実装に落とす。

> ⚠️ **Propr規約への適合性が必須**: 本戦略は「シグナル抽出 → 自前バックテスト → 自分の戦略として執行」までを行う。**他人のwalletを生コピーすることはしない**(共謀/シグナル共有条項に抵触リスク)。詳細は[後述](#proprルール遵守)。

---

## 1. データソース

| 用途 | 出典 | コスト | 制限 |
|---|---|---|---|
| 候補wallet抽出 | ASXN, Dexly, HyperTracker無料枠 | 無料 | Hyperdash/Hyperliquid UI は Cloudflare ブロックでWebFetch不可 — 手動コピー or Apify Scraperで取得 |
| wallet詳細データ | `api.hyperliquid.xyz/info` 直叩き | 無料 | 1200 req/min加重制限、422問題なし(公式) |
| マーケットコンテキスト | 同上 (`allMids`, `metaAndAssetCtxs`) | 無料 | 既存`free/api.py`の`hl_prices()`で活用済 |

**重要**: QuickNode等のRPCプロキシは `userFills, portfolio, candleSnapshot` 等で 422 になる。**必ず公式エンドポイントを直叩く**。

## 2. Hyperliquid公開APIメソッド(本戦略で使う4本)

```python
# 1) 建玉・マージン
POST /info  {"type":"clearinghouseState", "user":"0x...", "dex":""}
# → marginSummary, assetPositions(entryPx, szi, leverage, unrealizedPnl)

# 2) 約定履歴(時間範囲、500件/回)
POST /info  {"type":"userFillsByTime", "user":"0x...", "startTime":<ms>, "endTime":<ms>}
# → [{closedPnl, coin, dir, px, side, sz, time, fee, crossed}, ...]

# 3) 時系列PnL(リスク調整後リターンの主データ源)
POST /info  {"type":"portfolio", "user":"0x..."}
# → [["allTime", {accountValueHistory, pnlHistory, vlm}], ["perpAllTime", {...}], ...]

# 4) ファンディング履歴(MM/ファンディングファーミング判別用)
POST /info  {"type":"userFunding", "user":"0x...", "startTime":<ms>}
```

検証済: `clearinghouseState` は無効アドレスでも `accountValue: 0` を返す(エラーにならない) — 任意の0xアドレスで照会可能。

## 3. 候補wallet選定 (段階1)

**手順**:
1. ASXN (https://stats.hyperliquid.xyz) と Dexly (https://dexly.trade) の**クローズ済みベース**リーダーボードから30〜50件のアドレスを手動収集
   - ソート: 30日 ROI, 7日 ROI, 30日 PnL(クローズ済み)
   - **総PnL順は避ける**(生存者バイアス・含み益の罠)
2. account size帯を自分(=$5,000 paper)に近い「**Shrimp/Fish**」(HyperTracker分類)に絞る
   - 大口専用戦略(MM, ファンディングファーミング)は$5k口座で再現不可
3. 初期リストを `smart_money/wallets_raw.json` に保存

## 4. スコアリング (段階2)

`smart_money/scorer.py` (未実装) が以下を計算:

| 指標 | しきい値 | 計算元 |
|---|---|---|
| 総トレード数 | ≥ 100 | `userFillsByTime` 90日分の件数 |
| 稼働日数 | ≥ 90日 | `portfolio.perpAllTime.accountValueHistory` の最初〜最後 |
| 年率Sharpe | ≥ 1.0(理想 ≥ 1.5) | `accountValueHistory`から日次リターン → `(mean - rf)/std × √365` (rf=4%/365) |
| 最大DD | ≤ 30% | `accountValueHistory`の累積最大からの最大下落率 |
| Profit factor | ≥ 1.3 | `userFills`の `closedPnl > 0` 合計 / `< 0` 合計絶対値 |
| メイカー比率 | 記録のみ | `userFills.crossed=false` の割合 → MMかどうか判別 |
| 単一トレード集中度 | 上位3件で総PnLの50%未満 | 「一発当て」を除外 |

**アルファ源泉の分類**:
- **方向性**: 多数の小〜中サイズの方向トレード、テイカー多め
- **ファンディングファーミング**: デルタニュートラル、`userFunding` 受領が主収益
- **MM**: メイカー比率 > 70%、両面約定多数

→ **「方向性アルファ」のwalletのみ** を本戦略のシグナル源に採用。MMやファーミングは追従しても自分の口座では再現できない。

## 5. シグナル定義 (段階3)

合格wallet群を `smart_money/wallets_qualified.json` に保存し、`smart_money/monitor.py` が15分〜1時間ごとにポーリング:

### シグナルA: 新規エントリー検知
- 合格群の **過半数** が直近1時間以内に**同方向**で新規ポジション開始 → **Tier-1 confidence**
- 過半数ではなく1/3以上 → **Tier-2**
- 単独wallet のエントリーは無視(個別ノイズ)

### シグナルB: ネットL/S偏向
- 合格群の合計 notional がロング/ショートで偏る → 偏った方向にバイアス
- 履歴ベースの分位点(例: 過去30日の95%タイル超え)で「**極端値**」として警告

### シグナルC: ダイバージェンス
- ASXN等の**全体センチメント**と**スマートマネー上位群**が逆方向
  → 反転シグナル(資料に「最も注目度が高い」と明記)
- これは段階4 (CoinGlass API課金 or Buildix無料枠) が必要

## 6. 既存戦略との統合

シグナルA/Bを **既存トレンドフォロー戦略のエントリー時の "confidence boost"** として使う:

| シナリオ | 動作 |
|---|---|
| トレンド方向 と スマートマネー一致(Tier-1) | サイズ +50% 増 |
| トレンド方向 と スマートマネー一致(Tier-2) | サイズ +25% 増 |
| トレンド方向 と スマートマネー逆方向 | サイズ -50% 減 or エントリー見送り |
| トレンド無し、スマートマネーTier-1のみ | 別建てで小ロット試験エントリー(口座の0.5%以内) |

**注意**: 段階3バックテスト合格までは、シグナル発生時も**手動確認のみ**(自動execution禁止)。

## 7. バックテスト方針

- **データ**: 過去90日の合格wallet ポートフォリオ動向 + Hyperliquid candle(15m/1h)
- **検証**:
  - エントリーシグナル発火時点から1h/4h/24h後のリターン分布
  - 手数料(0.045%) + slippage(15bp保守的) を控除
  - 複数レジーム(直近の上昇/下落/レンジ各1か月)
- **合格基準**: Sharpe ≥ 1.2、勝率 ≥ 50%、最大DD ≤ 5% (口座比)
- **フォワード**: 合格後、紙トレード(現Free Trial)で2週間運用 → 想定通り動くか確認 → 実弾

## 8. Proprルール遵守

[Propr Rulebook](https://www.propr.xyz) と資料の整理:

| OK | NG |
|---|---|
| 自分の戦略にスマートマネー挙動を **特徴量** として組み込む | 他人wallet の動きを **生コピー** (タイミング共有疑い) |
| 公開オンチェーンデータを **学習** に使う | 複数Propr口座間で対向ヘッジ |
| バックテストして自分の判断で発注 | 他トレーダーと**シグナル共有/共謀** |
| ボット/EA で自分の戦略を執行 | ウォッシュ取引、レイテンシアービ |

**安全側**:
- 外部walletの動きをそのまま即execするのは避ける(15〜60分の遅延を入れる、自分のフィルタを噛ます)
- シグナルはあくまで「自分の判断材料」、execは自分の戦略ロジックで
- 同方向ミラーリングは明文禁止ではないが、共謀条項リスクを避けるため上記混合方針

## 9. 実装ステップ(着手順)

```
smart_money/
├── wallets_raw.json        # 段階1で手動抽出した候補(初期30-50件)
├── wallets_qualified.json  # 段階2で採点合格した群
├── scorer.py               # ① wallet採点パイプライン
├── monitor.py              # ② 合格群のポジ動向を周期取得
├── signals.py              # ③ A/B/Cシグナル判定
├── backtest.py             # ④ シグナル発火→将来リターン分布
└── snapshots/              # walletスナップショット時系列(GitHub)
```

**実装優先度**:
1. **scorer.py** から着手(段階2の自前検証パイプライン)。これは候補wallet 1件入れれば動く小さなツール
2. wallets_raw.json は **ユーザーが手動** で初期候補をペースト(or 私がASXN等を読み取って提案)
3. scorer.py の出力で wallets_qualified.json を作る
4. monitor.py → signals.py → backtest.py の順に積み上げ
5. 全部できてから既存戦略への統合を検討

**実行頻度**:
- scorer.py: 候補wallet追加時に1回 + 月次再採点
- monitor.py: 15-30分ごと(WebSocket移行は将来)
- バックテスト: 戦略変更時のみ

---

## 次のアクション候補

- [ ] ASXN/Dexly のリーダーボードから候補wallet 10-20件を抽出して `wallets_raw.json` を作る
- [ ] `scorer.py` の MVP実装 (clearinghouseState + portfolio + userFillsByTime → スコアテーブル出力)
- [ ] 既存wallet候補1件で `scorer.py` を動かして実用性確認

優先度・実行順はユーザー判断。
