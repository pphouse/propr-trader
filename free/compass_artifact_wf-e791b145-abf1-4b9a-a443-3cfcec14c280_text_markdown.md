# Hyperliquid スマートマネー分析 実務リサーチドキュメント（2026年6月版）

> 本資料は分析・学習・研究目的の技術リサーチであり、**投資助言ではありません**。

## TL;DR
- **2026年時点のスマートマネー分析は「ダッシュボード＋公式API自前取得＋スコアリング」の三層構成が最適。** ダッシュボード（Hyperdash, HyperTracker, CoinGlass, Dexly, Nansen等）で候補ウォレットを発掘し、Hyperliquid公式 `info` エンドポイント（`POST https://api.hyperliquid.xyz/info`、認証キー不要）で `clearinghouseState`・`userFillsByTime`・`portfolio` を自前取得して検証、リスク調整後リターンでスコアリングする流れが王道。
- **総PnL順リーダーボードは「上手いトレーダー」発見には不適。** 生存者バイアス・含み益の罠・レバレッジ歪みを排除するには、試行回数（トレード数・稼働日数）、一貫性（勝率×平均損益比、最大ドローダウン、Sharpe的指標）、相場レジームを跨いだ生存、リターンの源泉（方向性/ファンディング/MM）を加味した独自スコアが必須。
- **集団ポジショニングはシグナル化できるが「生フォロー」は禁物。** 上位群のネットL/S・含み損益・クラウディングを特徴量化し、必ずバックテストを経てから戦略に組み込む。なお他人の戦略をProprなどのプロップ口座で複製する場合、Proprは「コピートレード自体は許可」する一方で、**相関・対向ポジションや共謀シグナルはオンチェーン相関分析＋Chainalysisエンティティ＋リンクグラフで検知し、即時凍結・没収・永久BAN**とする。学習・自戦略構築に留めるのが安全。

---

## Key Findings

1. **Hyperdash はpvp.tradeに買収され、V2は分析＋執行の統合ターミナルに転換。** pvp.trade公式X投稿で発表（"Today, PVP is announcing our acquisition of Hyperdash (@hypurrdash) — the leading analytics product on Hyperliquid"）、Foresight News報道では現地時間11月19日（UTC+8）。公開APIは無い（UI内に分析がロック）。Cohorts/Top Traders/Alphaリーダーボードで利益帯別ポジショニングを可視化。執行手数料は1.5bp（builder code f=15）。
2. **HyperTracker（CoinMarketManager運営）は約204万ウォレットを追跡し、16の行動コホート分類と本格的REST/WebSocket/Webhook APIを提供。** 無料枠は100リクエスト/日、有料はPulse $179/月〜Stream $2,399/月。スマートマネー分析の「API化」では最有力。
3. **CoinGlassは$1M超ポジションのクジラ監視・PnL分布・サイズ別ウォレット分類をマルチ取引所横断で提供。** API $29/月〜$699/月。Dexlyはクローズ済みポジション基準のリーダーボード＋ウォレットExplorer（無料、コピートレード機能あり）。NansenはHyperliquid向け「Smart Money Perps」とPerp Leaderboard APIを提供（Pro $49/月〜）。
4. **公式API：オープンソースノード経由だと `userFills`・`userFillsByTime`・`portfolio`・`candleSnapshot`・`l2Book` 等が 422 "Failed to deserialize" エラーになる。** これらはFoundationインデクサ依存メソッドで、公式 `api.hyperliquid.xyz/info` を直接叩く必要がある。
5. **スコアリングは「リスク調整後リターン × 試行回数 × 生存期間 × アルファ源泉」で。** オンチェーンの `pnlHistory`/`accountValueHistory`（`portfolio`）から日次リターン列を作り、Sharpe・最大ドローダウンを計算するのが実務的手順。
6. **Proprでのコピーは「同方向の単純コピーは規約上許可」だが、相関・対向・共謀は検知・凍結対象。** 学習目的に徹し、生フォローではなくシグナル化＋バックテストを推奨。

---

## Details

### 1. スマートマネー分析ツール 最新状況（2026年）

