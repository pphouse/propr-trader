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
from datetime import datetime, timezone, timedelta

# 古すぎる trade (これより昔) は state に記録するが音声化しない
RECENT_NOTIFY_MINUTES = 10
# 1回の run で最大何件まで音声化するか
MAX_NOTIFY_PER_RUN = 3

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


def _latest_finished_cycle(log_text):
    if not log_text or 'autopilot run finished' not in log_text:
        return None
    up_to = log_text.rsplit('autopilot run finished', 1)[0]
    parts = up_to.split('autopilot run starting')
    return parts[-1] if len(parts) >= 2 else None


def extract_signal_reason(log_text, asset):
    """シグナル section から該当 asset の signal の根拠を抜いて自然な日本語に."""
    cycle = _latest_finished_cycle(log_text)
    if not cycle:
        return None
    # 各 asset 行: '- **ZEC** [strategy]: signal=**short** (funding=-0.0069% ≤ -0.001, mom=-7.648% ≤ -0.5%)'
    pattern = rf'[-*•]\s*\*?\*?{re.escape(asset)}\*?\*?\s*\[([\w_]+)\][^\n]*?signal=\*?\*?(\w+)\*?\*?\s*\(([^)]+)\)'
    m = re.search(pattern, cycle)
    if not m:
        return None
    strategy, sig, raw = m.group(1), m.group(2), m.group(3)
    # signal=None の場合は entry してないので根拠出さない (close 側で誤って取らない保険)
    if sig.lower() in ('none', ''):
        return None
    s = raw
    # 比較演算子と直後の閾値 (例: ' ≤ -0.001') を削る
    s = re.sub(r'\s*[≤≥<>]=?\s*-?\d+\.?\d*x?%?', '', s)
    s = re.sub(r'\s*✓\s*', '', s)
    # 純粋な 「変数=値」 ペアだけ残す: 自然文 (e.g. 'not extreme or oversold') を除去
    # → カンマ区切りで chunk化、 'name=value' or 'name value' 形式以外は捨てる
    chunks = [c.strip() for c in re.split(r',|、', s) if c.strip()]
    keep = []
    for c in chunks:
        # 変数名らしいキーワード (英数+_) が ある or 数値%が ある chunk のみ
        if re.search(r'\b(fund(?:ing)?|mom|vol_mult|RSI|EMA|cross_diff)\b', c, re.I) and re.search(r'-?\d', c):
            keep.append(c)
    if not keep:
        return None
    s = '、 '.join(keep)
    # 変数名を日本語化
    s = re.sub(r'\bfund(?:ing)?\b', 'ファンディング', s, flags=re.I)
    s = re.sub(r'\bmom\b', 'モメンタム', s, flags=re.I)
    s = re.sub(r'\bvol_mult\b', '出来高倍率', s, flags=re.I)
    s = re.sub(r'\bcross_diff\b', 'クロス差', s, flags=re.I)
    s = re.sub(r'\bEMA\s*\d*\b', 'EMA', s, flags=re.I)
    s = re.sub(r'\s*=\s*', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip(' 、。')
    return s[:140]


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

    # 古い trade は silent seen化 (cron 復帰時の spam 防止)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=RECENT_NOTIFY_MINUTES)
    recent = []
    too_old = []
    for t in new_trades:
        try:
            t_time = datetime.fromisoformat(t['executedAt'].replace('Z', '+00:00'))
            if t_time >= cutoff:
                recent.append(t)
            else:
                too_old.append(t)
        except Exception:
            too_old.append(t)

    if too_old:
        print(f'[silent] {len(too_old)} old trades silently marked seen')
        seen.update(t['tradeId'] for t in too_old)
    if not recent:
        state['seen_trade_ids'] = list(seen)[-200:]
        state['last_check'] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        return

    # 多すぎる時は最新 N件だけ音声化、 残りは silent seen化
    if len(recent) > MAX_NOTIFY_PER_RUN:
        seen.update(t['tradeId'] for t in recent[:-MAX_NOTIFY_PER_RUN])
        recent = recent[-MAX_NOTIFY_PER_RUN:]
        print(f'[capped] notifying only latest {MAX_NOTIFY_PER_RUN}')

    new_trades = recent
    print(f'[detected] {len(new_trades)} recent trades to notify')

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

    # VPS log fetch → entry/flip の根拠のみ抽出 (close は TP/SL hit なので不要)
    needs_reason_assets = {t['asset'] for t in deduped
                           if t.get('type') in ('open', 'flip')}
    reasons_by_asset = {}
    if needs_reason_assets:
        log_text = fetch_vps_log(400)
        if log_text:
            for a in needs_reason_assets:
                r = extract_signal_reason(log_text, a)
                if r:
                    reasons_by_asset[a] = r

    # 残高情報
    mb = float(acc['marginBalance'])
    upnl = float(acc['totalUnrealizedPnl'])

    body_parts = sentences[:]
    for asset, reason in reasons_by_asset.items():
        body_parts.append(f"{asset}の根拠は{reason}")
    body_parts.append(f"残高{mb:.0f}ドル、 含み{'プラス' if upnl >= 0 else 'マイナス'}{abs(upnl):.0f}ドル")
    msg = '。 '.join(body_parts) + '。'

    # 緊急度 → トーン
    has_loss = any(float(t.get('realizedPnl', 0)) < 0 for t in deduped)
    has_profit = any(float(t.get('realizedPnl', 0)) > 0 for t in deduped)
    style = ('in a serious tone' if has_loss
             else 'in a calm satisfied tone' if has_profit
             else 'in a clear informative tone')

    print(f'[speak] {msg}')
    try:
        speak(msg, voice='Kore', style_prefix=style)
    except Exception as e:
        print(f'[ERROR] TTS: {e}', file=sys.stderr)

    # state 更新 (max 200 件まで保持)
    seen.update(t['tradeId'] for t in new_trades)
    state['seen_trade_ids'] = list(seen)[-200:]
    state['last_check'] = datetime.now(timezone.utc).isoformat()
    save_state(state)


if __name__ == '__main__':
    main()
