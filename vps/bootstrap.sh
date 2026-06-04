#!/bin/bash
# propr-trader VPS bootstrap (Ubuntu 22.04 / 24.04, run as the user that owns ~/)
#
# Usage on a fresh Hetzner CX11:
#   curl -fsSL https://raw.githubusercontent.com/pphouse/propr-trader/master/vps/bootstrap.sh | bash
#
# After this runs, edit ~/.propr-env with your two secrets, then test:
#   ~/propr-trader/vps/run.sh
#
# Cron entry is installed automatically (every 10 min). Logs go to ~/autopilot.log
set -euo pipefail

REPO_URL="https://github.com/pphouse/propr-trader.git"
REPO_DIR="$HOME/propr-trader"
ENV_FILE="$HOME/.propr-env"
LOG_FILE="$HOME/autopilot.log"

echo "==> apt update + base packages"
sudo apt-get update -qq
sudo apt-get install -y -qq curl git python3 python3-pip ca-certificates

echo "==> Install Node 22 (NodeSource)"
if ! command -v node >/dev/null || [ "$(node -v | sed 's/v//; s/\..*//')" -lt 20 ]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
  sudo apt-get install -y -qq nodejs
fi
node -v
npm -v

echo "==> Install Claude Code CLI globally"
sudo npm install -g @anthropic-ai/claude-code
claude --version || true

echo "==> pip install Python deps"
pip3 install --break-system-packages --quiet python-ulid

echo "==> Clone or update repo at $REPO_DIR"
if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$REPO_DIR"
fi

echo "==> Create $ENV_FILE template (only if missing)"
if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<'EOF'
# propr-trader runtime secrets — keep this file mode 600
export PROPR_API_KEY="pk_live_REPLACE_ME"
export CLAUDE_CODE_OAUTH_TOKEN="sk-ant-oat01-REPLACE_ME"
# optional override (defaults to Free Trial account in api.py)
# export PROPR_ACCOUNT_ID="urn:prp-account:xREXiJC2b4He"
EOF
  chmod 600 "$ENV_FILE"
  echo "    -> created template, fill in the two REPLACE_ME values"
else
  echo "    -> existing $ENV_FILE preserved"
fi

echo "==> Install cron entry (every 10 min)"
CRON_LINE="*/10 * * * * $REPO_DIR/vps/run.sh >> $LOG_FILE 2>&1"
if crontab -l 2>/dev/null | grep -qF "$REPO_DIR/vps/run.sh"; then
  echo "    -> cron entry already present"
else
  (crontab -l 2>/dev/null || true; echo "$CRON_LINE") | crontab -
  echo "    -> installed: $CRON_LINE"
fi

echo
echo "==> DONE. Next steps:"
echo "  1. Edit $ENV_FILE and put the real PROPR_API_KEY and CLAUDE_CODE_OAUTH_TOKEN"
echo "  2. Test once manually:   $REPO_DIR/vps/run.sh"
echo "  3. Watch logs:           tail -f $LOG_FILE"
echo "  4. Verify cron is live:  crontab -l"