#### Hyperdash（hyperdash.com）
- **買収・現状**：pvp.tradeがHyperdash（旧 @hypurrdash、"Hyperliquid最大の分析プロダクト"）の買収を公式Xで発表（Foresight News報道では現地時間11月19日 UTC+8）。数か月かけて再構築し、**V2を分析＋執行の統合ターミナル**として再ローンチ。オンボーディングは段階制で、アクティブなHyperliquidトレーダーとPVPユーザーを優先。
- **トップトレーダー / リーダーボード**：「Alpha leaderboard」が上位トレーダーを **PnL・equity・勝率・総トレード数・Sharpe ratio・最大ドローダウン** でランク付け。左サイドバーで利益帯（"Extremely Profitable" +$1M PnL 〜 "Rekt" -$1M+）とウォレットサイズで絞り込み可能。
- **ポジショニングデータ（Cohorts タブ）**：選択中の資産について、トレーダーを利益帯別に分割し、**ネット建玉（notional）・トレーダー数・含み損益分布** を表示。Bankless検証記事（David, 2025年）の記述：ZECで全体が50/50ロング/ショートでも、"the 'Extremely Profitable' cohort (+$1M PNL) specifically is 66% short, to the tune of $169M" といった乖離が見える。
- **コピートレード機能**：任意トレーダーをトラッキングリストに追加、ポジションへのカウンター、またはコピートレード設定（ポジションサイジング・ストップ・テイクプロフィットの組み込みリスク制御）が可能。
- **料金**：ダッシュボードは無料。執行時にbuilder fee 1.5bp（0.015%、builder code f=15）。30日出来高に応じたティア別キャッシュバックあり（最上位Obsidianで実効約1.16bp）。**公開API無し**（分析データはUI内にロックされ、外部アプリへのパイプ不可）。
- **最適用途**：分析と執行を同一画面でやりたいアクティブトレーダー、利益帯別ポジショニングの即時確認。

#### HyperTracker（hypertracker.io、運営：CoinMarketManager）
- **追跡ウォレット数**：HyperTracker公式リーダーボード表記で 2,039,387 ウォレットをリアルタイム追跡（"Tracking All 2,039,387 Hyperliquid wallets in real time"、Active Perp Traders 217,850）。リーダーボードのPerp PnLは 266,408 の資格ウォレット対象（"Perp PNL rankings across 266,408 qualified wallets"）。約5分のリフレッシュサイクル。
- **ウォレットのドリルダウン**：任意アドレスを貼ると、総equity、現在のperpバイアス、使用レバレッジ、24h/7d/30d/全期間のPnL、出来高、全建玉（エントリー価格・含みPnL・受取ファンディング・清算距離）、全保有・直近約定・オープンオーダー・送金・リファラルまで可読表示。各ウォレットに**perp equity帯**と**全期間PnL帯**の2つのコホートバッジ。
- **コホート分析**：全ウォレットを**16の行動コホート**（perp equityで8段階、全期間PnLで8段階）に自動分類。Shrimp/Fish/Dolphin/Apex Predator/Small Whale等のequity帯ごとにバイアススコア・平均レバレッジ・建玉保有率を集計。
- **リーダーボード**：PnL（perpのみ/全体）、30日平均perp PnL、最大ポジション、トップHYPE保有、最多お気に入り、Vaultなど複数軸。各行に perp equity・open value・leverage・current bias・期間別PnL。
- **有料API**：REST + WebSocket（Streamティア）+ Webhook（Surge以上）。リーダーボード/コホート/ポジションヒートマップ/オーダーデータ/清算データ/ビルダー分析の各エンドポイント、CSVエクスポート（1期間あたり最大25,000行）。ウォレット年齢・レバレッジ・open exposure・directional biasなど標準Hyperliquid APIに無い派生指標を付加。
- **料金**：無料（100リクエスト/日）、Pulse $179/月（5万リクエスト）、Surge $499/月（10万）、Flow $1,159/月（20万）、Stream $2,399/月（100万＋WebSocket）。
- **最適用途**：スマートマネー分析を**API化**して自前のシグナル/ボット/ダッシュボードに組み込みたい開発者・クオンツ。自力で同等を作ると$10K+/月相当との比較が売り。

