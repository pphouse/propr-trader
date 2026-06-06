"""propr ポジション ポーリング + diff検知 → Charon voice で通知.

Mac の cron から 10分毎に呼び出される想定。
state は ~/.propr-notifier-state.json に保持。
VPS の autopilot.log を ssh で fetch して 判断 reasoning も加える。
"""
import os
import sys
import json
import subprocess
import re
from pathlib import Path
from datetime import datetime, timezone

# free/api.py を import するため path追加
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / 'free'))
import api  # noqa: E402

from play import speak  # noqa: E402

STATE_FILE = Path.home() / '.propr-notifier-state.json'
VPS = 'ubuntu@128.22.161.56'


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {'last_check': None, 'positions': {}}


def save_state(s):
    STATE_FILE.write_text(json.dumps(s, indent=2, default=str))


def fetch_vps_log(lines=200):
    """ssh 鍵認証で VPS の autopilot.log 末尾を取得。 失敗時 None."""
    try:
        r = subprocess.run(
            ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
             VPS, f'tail -{lines} ~/autopilot.log'],
            capture_output=True, text=True, timeout=20
        )
        if r.returncode == 0:
            return r.stdout
    except Exception:
        pass
    return None


def extract_reason_from_log(log_text):
    """最新の Claude 判断 reasoning を log から抜く.

    各 cycle は '[YYYY-MM-DDTHH:MM:SSZ] autopilot run starting' で始まり
    'autopilot run finished' で終わる。 最後の "judgment" sectionを抜く。
    """
    if not log_text:
        return None
    # 最後の cycle 末尾100行ぐらいから 「### 🎯 判断」 or '判断' の sectionを探す
    tail = log_text.split('\n')[-150:]
    # 「### 🎯」 〜 「###」 もしくは end までを抽出
    text = '\n'.join(tail)
    m = re.search(r'(?:### 🎯|### .*判断|🎯)([^\n]*\n[^#]*?)(?=###|\Z)', text)
    if m:
        return m.group(1).strip()[:400]
    # fallback: 末尾80字
    return text[-400:].strip()


def main():
    state = load_state()

    try:
        acc = api.account()
        pos_open = [p for p in api.positions(status='open')['data']
                    if float(p['quantity']) != 0]
        trades = api.get(f'/accounts/{api.ACCOUNT_ID}/trades', limit=15)['data']
    except Exception as e:
        print(f'[ERROR] propr API: {e}', file=sys.stderr)
        return

    # 現ポジ snapshot
    current = {p['positionId']: {
        'asset': p['asset'],
        'side': p['positionSide'],
        'qty': p['quantity'],
        'entry': p['entryPrice'],
        'mark': p['markPrice'],
        'uPnL': p['unrealizedPnl'],
    } for p in pos_open}

    prev = state.get('positions', {})
    new_open_ids = set(current) - set(prev)
    new_close_ids = set(prev) - set(current)

    # 初回: baseline 取って通知なし
    if state.get('last_check') is None:
        print(f'[baseline] {len(current)} positions tracked, no notify')
        state['positions'] = current
        state['last_check'] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        return

    if not new_open_ids and not new_close_ids:
        print(f'[no change] {len(current)} positions')
        state['last_check'] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        return

    # VPS log fetch (1回だけ、 全 event で共有)
    log_tail = fetch_vps_log(200)
    reason = extract_reason_from_log(log_tail) if log_tail else None

    # 各 event を文章化
    sentences = []
    has_loss = False
    has_profit = False
    for pid in new_open_ids:
        p = current[pid]
        side_ja = 'ロング' if p['side'] == 'long' else 'ショート'
        sentences.append(f"{p['asset']}を{side_ja}でエントリー、 価格 {p['entry']}")

    for pid in new_close_ids:
        p = prev[pid]
        side_ja = 'ロング' if p['side'] == 'long' else 'ショート'
        close_trade = next(
            (t for t in trades
             if t.get('positionId') == pid
             and t.get('type') == 'close'
             and float(t.get('realizedPnl', 0)) != 0),
            None
        )
        if close_trade:
            pnl = float(close_trade['realizedPnl'])
            if pnl > 0:
                sentences.append(f"{p['asset']} {side_ja} クローズ、 利確 {abs(pnl):.0f}ドル")
                has_profit = True
            else:
                sentences.append(f"{p['asset']} {side_ja} クローズ、 損切り {abs(pnl):.0f}ドル")
                has_loss = True
        else:
            sentences.append(f"{p['asset']} {side_ja} クローズ")

    # 残高情報を末尾に追加
    mb = float(acc['marginBalance'])
    upnl = float(acc['totalUnrealizedPnl'])
    sentences.append(f"現在残高 {mb:.0f}ドル、 含み {'プラス' if upnl >= 0 else 'マイナス'} {abs(upnl):.0f}ドル")

    msg = '。 '.join(sentences) + '。'

    # 緊急度に応じて style 切替
    if has_loss:
        style = 'in a serious low tone'
    elif has_profit:
        style = 'in a calm satisfied voice'
    else:
        style = 'in a calm informative voice'

    print(f'[speak] {msg}')
    try:
        speak(msg, voice='Charon', style_prefix=style)
    except Exception as e:
        print(f'[ERROR] TTS: {e}', file=sys.stderr)

    if reason:
        print(f'[log reason snippet] {reason[:300]}')

    state['positions'] = current
    state['last_check'] = datetime.now(timezone.utc).isoformat()
    save_state(state)


if __name__ == '__main__':
    main()
