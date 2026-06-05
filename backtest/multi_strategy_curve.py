"""銘柄別最適戦略 を組合せた multi-strategy 累積equity曲線."""
import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

import data_fetcher
from strategies import STRATEGY_REGISTRY
from engine import run_simulation

NOTIONAL = 500  # Phase 2 サイズ

# results_asset_specific.json から読む銘柄別 best
BEST_PER_ASSET = json.loads((Path(__file__).parent / 'results_asset_specific.json').read_text())


def collect_multi_strategy_trades(assets, all_data, with_concurrency_limit=True, max_concurrent=2):
    """各銘柄に専用の戦略を適用、 全部の trades を時系列順に."""
    all_trades = []
    for a in assets:
        best = BEST_PER_ASSET.get(a)
        if not best:
            continue
        # 戦略 lookup
        strat_fn, _ = STRATEGY_REGISTRY[best['strategy']]
        # 全期間 (IS+OOS) を通して trade
        candles = all_data[a]['candles']
        funding = all_data[a]['funding']
        ents = strat_fn(candles, funding, **best['params'])
        trades = run_simulation(candles, ents, best['sl_pct'], best['tp_pct'], NOTIONAL, 'none')
        for t in trades:
            t['asset'] = a
            t['strategy_used'] = best['strategy']
            t['entry_t'] = int(candles[t['entry_idx']]['t'])
            t['exit_t'] = t['entry_t'] + t['bars_held'] * 3600 * 1000
            all_trades.append(t)
    all_trades.sort(key=lambda x: x['entry_t'])

    # 同時ポジ制限 + 連敗ストッパー
    accepted = []
    active = []
    recent_results = []
    streak_stop_until = 0
    for t in all_trades:
        active = [a for a in active if a['exit_t'] > t['entry_t']]
        if with_concurrency_limit and len(active) >= max_concurrent:
            continue
        if t['entry_t'] < streak_stop_until:
            continue
        accepted.append(t)
        active.append(t)
        recent_results.append(1 if t['realized_usd'] > 0 else 0)
        if len(recent_results) >= 3 and sum(recent_results[-3:]) == 0:
            streak_stop_until = t['exit_t'] + 6 * 3600 * 1000
    return accepted


def build_curve(trades):
    if not trades:
        return [], []
    eq = 0
    points = [(datetime.fromtimestamp(trades[0]['entry_t']/1000, tz=timezone.utc), 0)]
    for t in trades:
        eq += t['realized_usd']
        points.append((datetime.fromtimestamp(t['exit_t']/1000, tz=timezone.utc), eq))
    return [p[0] for p in points], [p[1] for p in points]


def main():
    ASSETS = list(BEST_PER_ASSET.keys())
    print(f'Assets with best strategy: {ASSETS}')
    print('Loading data...')
    all_data = {}
    for a in ASSETS:
        c = data_fetcher.fetch_candles(a, '1h', 5000)
        f = data_fetcher.fetch_funding_history(a, 5000)
        all_data[a] = {'candles': c, 'funding': f}

    scenarios = {
        'Multi-strategy 7 assets (1 pos limit)': {'assets': ASSETS, 'max_concurrent': 1, 'color': '#1f77b4', 'lw': 2.5},
        'Multi-strategy 7 assets (2 pos)': {'assets': ASSETS, 'max_concurrent': 2, 'color': '#2ca02c', 'lw': 2.0},
        'Multi-strategy 7 assets (3 pos)': {'assets': ASSETS, 'max_concurrent': 3, 'color': '#ff7f0e', 'lw': 1.5},
        'Top-3 assets only (HYPE+ZEC+SOL, 2 pos)': {'assets': ['HYPE', 'ZEC', 'SOL'], 'max_concurrent': 2, 'color': '#d62728', 'lw': 2.0},
    }

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
    summaries = []
    for name, cfg in scenarios.items():
        trades = collect_multi_strategy_trades(cfg['assets'], all_data, max_concurrent=cfg['max_concurrent'])
        times, eqs = build_curve(trades)
        if not eqs:
            continue
        peak = eqs[0]; max_dd = 0
        for e in eqs:
            peak = max(peak, e)
            max_dd = max(max_dd, peak - e)
        ax1.plot(times, eqs,
                 label=f'{name}  n={len(trades)}, net=${eqs[-1]:+.0f}, EV/t=${eqs[-1]/len(trades):.2f}, maxDD=${max_dd:.0f}',
                 color=cfg['color'], linewidth=cfg['lw'])
        dd_curve = []
        peak_cum = eqs[0]
        for e in eqs:
            peak_cum = max(peak_cum, e)
            dd_curve.append(-(peak_cum - e))
        ax2.plot(times, dd_curve, color=cfg['color'], linewidth=cfg['lw']*0.6, alpha=0.7)
        summaries.append({
            'name': name, 'n': len(trades), 'net': round(eqs[-1], 2),
            'ev_per_trade': round(eqs[-1]/len(trades), 2) if trades else 0,
            'max_dd': round(max_dd, 2),
        })

    ax1.axhline(0, color='gray', linewidth=0.5, linestyle='--')
    ax1.set_title(f'Multi-Strategy Cumulative Equity — per-asset optimized parameters (${NOTIONAL} notional)',
                  fontsize=13, fontweight='bold')
    ax1.set_ylabel('Cumulative PnL (USDC)', fontsize=11)
    ax1.legend(loc='upper left', fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))

    ax2.axhline(0, color='gray', linewidth=0.5)
    ax2.set_title('Drawdown', fontsize=11)
    ax2.set_ylabel('DD (USDC)', fontsize=10)
    ax2.set_xlabel('Date (UTC)', fontsize=11)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    out = Path(__file__).parent / 'multi_strategy_curve.png'
    plt.savefig(out, dpi=130, bbox_inches='tight')
    print(f'saved: {out}')

    print('\n=== Summary ===')
    for s in summaries:
        print(f'  {s["name"]:55} n={s["n"]:>4}  net=${s["net"]:>+7.2f}  EV/t=${s["ev_per_trade"]:>+5.2f}  maxDD=${s["max_dd"]:>6.0f}')


if __name__ == '__main__':
    main()