#### CoinGlass（coinglass.com/hl, /hyperliquid）
- **PnL分布・クジラ監視**：Hyperliquidウォレットのポジション分布・PnL分布をリアルタイム表示。CoinGlass APIドキュメント（Hyperliquid Whale Alert）：「real-time whale alerts on Hyperliquid, highlighting positions with a notional value over $1 million.（Returns up to approximately 200 most recent records）」。クジラのロング/ショート比率、ロング/ショートトレーダー数、含みPnL・ファンディング手数料を可視化。
- **サイズ別ウォレット分類**：ウォレットを取引サイズで区分（例：$0〜$10k帯から上位口座まで）。"Smart Money"と"Giga Rekt"のアドレスタイプ識別、約35万アドレスをカバー。
- **API・料金**：80超のエンドポイント。Hobbyist $29/月（30 req/min）、Startup $79、Standard $299、Professional $699（1,200 req/min）。
- **最適用途**：複数取引所（Binance/Bybit/OKX等）を横断したクジラ・清算の統一監視。Hyperliquid固有の深さでは専用ツールに劣る。

#### Dexly（dexly.trade）
- **クローズ済みポジション基準リーダーボード**：実現PnL（クローズ済みポジションの実損益）・ROI（%）・出来高・account valueでランク。**24h/7d/30d/全期間**のタブと、ROI/PnL/出来高/account valueでのソートに対応。複数時間枠での一貫性チェックを推奨。
- **ウォレットExplorer**：任意アドレスの建玉・含みPnL・レバレッジ・equity曲線（Hyperliquid L1からリアルタイム）、全約定履歴・ファンディング・入出金、勝率・実現益・総手数料を表示。DeBank/Zerion等の汎用トラッカーと違いperps特化。
- **コピートレード**：ノンカストディアル（資金はウォレットに残る）の1クリックミラーリング、ポジションサイジング・最大ドローダウン・ストップロスのリスクパラメータ設定可。
- **料金**：基本無料（オンチェーンデータ由来、自己申告不可）。
- **最適用途**：クローズ済み（実現）ベースで実力を見たい、ウォレット単位の深掘り。

#### Arkham / Nansen（個人特定には踏み込まない前提）
- **Nansen**：5億超のウォレットをラベリング、マルチチェーン。Hyperliquid向けに**「Smart Money Perps」**ダッシュボードとToken Screenerを提供。API側に `perp-leaderboard`、Smart Money Perp Trades、Address Perp Positions/Trades、Hyperliquid Address Leaderboard等。"Smart Money"は約12種のラベル（Smart Trader, Fund, Smart LP 等）で、全体で約5,000〜10,000ウォレット規模。料金は2025年に大幅簡素化・値下げ（Nansen公式 "New Pricing Explained"：「We're simplifying to one Pro plan priced at $49/mo (annual) and $69/mo (monthly)… The new Pro plan launches September 25th, 2025」、旧Professional $999+/月から最大95%減）。
- **Arkham**：エンティティ識別に強い（複数チェーン横断、資金フロー追跡、バウンティ型ラベリング）。コア分析は無料、API申請制。Hyperliquidのエンティティ閲覧に対応。
- **本ドキュメントの方針**：両者とも**実名・個人特定への紐付けには踏み込まない**。スマートマネー「ラベル」と挙動分析のみを用途とする。

#### その他（Buildix, Apify など）
- **Buildix（buildix.trade）**：Hyperliquid特化のオーダーフロー分析。無料枠で311超ペアスクリーナー、CVD、VPIN、**Smart Money Delta**、クジラフィード、5取引所横断比較、シグナルバックテスト、ウォレットトラッカー。Proで Kyle's Lambda・レジーム検知・API。Exocharts代替としてHL対応唯一級。
- **Apify Hyperliquid Leaderboard & Vaults Scraper**：リーダーボード/Vaultsをプログラムから取得（$0.5/1000件級、Apify API経由）。スクレイピング用途。
- **ASXN / HyperScreener**：無料の総合ダッシュボード（クジラ・清算・トップトレーダー・大口・ファンディング・OI）。日次更新。公式 stats.hyperliquid.xyz もASXN提供。

