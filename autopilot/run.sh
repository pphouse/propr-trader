#!/bin/bash
# cronから起動される自動売買 wrapper。
# 20分ごとに claude -p を起動して投資判断+執行+記録を行う。
#
# セットアップ手順は CRONJOB.md を参照。
set -euo pipefail

# 絶対パスで作業ディレクトリ確定 (cronは / がcwdのため)
REPO="/Users/naoto/propr"
cd "$REPO"

# cron環境では PATH が貧弱で python3 resolution が miniforge3 を拾い、
# python-ulid が無いため snapshot.py が import fail する。
# pyenv shims を先頭に置いて、shellと同じpython3 (3.9 + ulid) を使う。
export PATH="/Users/naoto/.pyenv/shims:$PATH"

LOG_DIR="$REPO/autopilot/logs"
mkdir -p "$LOG_DIR"
TODAY=$(date +%Y-%m-%d)
LOG="$LOG_DIR/$TODAY.log"
JSONL="$LOG_DIR/$TODAY.runs.jsonl"
ERR="$LOG_DIR/$TODAY.err"

# 開始ヘッダ
{
  echo ""
  echo "============================================================"
  echo "=== run @ $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "============================================================"
} >> "$LOG"

# 1) Snapshot を必ず撮る (Claudeまかせにしない、また /tmp/propr_current.json にコンパクト版を出力)
cd "$REPO/free"
python3 -c "
import sys, json
sys.path.insert(0, '.')
import api

acc = api.account()
pos_open = api.positions(status='open')['data']
pos_closed = api.positions(status='closed')['data']
orders = api.get('/accounts/' + api.ACCOUNT_ID + '/orders', limit=30)['data']
trades = api.get('/accounts/' + api.ACCOUNT_ID + '/trades', limit=20)['data']

# Hyperliquid市況
import urllib.request
req = urllib.request.Request('https://api.hyperliquid.xyz/info',
    data=json.dumps({'type':'metaAndAssetCtxs'}).encode(),
    headers={'Content-Type':'application/json'})
hl = json.loads(urllib.request.urlopen(req).read())
universe, ctxs = hl[0]['universe'], hl[1]
focus_assets = {'BTC','ETH','SOL','HYPE','DOGE','XRP','AVAX','LINK','SUI'}
focus_assets.update(p['asset'] for p in pos_open if float(p['quantity']) != 0)
mkt = {}
for u, c in zip(universe, ctxs):
    if u['name'] not in focus_assets: continue
    mid = float(c.get('markPx',0)); prev = float(c.get('prevDayPx',0))
    chg = (mid/prev - 1)*100 if prev else 0
    mkt[u['name']] = {'mid':mid, 'chg24h_pct':round(chg,2), 'funding':float(c.get('funding',0))}

compact = {
  'now_utc': __import__('datetime').datetime.utcnow().isoformat()+'Z',
  'account': {
    'marginBalance': acc['marginBalance'],
    'balance': acc['balance'],
    'totalUnrealizedPnl': acc['totalUnrealizedPnl'],
    'totalInitialMargin': acc['totalInitialMargin'],
    'availableBalance': acc['availableBalance'],
    'highWaterMark': acc['highWaterMark'],
  },
  'positions_open': [
    {'asset':p['asset'],'side':p['positionSide'],'qty':p['quantity'],
     'entry':p['entryPrice'],'mark':p['markPrice'],
     'uPnL':p['unrealizedPnl'],'lev':p['leverage'],
     'margin':p['marginUsed'],'breakEven':p['breakEvenPrice'],
     'positionId':p['positionId']}
    for p in pos_open if float(p['quantity']) != 0
  ],
  'positions_closed_today': [
    {'asset':p['asset'],'side':p['positionSide'],'entry':p['entryPrice'],
     'realizedPnl':p['realizedPnl'],'closedAt':p['closedAt']}
    for p in pos_closed
    if p.get('closedAt','') >= __import__('datetime').date.today().isoformat()
  ],
  'pending_protective_orders': [
    {'asset':o['asset'],'type':o['type'],'trigger':o['triggerPrice'],
     'qty':o['quantity'],'positionId':o['positionId']}
    for o in orders if o['status']=='pending'
  ],
  'recent_trades_5': [
    {'asset':t['asset'],'type':t['type'],'side':t['side'],
     'price':t['price'],'qty':t['quantity'],'pnl':t['realizedPnl'],'at':t['executedAt']}
    for t in trades[:5]
  ],
  'market_24h': mkt,
}

# 日次realized集計
today = __import__('datetime').date.today().isoformat()
realized_today = sum(float(t['realizedPnl']) for t in trades if t.get('executedAt','')[:10] == today)
compact['account']['realized_today'] = round(realized_today, 4)

with open('/tmp/propr_current.json','w') as f:
    json.dump(compact, f, indent=2, default=str)

# 時系列snapshotsにも保存
from pathlib import Path
import datetime
now = datetime.datetime.utcnow()
out_dir = Path('$REPO/snapshots') / now.strftime('%Y-%m-%d')
out_dir.mkdir(parents=True, exist_ok=True)
out = out_dir / (now.strftime('%H-%M') + '-utc-auto.json')
out.write_text(json.dumps(compact, indent=2, default=str))
print(f'snapshot ok: {out}')
" >> "$LOG" 2>>"$ERR" || {
  echo "[error] snapshot failed, abort" >> "$LOG"
  exit 1
}
cd "$REPO"

# cron環境ではkeychainアクセス不可。下記2つのいずれか必須:
#   - ANTHROPIC_API_KEY (API直課金、推奨)
#   - CLAUDE_CODE_OAUTH_TOKEN (Pro/Max plan枠使用、`claude setup-token` で生成)
if [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
  echo "[warn] Neither ANTHROPIC_API_KEY nor CLAUDE_CODE_OAUTH_TOKEN is set." >> "$LOG"
  echo "[warn] cron auth will fail (keychain not accessible from cron)." >> "$LOG"
fi

# claudeフルパスはセットアップ環境で確認 (which claude)
CLAUDE_BIN="${CLAUDE_BIN:-/Users/naoto/.npm-global/bin/claude}"

# Sonnet 4.6 で実行 (Opusは高すぎる、Haikuは判断力不足)
# --dangerously-skip-permissions: cronでの完全自動化のため必須
# --output-format json: コスト・session追跡用
PROMPT=$(cat "$REPO/autopilot/prompt.md")

"$CLAUDE_BIN" -p "$PROMPT" \
  --model claude-sonnet-4-6 \
  --dangerously-skip-permissions \
  --output-format json \
  --max-budget-usd 0.30 \
  --fallback-model claude-haiku-4-5 \
  2>>"$ERR" \
  | tee -a "$JSONL" \
  | jq -r '
      "--- result ---",
      (.result // "(no result field)"),
      "--- meta ---",
      "session: \(.session_id // "n/a")",
      "cost:    $\(.total_cost_usd // 0)",
      "duration:\(.duration_ms // 0)ms",
      "turns:   \(.num_turns // 0)",
      ""
    ' >> "$LOG" 2>>"$ERR" || {
      echo "[error] claude or jq failed, see $ERR" >> "$LOG"
    }

echo "=== end @ $(date '+%H:%M:%S') ===" >> "$LOG"
