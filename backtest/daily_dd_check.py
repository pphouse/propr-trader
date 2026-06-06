"""日次 drawdown が propr の -$150 制約に何回触るか検証.

multi-strategy 7 assets 3pos 設定で 208日 trade を生成し、
各 UTC 日の equity の peak-to-trough を計算。
-$150 を超える日が何日あるか = breach 確率。
"""
import json
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path

import data_fetcher
from strategies import STRATEGY_REGISTRY
from engine import run_simulation

BEST = json.loads((Path(__file__).parent / 'results_asset_specific.json').read_text())
ASSETS = list(BEST.keys())
DAILY_LOSS_LIMIT = 150  # propr -3%
SELF_STOP = 100         # 自主ブレーキ -$100


def collect_trades(assets, all_data, notional, max_concurrent=3, with_stopper=True):
    """全 trades 時系列ソート + 同時ポジ制限 + 連敗ストッパー."""
    all_t = []
    for a in assets:
        best = BEST[a]
        fn, _ = STRATEGY_REGISTRY[best['strategy']]
        c = all_data[a]['candles']
        f = all_data[a]['funding']
        ents = fn(c, f, **best['params'])
        ts = run_simulation(c, ents, best['sl_pct'], best['tp_pct'], notional, 'none')
        for t in ts:
            t['asset'] = a
            t['entry_t'] = int(c[t['entry_idx']]['t'])
            t['exit_t'] = t['entry_t'] + t['bars_held'] * 3600 * 1000
            all_t.append(t)
    all_t.sort(key=lambda x: x['entry_t'])
    accepted = []
    active = []
    recent_results = []
    streak_stop_until = 0
    for t in all_t:
        active = [x for x in active if x['exit_t'] > t['entry_t']]
        if len(active) >= max_concurrent:
            continue
        if with_stopper and t['entry_t'] < streak_stop_until:
            continue
        accepted.append(t)
        active.append(t)
        recent_results.append(1 if t['realized_usd'] > 0 else 0)
        if with_stopper and len(recent_results) >= 3 and sum(recent_results[-3:]) == 0:
            streak_stop_until = t['exit_t'] + 6 * 3600 * 1000
    return accepted


def apply_daily_stopper(trades, daily_limit=100):
    """1日の realized が -daily_limit を超えたらその日の以降 trade を skip."""
    if not trades:
        return [], {}
    accepted = []
    daily_realized = defaultdict(float)
    halted_days = set()
    for t in trades:
        # 日付は entry_t の UTC date
        day = datetime.fromtimestamp(t['entry_t']/1000, tz=timezone.utc).date()
        if day in halted_days:
            continue
        accepted.append(t)
        # realized は exit時点で確定するが、 計算簡易化のため entry日でカウント (close日も同じ事多い)
        exit_day = datetime.fromtimestamp(t['exit_t']/1000, tz=timezone.utc).date()
        daily_realized[exit_day] += t['realized_usd']
        if daily_realized[exit_day] <= -daily_limit:
            halted_days.add(exit_day)
    return accepted, dict(daily_realized)


def analyze_daily_dd(trades, breach_limit=DAILY_LOSS_LIMIT, label=''):
    """各日の最大intraday drawdown を計算 (peak-to-trough)."""
    # 日ごとに trade を分割
    by_day = defaultdict(list)
    for t in trades:
        day = datetime.fromtimestamp(t['exit_t']/1000, tz=timezone.utc).date()
        by_day[day].append(t)

    breach_days = []
    near_breach_days = []  # -$100 触ったが breach 未満
    realized_days = defaultdict(float)
    intraday_low = {}  # day -> max drop from day peak
    for day, ts in by_day.items():
        ts_sorted = sorted(ts, key=lambda x: x['exit_t'])
        eq = 0
        peak = 0
        max_dd = 0
        for t in ts_sorted:
            eq += t['realized_usd']
            peak = max(peak, eq, 0)  # 朝の equity = 0 とする (前日からの引き継ぎなし、 propr の 00:00 UTC reset)
            dd = peak - eq
            max_dd = max(max_dd, dd)
        realized_days[day] = eq
        intraday_low[day] = max_dd
        if max_dd >= breach_limit:
            breach_days.append((day, max_dd, eq))
        elif max_dd >= 100:
            near_breach_days.append((day, max_dd, eq))

    total_days = len(by_day)
    total_trades = sum(len(ts) for ts in by_day.values())
    days_pnl_negative = sum(1 for v in realized_days.values() if v < 0)
    days_pnl_below_minus100 = sum(1 for v in realized_days.values() if v <= -100)
    days_pnl_below_minus150 = sum(1 for v in realized_days.values() if v <= -150)

    print(f'\n[{label}]')
    print(f'  total trading days: {total_days}, total trades: {total_trades}')
    print(f'  days with negative realized: {days_pnl_negative} ({days_pnl_negative/total_days*100:.0f}%)')
    print(f'  days with realized ≤ -$100: {days_pnl_below_minus100}')
    print(f'  days with realized ≤ -$150: {days_pnl_below_minus150}  ← server breach trigger')
    print(f'  days with intraday max DD ≥ $150 (breach): {len(breach_days)}  ← actual breach risk')
    print(f'  days with intraday max DD between $100-$150: {len(near_breach_days)}')
    if breach_days:
        breach_days.sort(key=lambda x: -x[1])
        print(f'  worst 5 breach days:')
        for day, dd, eq in breach_days[:5]:
            print(f'    {day}  intraday_DD=${dd:.0f}  final={eq:+.0f}')


def main():
    print('Loading...')
    all_data = {}
    for a in ASSETS:
        all_data[a] = {
            'candles': data_fetcher.fetch_candles(a, '1h', 5000),
            'funding': data_fetcher.fetch_funding_history(a, 5000),
        }

    print('=' * 95)
    print('DAILY DRAWDOWN BREACH RISK (propr 1-Step: -$150/day = permanent breach)')
    print('=' * 95)

    # 設定別に検証
    configs = [
        ('$500 notional, 3 pos, loss-streak stopper, NO daily stopper', 500, 3, True, None),
        ('$500 notional, 3 pos, loss-streak stopper + daily -$100 stopper', 500, 3, True, 100),
        ('$300 notional, 3 pos, both stoppers', 300, 3, True, 100),
        ('$300 notional, 2 pos, both stoppers', 300, 2, True, 100),
        ('$200 notional, 2 pos, both stoppers', 200, 2, True, 100),
    ]
    for label, notional, pos, stopper, daily_stop in configs:
        trades = collect_trades(ASSETS, all_data, notional=notional,
                                 max_concurrent=pos, with_stopper=stopper)
        if daily_stop:
            trades, _ = apply_daily_stopper(trades, daily_limit=daily_stop)
        net = sum(t['realized_usd'] for t in trades)
        print(f'\n=== {label}  total trades={len(trades)} net=${net:+.0f}')
        analyze_daily_dd(trades, label=label)


if __name__ == '__main__':
    main()