#### ツール比較表（無料/有料・API有無・最適用途）

| ツール | 無料でできること | 主な有料機能 | API | 最適用途 |
|---|---|---|---|---|
| Hyperdash | ダッシュボード全般、Cohorts、Alphaリーダーボード | 執行（1.5bp）、コピートレード | **無し** | 分析＋執行の一体運用 |
| HyperTracker | 100 req/日、コホート閲覧、ウォレット検索 | REST/WS/Webhook、CSV、$179〜$2,399/月 | **有り（最充実）** | スマートマネーのAPI化・ボット |
| CoinGlass | クジラ監視・PnL分布の閲覧 | API $29〜$699/月、$1M+アラート | 有り | 複数取引所横断のクジラ監視 |
| Dexly | リーダーボード、Explorer、コピートレード | （基本無料） | 限定的 | 実現ベースの実力評価・深掘り |
| Nansen | 一部閲覧 | Smart Money Perps、Perp Leaderboard API、$49〜 | 有り | エンティティ・ラベル＋マルチチェーン |
| Arkham | コア分析無料 | API申請制 | 申請制 | エンティティ・資金フロー追跡 |
| Buildix | スクリーナー、VPIN、Smart Money Delta、BT | Kyle's Lambda、レジーム検知、API | Pro | オーダーフロー分析 |
| ASXN | 総合ダッシュボード全般 | （無料） | 有り（日次） | リサーチ・センチメント確認 |

### 2. Hyperliquid公式API詳細（自前データ取得）

#### 基本
- **infoエンドポイント**：`POST https://api.hyperliquid.xyz/info`、`Content-Type: application/json`、**認証キー不要**（読み取り専用）。ボディの `type` で取得対象を指定。
- **マスター/サブアカウント**：実アドレスを渡す必要がある。**agent（API）ウォレットのアドレスを渡すと空の結果**になる罠に注意。

#### clearinghouseState（建玉・マージンサマリー）
- リクエスト：`{"type":"clearinghouseState","user":"0x...","dex":""}`
- `dex` フィールドはperp dex名。空文字＝第一perp dex（標準のperps）。**HIP-3市場を指定**する場合は `"dex":"xyz"` のように指定。`"dex":"ALL_DEXES"` で単一ユーザーを全DEX横断取得。
- レスポンス：`marginSummary`（accountValue, totalNtlPos, totalRawUsd, totalMarginUsed）、`crossMarginSummary`、`crossMaintenanceMarginUsed`、`withdrawable`、`assetPositions`（各建玉）、`time`。
- 重要：エントリー価格・含みPnL・クローズPnLは**フロントエンドの便宜的表示**。会計の根本はmargin（spotはbalance）とtrades。含みPnL = `side*(mark_price - entry_price)*position_size`、クローズPnL = `fee + side*(mark_price - entry_price)*position_size`（クローズ時、オープン時はfeeのみ）。

#### userFills / userFillsByTime（約定履歴）
- `{"type":"userFills","user":"0x..."}` または `userFillsByTime` で `startTime`/`endTime`（ミリ秒）を指定。
- 各約定：`closedPnl, coin, crossed, dir（Open Long等）, hash, oid, px, side（B=買/A=売）, startPosition, sz, time, fee, feeToken, builderFee（任意）, tid`。HIP-3資産は `coin` がdex名プレフィックス付き（例 `xyz:XYZ100`）。
- 時間範囲指定は**1回500件まで**。それ以上は最終timestampを次の `startTime` にしてページング。`aggregate_by_time` で部分約定の結合可。

#### portfolio（時系列PnL）
- `{"type":"portfolio","user":"0x..."}`。
- レスポンスは `["day", {...}], ["week", ...], ["month", ...], ["allTime", ...], ["perpDay", ...], ["perpWeek", ...], ["perpMonth", ...], ["perpAllTime", ...]` の配列。各要素に **`accountValueHistory`（[timestamp, value]の配列）**、**`pnlHistory`（[timestamp, pnl]）**、`vlm`（出来高）。
- これが**リスク調整後リターン計算の主データ源**（後述）。

