"""アカウント/ポジ/オーダー/取引のスナップショットを撮って snapshots/YYYY-MM-DD/HH-MM-utc-snapshot.json に保存。

使い方:
    python3 snapshot.py                    # 普通のスナップショット
    python3 snapshot.py "BTC short entry"  # context注釈付き

書き出した後、Claude側で MCP 経由で Google Drive にもアップロードする。
Driveフォルダ: https://drive.google.com/drive/folders/1TQqCOozs7OBji5t7P_dnzlDhOgG-QQUe
"""
import sys, os, json
from datetime import datetime, timezone
from pathlib import Path
import api

context = sys.argv[1] if len(sys.argv) > 1 else None

now = datetime.now(timezone.utc)
date_str = now.strftime("%Y-%m-%d")
time_str = now.strftime("%H-%M")

# /Users/naoto/propr/snapshots/YYYY-MM-DD/HH-MM-utc-snapshot.json
root = Path(__file__).resolve().parent.parent
out_dir = root / "snapshots" / date_str
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / f"{time_str}-utc-snapshot.json"

snapshot = {
    "snapshotTakenAt": now.isoformat(),
    "context": context,
    "account": api.account(),
    "positions": (
        api.positions(status="open")["data"]
        + api.positions(status="closed")["data"]
    ),
    "orders": api.get(f"/accounts/{api.ACCOUNT_ID}/orders", limit=100)["data"],
    "trades": api.get(f"/accounts/{api.ACCOUNT_ID}/trades", limit=100)["data"],
}

with open(out_path, "w") as f:
    json.dump(snapshot, f, indent=2, default=str)

print(f"saved: {out_path}")
print(f"  positions: {len(snapshot['positions'])}")
print(f"  orders:    {len(snapshot['orders'])}")
print(f"  trades:    {len(snapshot['trades'])}")
print(f"  mb=${snapshot['account']['marginBalance']} uPnL=${snapshot['account']['totalUnrealizedPnl']}")
