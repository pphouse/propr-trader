# CRONJOB — 20分定期自動売買のセットアップ手順

`autopilot/run.sh` を cron で20分ごとに起動して、`claude -p` に投資判断・執行・記録をさせる仕組み。

## 構成

```
autopilot/
├── prompt.md         # claude -p に毎回渡す指示書(コンテキスト)
├── run.sh            # cronが叩く wrapper
├── logs/
│   ├── YYYY-MM-DD.log         # 人が読む実行ログ
│   ├── YYYY-MM-DD.runs.jsonl  # コスト・session追跡用 (claude --output-format json)
│   └── YYYY-MM-DD.err         # stderr
└── CRONJOB.md        # このファイル
```

## 事前準備

### 1. claude CLI の OAuth トークン生成 (cron用、keychain回避)

```bash
claude setup-token
# 1年有効のtokenが出力される。コピーして次の手順で使う
```

### 2. ~/.zshrc に環境変数を追加

```bash
echo 'export CLAUDE_CODE_OAUTH_TOKEN="<コピーしたtoken>"' >> ~/.zshrc
source ~/.zshrc
```

### 3. claude のパス確認

```bash
which claude
# /Users/naoto/.npm-global/bin/claude などが出る
# 違ったら run.sh の CLAUDE_BIN を修正
```

### 4. ローカルで手動テスト (cron登録前に必ず)

```bash
cd /Users/naoto/propr
CLAUDE_CODE_OAUTH_TOKEN="<token>" bash autopilot/run.sh
cat autopilot/logs/$(date +%Y-%m-%d).log
```

判断と実行が想定通りなら次へ。

## cron 登録

### 5. crontab エントリ追加

```bash
crontab -e
```

以下を追記:

```cron
# 環境変数 (cronはshell rc読まないため明示)
PATH=/usr/local/bin:/usr/bin:/bin:/Users/naoto/.npm-global/bin
CLAUDE_CODE_OAUTH_TOKEN=<your-token-here>

# 20分ごとにpropr.xyz投資判断
*/20 * * * * /Users/naoto/propr/autopilot/run.sh
```

`*/20 * * * *` = 毎時 0/20/40分 に実行。

### 6. Mac スリープ防止 (必須)

cron は Mac がスリープ中は動かない。caffeinate でディスプレイOFFでもCPU稼働させる:

```bash
# 別途常駐させる (起動時自動化したいなら launchd)
nohup caffeinate -i &
```

または、システム設定 > バッテリー > "ディスプレイのスリープ中もネットワーク経由のアクセスを可能に" をON。

## 運用

### ログ確認

```bash
# 今日の判断ログ
tail -f /Users/naoto/propr/autopilot/logs/$(date +%Y-%m-%d).log

# 累積コスト確認
jq -r '.total_cost_usd' /Users/naoto/propr/autopilot/logs/*.runs.jsonl | awk '{sum+=$1} END {print "$" sum}'

# エラー
cat /Users/naoto/propr/autopilot/logs/$(date +%Y-%m-%d).err
```

### 停止

```bash
crontab -e
# */20 ... の行をコメントアウト or 削除
```

緊急停止が必要なら:

```bash
crontab -r  # 全crontab削除 (注意: 他のcronも消える)
```

### 実行間隔の変更

| 間隔 | cron | 1日runs | 月額目安 |
|---|---|---|---|
| 10分 | `*/10 * * * *` | 144 | ~$195 |
| 20分 | `*/20 * * * *` | 72 | **~$97** ⬅ デフォルト |
| 30分 | `*/30 * * * *` | 48 | ~$65 |
| 1時間 | `0 * * * *` | 24 | ~$32 |

(Sonnet 4.6 / 1run = ~5k in + ~2k out = $0.045想定)

トレンドフォロー戦略なら20-30分で十分。HFTじゃないので10分以下は無駄。

## コスト見積もり詳細

| 項目 | 単価 | 1run | 72runs/日 | 月 |
|---|---|---|---|---|
| Input (5k tok) | $3/MT | $0.015 | $1.08 | ~$32 |
| Output (2k tok) | $15/MT | $0.030 | $2.16 | ~$65 |
| **合計** | — | **$0.045** | **$3.24** | **~$97** |

実際の input tokens は prompt.md (~2k) + STRATEGY.md/KNOWLEDGE.md読込 (~3k) + snapshot output (~1-2k) で5-7k見込み。Output は判断+ログで1-2k見込み。

ポジション動かないターンが多ければ output が小さくなりコスト下がる。

## 既知の制約

- **Mac スリープ中は動かない**。caffeinate 必須。
- **OAuth token は1年で失効**。期限管理 (cal リマインド推奨)。
- **claude -p の決定は確率的**。同じ状況でも判断がブレうる。重要な変更は STRATEGY.md に書いて将来のClaudeに渡す。
- **rate limit**: 20分間隔 × 72回/日なら propr 1200 req/min には遠く届かない。
- **prompt.md の指示は絶対ではない**。指示を破る判断もありえる。logsを定期的にレビュー必須。

## トラブルシューティング

| 症状 | 確認 |
|---|---|
| 何も書かれない | `cat logs/$(date +%Y-%m-%d).err`、cronエントリの環境変数 |
| auth error | OAuth token期限切れ・PATH問題。`claude setup-token` で再生成 |
| api.py が ModuleNotFound | python3が必要なpkg(python-ulid)入ってない。`pip3 install python-ulid` |
| 全部実行されてない | Macスリープ中。`pmset -g log | grep -i sleep` で確認 |
| 過剰トレード | prompt.md の「何もしない」を強調する条件を追記 |