#### その他関連メソッド
- `candleSnapshot`（ローソク。`req` に coin/interval/startTime/endTime）、`fundingHistory`（コイン別ファンディング）、`userFunding`/`userFundingHistory`、`openOrders`/`frontendOpenOrders`（TP/SLトリガー含む）、`l2Book`、`recentTrades`、`metaAndAssetCtxs`、`spotClearinghouseState`、`vaultDetails`、`predictedFundings` 等。

#### 422エラー問題（オープンソースノード経由）
- QuickNode等の `/info` はオープンソースHyperCoreノードをプロキシし、**52メソッド中30のみネイティブ対応**。**Foundationインデクサ出力に依存するメソッド（`allMids, metaAndAssetCtxs, userFills, userFillsByTime, l2Book, recentTrades, candleSnapshot, portfolio, fundingHistory, orderStatus` 等）は 422 "Failed to deserialize" を返す。**
- 対処：**公式 `api.hyperliquid.xyz/info` を直接叩く**（最も確実）。あるいはgRPCストリーミング/SQL Explorer等の代替。`portfolio` は「公式公開APIのみ」と明記されている。

#### レートリミット
- **IP単位**：RESTは加重合計**1,200/分**。`l2Book, allMids, clearinghouseState, orderStatus, spotClearinghouseState, exchangeStatus` は weight 2、`userRole` は60、その他documented infoは weight 20。さらに `userFills, userFillsByTime, fundingHistory` 等は**返却20件ごとに追加加重**、`candleSnapshot` は60件ごとに追加加重。
- **WebSocket**：最大10接続、新規接続30/分、サブスクリプション最大**1,000**、user固有サブは最大10ユーザー、メッセージ2,000/分、inflight post 100。
- **アドレス単位**：累積取引1 USDCあたり1リクエスト、初期バッファ10,000リクエスト。レート超過時は10秒に1リクエスト（取引アクションに適用、info照会には非適用）。
- **EVM JSON-RPC**：`rpc.hyperliquid.xyz/evm` は100/分。
- 推奨：低レイテンシのリアルタイムはWebSocket、オンデマンドの照会にRESTを温存。

#### WebSocket（リアルタイム購読）
- URL：`wss://api.hyperliquid.xyz/ws`。`{"method":"subscribe","subscription":{"type":"trades","coin":"SOL"}}` 形式。
- 主なチャネル：`trades, l2Book, bbo, candle, allMids, notification, orderUpdates, userFills, webData2, activeAssetCtx, clearinghouseState, openOrders, twapStates` 等。`allMids` のみ全市場集約。ユーザー系（userFills等）は初回 `isSnapshot: true`。
- バッチ購読不可（1市場1サブスク）。切断は予告なく起こり得るため再接続必須。

#### Python SDK
- **公式 `hyperliquid-python-sdk`（hyperliquid-dex）**。`pip install hyperliquid-python-sdk`。
  ```python
  from hyperliquid.info import Info
  from hyperliquid.utils import constants
  info = Info(constants.MAINNET_API_URL, skip_ws=True)
  state  = info.user_state("0x...")            # = clearinghouseState
  fills  = info.user_fills("0x...")
  fills_t = info.user_fills_by_time("0x...", start_time, end_time)
  ```
- 主なinfoメソッド：`user_state`（clearinghouseState）、`spot_user_state`、`open_orders`、`all_mids`、`user_fills`、`user_fills_by_time`、`funding_history`、`user_funding_history`、`candle_snapshot`。取引系は `Exchange` クラス（EIP-712署名処理）。開発はPython 3.10ちょうどを要求、Poetry v1系。
- コミュニティSDK：TypeScript（nktkas/hyperliquid、nomeida/hyperliquid）、Go（sonirico/go-hyperliquid）、CCXT等。

### 3. 「上手いトレーダー」と「運が良かっただけ」の見分け方

