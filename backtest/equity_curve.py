"""Phase 2 戦略 (volume_spike_momentum) の累積equity曲線描画.

複数シナリオを同じ図で比較:
1. Phase 2実装通り: BTC+HYPE のみ、 ノーション$500、 3連敗ストッパー
2. backtest 5 EV+銘柄全部: BTC+HYPE+ZEC+WLD+SOL、 ノーション$500、 ストッパーなし
3. 全8銘柄: ストッパーなし (Phase 2前 = naiveバージョン)

時系列順に trade を並べて 累積PnLを描く。
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

import data_fetcher
from strategies import strat_volume_spike_momentum
from engine import run_simulation

PARAMS = {'vol_lookback': 20, 'vol_mult': 2.0, 'mom_lookback': 5, 'mom_threshold': 0.5}
SL, TP, NOTIONAL = 3.0, 6.0, 500


def collect_trades(assets, all_data, with_loss_streak_stopper=True, max_concurrent=1):
    """全銘柄 × 全 OOS期間 で trade を集めて時系列にソート."""
    all_trades = []
    for a in assets:
        candles = all_data[a]['candles']
        funding = all_data[a].get('funding', [])
        ents = strat_volume_spike_momentum(candles, funding, **PARAMS)
        trades = run_simulation(candles, ents, SL, TP, NOTIONAL, 'none')
        for t in trades:
            t['asset'] = a
            t['entry_t'] = int(candles[t['entry_idx']]['t'])
            # exit time: entry + bars_held * 1h
            t['exit_t'] = t['entry_t'] + t['bars_held'] * 3600 * 1000
            all_trades.append(t)
    # 時系列順
    all_trades.sort(key=lambda x: x['entry_t'])

    # 同時ポジ制限 + 連敗ストッパー適用
    if max_concurrent or with_loss_streak_stopper:
        accepted = []
        active = []  # (exit_t, ...)
        recent_results = []  # 直近N件の win/loss
        streak_stop_until = 0  # 連敗ストッパー解除時刻 (ms)
        for t in all_trades:
            # 終了した active を取り除く
            active = [a for a in active if a['exit_t'] > t['entry_t']]
            # 連敗ストッパー判定
            if with_loss_streak_stopper and t['entry_t'] < streak_stop_until:
                continue
            # 同時ポジ判定
            if max_concurrent and len(active) >= max_concurrent:
                continue
            accepted.append(t)
            active.append(t)
            # 連敗カウント更新
            recent_results.append(1 if t['realized_usd'] > 0 else 0)
            if len(recent_results) >= 3 and sum(recent_results[-3:]) == 0:
                streak_stop_until = t['exit_t'] + 6 * 3600 * 1000  # 6h stop
        return accepted
    return all_trades


def build_curve(trades):
    """累積equity曲線データ生成."""
    if not trades:
        return [], []
    eq = 0
    points = [(datetime.fromtimestamp(trades[0]['entry_t']/1000, tz=timezone.utc), 0)]
    for t in trades:
        eq += t['realized_usd']
        points.append((datetime.fromtimestamp(t['exit_t']/1000, tz=timezone.utc), eq))
    times = [p[0] for p in points]
    eqs = [p[1] for p in points]
    return times, eqs


def main():
    ASSETS_ALL = ['BTC', 'ETH', 'SOL', 'HYPE', 'LINK', 'ZEC', 'WLD', 'NEAR']
    print('Loading data...')
    all_data = {}
    for a in ASSETS_ALL:
        candles = data_fetcher.fetch_candles(a, '1h', 5000)
        funding = data_fetcher.fetch_funding_history(a, 5000)
        # 全期間 (IS+OOS) を使う = 208日
        all_data[a] = {'candles': candles, 'funding': funding}

    print('Running scenarios...')
    scenarios = {
        'Phase 2 spec (BTC+HYPE, $500, 1pos, loss-streak stopper)': {
            'assets': ['BTC', 'HYPE'],
            'with_loss_streak_stopper': True,
            'max_concurrent': 1,
            'color': '#1f77b4',
            'lw': 2.5,
        },
        '5 assets + stopper (BTC+HYPE+ZEC+WLD+SOL)': {
            'assets': ['BTC', 'HYPE', 'ZEC', 'WLD', 'SOL'],
            'with_loss_streak_stopper': True,
            'max_concurrent': 1,
            'color': '#2ca02c',
            'lw': 1.8,
        },
        '5 assets, no stopper, no concurrency limit': {
            'assets': ['BTC', 'HYPE', 'ZEC', 'WLD', 'SOL'],
            'with_loss_streak_stopper': False,
            'max_concurrent': None,
            'color': '#ff7f0e',
            'lw': 1.5,
        },
        'All 8 assets, naive (no filtering, no stopper)': {
            'assets': ASSETS_ALL,
            'with_loss_streak_stopper': False,
            'max_concurrent': None,
            'color': '#d62728',
            'lw': 1.2,
        },
    }

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True,
                                     gridspec_kw={'height_ratios': [3, 1]})

    summaries = []
    for name, cfg in scenarios.items():
        trades = collect_trades(cfg['assets'], all_data,
                                with_loss_streak_stopper=cfg['with_loss_streak_stopper'],
                                max_concurrent=cfg['max_concurrent'])
        times, eqs = build_curve(trades)
        if not eqs:
            continue
        # max drawdown
        peak = eqs[0]; max_dd = 0
        for e in eqs:
            peak = max(peak, e)
            max_dd = max(max_dd, peak - e)
        ax1.plot(times, eqs, label=f'{name}  (n={len(trades)}, net=${eqs[-1]:+.0f}, maxDD=${max_dd:.0f})',
                 color=cfg['color'], linewidth=cfg['lw'])
        # ドローダウンチャート (under)
        dd_curve = []
        peak_cum = eqs[0]
        for e in eqs:
            peak_cum = max(peak_cum, e)
            dd_curve.append(-(peak_cum - e))
        ax2.plot(times, dd_curve, color=cfg['color'], linewidth=cfg['lw']*0.6, alpha=0.7)
        summaries.append({
            'name': name, 'n': len(trades), 'net': round(eqs[-1], 2),
            'max_dd': round(max_dd, 2),
            'ev_per_trade': round(eqs[-1] / len(trades), 2) if len(trades) else 0,
        })

    ax1.axhline(0, color='gray', linewidth=0.5, linestyle='--')
    ax1.set_title('Cumulative Equity Curve — volume_spike_momentum (vol≥2x median, |mom|≥0.5%, SL3%/TP6%, $500 notional)',
                  fontsize=13, fontweight='bold')
    ax1.set_ylabel('Cumulative PnL (USDC)', fontsize=11)
    ax1.legend(loc='upper left', fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))

    ax2.axhline(0, color='gray', linewidth=0.5)
    ax2.set_title('Drawdown (cumulative peak − current)', fontsize=11)
    ax2.set_ylabel('DD (USDC)', fontsize=10)
    ax2.set_xlabel('Date (UTC)', fontsize=11)
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))

    plt.tight_layout()
    out_path = Path(__file__).parent / 'equity_curve.png'
    plt.savefig(out_path, dpi=130, bbox_inches='tight')
    print(f'saved: {out_path}')

    # サマリ表示
    print('\n=== Summary ===')
    for s in summaries:
        print(f'  {s["name"]:55} n={s["n"]:>4}  net=${s["net"]:>+7.2f}  EV/t=${s["ev_per_trade"]:>+5.2f}  maxDD=${s["max_dd"]:>6.0f}')


if __name__ == '__main__':
    main()
