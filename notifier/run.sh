#!/bin/bash
# Mac cron から呼ばれる wrapper.
# crontab: */10 * * * * /Users/naoto/propr/notifier/run.sh
set -e

REPO="/Users/naoto/propr"
ENV_FILE="$REPO/notifier/.env"

# secrets load
if [ ! -f "$ENV_FILE" ]; then
    echo "[FATAL] $ENV_FILE missing" >&2
    exit 1
fi
# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

# cron は最小 PATH なので明示的に指定
# miniforge3 の python3 を使う (ulid 既導入の環境)
PYTHON="/Users/naoto/miniforge3/bin/python3"
export PATH="/Users/naoto/miniforge3/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

cd "$REPO"
exec "$PYTHON" notifier/watcher.py