#### 総PnL順リーダーボードの問題点
- **生存者バイアス**：公開リーダーボードは現存する勝者しか映さない。同じ戦略で破産した多数のウォレットは消えている。極端なレバレッジで一発当てたウォレットが上位に来やすい。
- **含み益（未実現損益）の罠**：総PnL順の多くは未実現益を含む。Hyperliquidでは含みPnLは `side*(mark-entry)*size` のフロントエンド表示に過ぎず、決済まで確定しない。Dexlyのように**クローズ済みベース**で見ると実力が出やすい。
- **レバレッジ歪み**：高レバレッジは小資金でも巨額PnLを生むが、ドローダウンも比例して巨大。PnL絶対額は実力の指標にならない。
- **ROIの定義差**：Hyperliquid公式ROIは `PnL / max(100, 起点account value + 最大ネット入金)`。アカウント間で起点が違うと比較不能。Nansen等は日付範囲やaccount value下限フィルタで補正。

#### スコアリングに使うべき指標
1. **試行回数**：総トレード数・稼働日数。少数のトレードで大半の利益が出ているウォレットは運の可能性大。統計的に意味のある最低トレード数（目安: 数十〜100超）を満たすか。
2. **一貫性**：勝率 × 平均損益比（payoff ratio）、profit factor、expectancy。最大ドローダウン（peak-to-trough）と回復時間。Sharpe的なリスク調整後リターン。
3. **稼働期間とレジーム跨ぎの生存**：単一の強気相場でしか結果が出ていないか、ボラ拡大局面・トレンド転換を生き延びたか。3か月のSharpeはほぼ無意味、複数レジームでの一貫性を見る。
4. **リターンの源泉（アルファ源泉）の区別**：
   - **方向性アルファ**：価格予測で稼ぐ（再現性の評価が最重要）。
   - **ファンディング・ファーミング**：デルタニュートラルでファンディング収益。低ボラ・高Sharpeに見えるが性質が違う。`userFunding` と建玉の符号で判別。
   - **マーケットメイキング**：多数の小約定、メイカー比率高、両面約定。`userFills` の `crossed=false`（メイカー）比率や約定頻度で推定。
5. **キャパシティ（口座サイズ帯）**：小口で機能する戦略が大口で通用するとは限らない。HyperTrackerのequityコホート、CoinGlassのサイズ別分類で「自分と同じ資金帯」のウォレットを選ぶ。

#### リスク調整後リターンの具体的計算（オンチェーンfill履歴から）
**手順A（portfolioベース・推奨）**
1. `portfolio` の `perpAllTime`（または `perpMonth`）から `accountValueHistory` を取得。
2. 等間隔（例：日次）にリサンプルし、日次リターン `r_t = (V_t - V_{t-1}) / V_{t-1}` を計算（入出金で歪むため、可能なら `pnlHistory` の差分とaccountValueで入出金調整）。
3. **Sharpe**（年率）= `(平均(r_t) - r_f) / 標準偏差(r_t) × √365`。`r_f` は2026年の米T-bill約4〜5%を日次換算（例：日次≈0.011%）。crypto戦略の床はSharpe≈1.0。
4. **Sortino**：分母を下方偏差（負のリターンのみの標準偏差）に置換。
5. **最大ドローダウン**：`accountValueHistory` の累積最大からの最大下落率。Sharpeと必ず併記（Sharpe 1.5でも70%DDがあり得る）。

**手順B（fillベース・入出金に頑健）**
1. `userFillsByTime` で全約定を取得（500件ごとページング）。
2. 各約定の `closedPnl` と `fee` を時系列に積み上げ、実現PnL曲線を構築。
3. 一定区間（日次など）に集計してリターン列化→Sharpe/Sortino/DD/profit factor/勝率/平均保有時間を算出。
4. メイカー比率（`crossed`）、資産別PnL寄与、`dir` 別（Open/Close × Long/Short）でアルファ源泉を分解。

**注意**：入出金（`portfolio` の非ファンディング台帳更新＝deposits/transfers/withdrawals）を調整しないとリターンが歪む。`accountValueHistory` の段差が入出金由来か損益由来かを `userFunding`・台帳で切り分ける。

### 4. 集団ポジショニングのシグナル化（AI/アルゴ戦略への組み込み）

