"""propr 新規trade 検知 + Charon voice 通知.

Mac の cron から **1分毎** に呼ばれる想定。
- state は ~/.propr-notifier-state.json に last_seen_trade_id を保持
- 新規 trade が出たら VPS log fetch → 該当 cycle の reasoning を抜く
- Gemini TTS Charon で 「アクション + 理由」 を読み上げ
"""
import os
import re
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone

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
    return {'seen_trade_ids': [], 'last_check': None}


def save_state(s):
    STATE_FILE.write_text(json.dumps(s, indent=2, default=str))


def fetch_vps_log(lines=400):
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


def extract_judgement_section(log_text):
    """最新の **完成済み** cycle の '### 🎯 判断' section と '### 💼 実行結果' を抜く.

    各 cycle は 'autopilot run starting' 〜 'autopilot run finished' で囲まれる.
    fetch時に最新 cycle が in-progress だと判断 section がまだ無いので、
    finished 済みの最後の cycle を取る.
    """
    if not log_text or 'autopilot run finished' not in log_text:
        return None
    # 最後の 'finished' までを切り出し → その中の最後の 'starting' 以降 = 最終完了 cycle
    up_to_finished = log_text.rsplit('autopilot run finished', 1)[0]
    parts = up_to_finished.split('autopilot run starting')
    if len(parts) < 2:
        return None
    cycle = parts[-1]
    # '判断' section
    m_decide = re.search(r'### (?:🎯\s*)?判断[^\n]*\n(.*?)(?=\n### |\Z)',
                          cycle, re.DOTALL)
    decide = m_decide.group(1).strip() if m_decide else None
    return decide


def shorten_reason(reason, max_chars=180):
    """log の判断 section を 1-2 文に縮める."""
    if not reason:
        return None
    # bullet (- や *) を区切りに、 最初の 2 行を取る
    lines = [l.strip(' -*•').strip() for l in reason.split('\n') if l.strip()]
    # markdown記号 (** や `) を除去
    cleaned = []
    for l in lines:
        l = re.sub(r'`[^`]*`', '', l)
        l = re.sub(r'\*\*', '', l)
        l = re.sub(r'[#✅✨🔴⚠️🎯💼📊🧠⏭ ]+', ' ', l)
        l = l.strip()
        if l:
            cleaned.append(l)
    joined = '。 '.join(cleaned[:2])
    if len(joined) > max_chars:
        joined = joined[:max_chars] + '...'
    return joined


def trade_to_sentence(t):
    """1つの trade を日本語の1文にする."""
    asset = t['asset']
    side_ja = 'ロング' if t['positionSide'] == 'long' else 'ショート'
    ttype = t.get('type', '')
    pnl = float(t.get('realizedPnl', 0))
    price = t.get('price', '?')

    if ttype == 'open':
        return f"{asset}を{side_ja}でエントリー、 価格 {price}"
    if ttype == 'close':
        if pnl > 0:
            return f"{asset} {side_ja} クローズ、 利確 {abs(pnl):.0f}ドル"
        elif pnl < 0:
            return f"{asset} {side_ja} クローズ、 損切り {abs(pnl):.0f}ドル"
        return f"{asset} {side_ja} クローズ"
    if ttype == 'flip':
        if pnl > 0:
            return f"{asset} {side_ja}にフリップ、 利確 {abs(pnl):.0f}ドル"
        return f"{asset} {side_ja}にフリップ、 損失 {abs(pnl):.0f}ドル"
    return f"{asset} {side_ja} {ttype}"


def main():
    state = load_state()
    seen = set(state.get('seen_trade_ids', []))

    try:
        trades = api.get(f'/accounts/{api.ACCOUNT_ID}/trades', limit=20)['data']
        acc = api.account()
    except Exception as e:
        print(f'[ERROR] propr API: {e}', file=sys.stderr)
        return

    trades = sorted(trades, key=lambda t: t.get('executedAt', ''))

    # 初回: 全 trades を seen 扱いにして 通知なし (履歴 spam 回避)
    if state.get('last_check') is None:
        seen = {t['tradeId'] for t in trades}
        state['seen_trade_ids'] = list(seen)
        state['last_check'] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        print(f'[baseline] {len(seen)} historical trades marked seen, no notify')
        return

    new_trades = [t for t in trades if t['tradeId'] not in seen]
    if not new_trades:
        print(f'[no change] no new trades')
        state['last_check'] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        return

    print(f'[detected] {len(new_trades)} new trades')

    # 同 positionId / 同 type を 1 sentence にまとめる (大型注文の分割約定対策)
    bucket = {}
    for t in new_trades:
        key = (t.get('positionId'), t.get('type'), t.get('asset'), t.get('positionSide'))
        if key not in bucket:
            bucket[key] = {**t, '_pnl_sum': 0, '_count': 0}
        bucket[key]['_pnl_sum'] += float(t.get('realizedPnl', 0))
        bucket[key]['_count'] += 1
    deduped = []
    for k, v in bucket.items():
        v['realizedPnl'] = v['_pnl_sum']
        deduped.append(v)

    sentences = [trade_to_sentence(t) for t in deduped]

    # VPS log fetch 1回 → 判断 reason 抜く
    log_text = fetch_vps_log(400)
    judgement = extract_judgement_section(log_text)
    short_reason = shorten_reason(judgement) if judgement else None

    # 残高情報
    mb = float(acc['marginBalance'])
    upnl = float(acc['totalUnrealizedPnl'])

    body_parts = sentences[:]
    if short_reason:
        body_parts.append(f"判断: {short_reason}")
    body_parts.append(f"残高 {mb:.0f}ドル、 含み {'プラス' if upnl >= 0 else 'マイナス'} {abs(upnl):.0f}ドル")
    msg = '。 '.join(body_parts) + '。'

    # 緊急度 → トーン
    has_loss = any(float(t.get('realizedPnl', 0)) < 0 for t in deduped)
    has_profit = any(float(t.get('realizedPnl', 0)) > 0 for t in deduped)
    style = ('in a serious low tone' if has_loss
             else 'in a calm satisfied voice' if has_profit
             else 'in a calm informative voice')

    print(f'[speak] {msg}')
    try:
        speak(msg, voice='Charon', style_prefix=style)
    except Exception as e:
        print(f'[ERROR] TTS: {e}', file=sys.stderr)

    # state 更新 (max 200 件まで保持)
    seen.update(t['tradeId'] for t in new_trades)
    state['seen_trade_ids'] = list(seen)[-200:]
    state['last_check'] = datetime.now(timezone.utc).isoformat()
    save_state(state)


if __name__ == '__main__':
    main()
