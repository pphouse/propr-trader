#!/bin/bash
# cronから起動される自動売買 wrapper。
# 20分ごとに claude -p を起動して投資判断+執行+記録を行う。
#
# セットアップ手順は CRONJOB.md を参照。
set -euo pipefail

# 絶対パスで作業ディレクトリ確定 (cronは / がcwdのため)
REPO="/Users/naoto/propr"
cd "$REPO"

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