#### 特徴量化
- **スマートマネー上位群のネットL/S**：HyperTrackerのコホート（例 "Profitable Large"）やHyperdashのCohorts（"Extremely Profitable" +$1M）について、資産別の**ネットnotional（ロング−ショート）**、トレーダー数、含みPnL分布を時系列で記録。
- **L/S比率**：account count比（>1で多数派ロング）と**capital（notional）比**を区別。account数とサイズは別物——少数派が大サイズを持つ場合がある。
- **多数派サイドの含み損益**：多数派が含み損を抱える＝清算燃料の蓄積。クジラの含みPnLが大きく振れる局面は要警戒。
- **ファンディング × OI**：ファンディングが極端に正＋OIが高い＝クラウデッド・ロング（下落時に清算カスケード燃料）。逆も同様。CoinGlass/Buildixのファンディング・OIと組み合わせる。

#### クラウディング検知・ダイバージェンス
- **クラウディング**：L/S比やファンディングが極端（例：歴史的にロング>70%は過熱）に振れたら、トレンド追随から逆張りへの優位性シフトを示唆。「明らかな取引」と皆が思う時が最も危険。
- **ダイバージェンス・シグナル**：公開センチメント（全体L/S）が一方向に偏る一方で、**スマートマネー上位群が反対方向**に動く（=賢い資金が利確/リスク削減/パニック吸収）局面が最も注目度が高い。一致なら「過熱でもトレンド継続」、乖離なら「反転リスク上昇」と解釈。
- 単体指標で判断せず、価格・ファンディング・流動性・ウォレット挙動を重ねる。

#### バックテストの重要性と「生フォロー」を避ける理由
- スマートマネーのポジションは**遅延して観測**される（オンチェーン確定後）うえ、クジラはヘッジ・分割・即時クローズし、全体戦略は見えない。生のミラーリングはエントリー/イグジットの遅延と部分情報で負けやすい。
- 必ず**特徴量→シグナル→バックテスト→フォワードテスト**の順で検証。手数料・スリッページ・約定遅延・過剰最適化（カーブフィッティング）・ルックアヘッドバイアスを織り込む。Sharpe・最大ドローダウンを必ず計測し、複数レジームで検証。

### 5. 注意点・リスク

- **これは投資助言ではない**：本ドキュメントは分析・学習・研究目的の技術情報。
- **過去の実績は将来を保証しない**：リーダーボード・コホートの過去成績は将来の結果を保証しない。上位ランクのトレーダーでも損失を被り得る。
- **プロップ口座（特にPropr）での複製リスク**：Proprは規約上**コピートレード自体は許可**（自分の複数Propr口座間も含む）し、ボット/EAも許可。ただし**①口座間の対向ヘッジ、②他トレーダーとの共謀・ドローダウン機構を突くタイミング共有シグナル、③ウォッシュ取引、④レイテンシ・アービトラージ**は禁止で、違反は**即時口座終了・ノーペイアウト・将来評価からの永久BAN（不服申立不可）**。検知には**オンチェーン取引分析（Hyperliquid）、口座間相関分析、IP/デバイスフィンガープリント、Chainalysisエンティティデータ、ウォレット＋KYC＋資金源＋IP＋デバイスのリンクグラフ**を使用。なお**A-bookの取引のみオンチェーン**でB-book（内部）はオンチェーンに出ない点も留意。**外部ウォレットの単純な同方向ミラーリングを名指しで禁ずる条文は公開規約には確認できなかった**が、共謀/シグナル共有条項に抵触し得るため、学習・自戦略構築に留めるのが安全。比較対象として**Breakout**（Kraken傘下）は「異なるユーザー間のコピートレード禁止」「相関資産での対向ポジション禁止」を明文化（業界一般慣行：自己口座間のコピーは許可、他トレーダー口座からのコピーは原則禁止）。
- **Proprの基本条件**（同社Rulebook v1.0等に基づく報告値・要再確認）：利益分配80%、最大ファンディング$100K（合算$200K）、ペイアウトはUSDCオンチェーンで24h以内・最低$50、チャレンジ料は1-Stepで$60〜$999、2-Stepで$50〜$749。レバレッジBTC/ETH 5x・他crypto 2x・株/商品4x。米英露＋OFAC制裁国は対象外。運営はXBorg Limited（BVI、無規制）。$PROPRは2026年8月TGE予定（シードは$17.5M FDV）。なお同種のオンチェーンHyperliquidプロップにはHypernova（最大$200K、90%分配を標榜、Lemniscapリードで$3Mプレシード調達）、HyperPnL、Breakout（Kraken買収）、Upscale Tradeがある。
- **オンチェーンデータの限界**：①含みPnLはフロントエンド表示で確定益ではない、②サブアカウント/複数ウォレットへの分散で実態が見えにくい、③CEXや他チェーンでのヘッジは見えない、④ラベリング（Nansen/Arkham）は確率的・proprietaryで誤りを含む、⑤ダッシュボードのリフレッシュ遅延（ASXNは日次、HyperTrackerは5分）、⑥オープンソースノードの422問題でメソッドにより公式API直叩きが必要。

