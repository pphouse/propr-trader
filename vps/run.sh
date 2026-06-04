#!/bin/bash
# Called every 10 min by cron. Runs one autopilot judgment cycle.
set -euo pipefail

REPO_DIR="$HOME/propr-trader"
ENV_FILE="$HOME/.propr-env"

# 1. Load secrets
if [ ! -f "$ENV_FILE" ]; then
  echo "[$(date -u +%FT%TZ)] FATAL: $ENV_FILE missing"
  exit 1
fi
# shellcheck disable=SC1090
source "$ENV_FILE"

# 2. Ensure binaries on PATH (cron has a stripped PATH)
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin"

# 3. cd into repo so claude sees the right working dir
cd "$REPO_DIR"

# 4. Pull latest prompt/strategy/code (cheap)
git pull --ff-only --quiet || true

# 5. Header
echo "============================================================"
echo "[$(date -u +%FT%TZ)] autopilot run starting"
echo "============================================================"

# 6. Run claude headless. Prompt goes via stdin so --allowed-tools
#    (variadic) doesn't swallow the prompt as one of its values.
cat <<'PROMPT' | claude --print --dangerously-skip-permissions --allowed-tools "Bash Read Write Edit WebSearch WebFetch Glob Grep"
Read `autopilot/prompt.md` from this repo and execute the instructions exactly. This is the propr.xyz autopilot, running on an ablenet VPS cron every 10 minutes.

Key reminders:
- The VPS has full network access (api.propr.xyz, api.hyperliquid.xyz both reachable).
- PROPR_API_KEY is set as an env var; free/api.py reads it via os.environ.
- Default account: urn:prp-account:xREXiJC2b4He (Free Trial paper $5k).
- DO NOT git commit/push. Working-tree changes are discarded by the next cron run pulling fresh master.
- Goal: reach +10% ($5500) — be ACTIVE, target 3 concurrent positions, follow the prompt's aggressive judgment axes.

Follow autopilot/prompt.md end-to-end (snapshot → news scan → judge → execute → markdown summary).
PROMPT

echo
echo "[$(date -u +%FT%TZ)] autopilot run finished"
echo