---

## Recommendations

**段階1（無料・即着手）**：ASXN/HyperScreenerとDexlyで候補ウォレットを発掘し、CoinGlassでサイズ帯・クジラ動向、HyperTracker無料枠（100 req/日）でコホートを確認。Hyperdashで利益帯別ポジショニングを目視。ここでは「総PnL順」を鵜呑みにせず、クローズ済みベース（Dexly）と複数時間枠の一貫性を見る。

**段階2（自前検証パイプライン構築）**：公式 `api.hyperliquid.xyz/info` を直接叩き（422回避）、候補ウォレットの `clearinghouseState`・`userFillsByTime`・`portfolio` をPython SDKで取得。手順A/Bでリスク調整後リターン（Sharpe・Sortino・最大DD・profit factor・勝率・平均保有時間）とアルファ源泉（方向性/ファンディング/MM）を算出。**スコア閾値の目安**：トレード数≥100、稼働≥90日かつ2レジーム以上を生存、年率Sharpe≥1.0（理想≥1.5）、最大DD≤戦略許容内、少数トレードへの利益集中が無いこと。これらを満たさないウォレットは「運」候補として除外。

**段階3（シグナル化＋バックテスト）**：合格ウォレット群（自分と同じequity帯）のネットL/S・notional・含みPnL・ファンディング×OIを特徴量化。クラウディング/ダイバージェンス・シグナルを定義し、手数料・スリッページ・遅延込みでバックテスト→フォワードテスト。**生フォローはしない**。

**段階4（必要に応じてAPI課金）**：リアルタイム性・規模が必要ならHyperTracker（Pulse $179〜、WebSocket/WebhookはStream $2,399）、エンティティ・ラベルが要るならNansen（$49〜）。複数取引所横断監視はCoinGlass（$29〜）。

**閾値が変わる条件**：①Hyperdashが公開APIを出したら段階2のデータ源に追加（現状UIロックで不可）。②対象がHIP-3市場中心なら `dex` 指定（`clearinghouseState` の `dex`、fillの `coin` プレフィックス）を必須化。③Proprなど資金化を検討する場合は、コピー/相関に関する最新Rulebook（v更新）を都度確認し、A-book/B-book表示を点検。④レートリミット（1,200/分加重）に当たるならWebSocket移行とバッチ設計。

---

## Caveats
- 本資料は2026年6月時点の公開情報に基づく技術リサーチであり、**投資助言ではない**。料金・機能・規約は変動する（特にHyperdash V2の段階展開、Proprの規約改定、Nansen/CoinGlassの価格改定）。
- ツールのウォレット数・カバレッジ・更新頻度はベンダー公称値を含む。HyperTrackerの追跡数は表示時点で2,039,387（Active Perp Traders 217,850）、Perp PnL資格ウォレットは266,408、CoinGlassのアドレス数は約35万との記載があるが、計測時点で変動する。
- Proprの「コピー許可だが相関・共謀は禁止」は同社Rulebook v1.0およびBusinessページの記載に基づく報告であり、外部ウォレットの同方向ミラーリングを名指しで禁ずる条文は確認できず、共謀/シグナル共有条項への抵触リスクとして整理した。具体的な数値（チャレンジ料・分配率・TGE時期等）は一次規約での再確認を推奨。実際の運用・エンフォースメント事例は launch 直後で乏しい。
- オンチェーン分析は含みPnL・サブアカウント分散・CEX/他チェーンヘッジ・ラベル誤りなどの構造的限界を持つ。最終判断は自己責任で。