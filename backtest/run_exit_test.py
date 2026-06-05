"""出口ロジック検証.

他AI と同じ設計:
- エントリーは機械的に生成 (random + momentum)
- 出口モード 3種類 (current / delayed / none) を同一 entry集合で比較
- 実効R:R が建値移動でどう壊れるか確認

期待結果 (他AI の数値):
  current: 78% win, R:R 0.06, EV -$7.14
  delayed: 21% win, R:R 1.96, EV -$10.62
  none:    28.7% win, R:R 1.87, EV -$7.41
"""
import json
from pathlib import Path

import data_fetcher
import entries
from engine import run_simulation, summarize, fmt_summary

ASSETS = ['BTC', 'ETH', 'SOL', 'HYPE', 'LINK', 'ZEC', 'WLD', 'NEAR']
SL_PCT = 2.0     # 2%
TP_PCT = 4.0     # 4% (R:R 2.0)
NOTIONAL = 1000  # $1,000 per trade


def main():
    print('=' * 90)
    print(f'EXIT LOGIC BACKTEST')
    print(f'  assets={len(ASSETS)}  SL={SL_PCT}%  TP={TP_PCT}% (design R:R={TP_PCT/SL_PCT})  notional=${NOTIONAL}')
    print(f'  fee=4.5bp/side, slippage=5bp/side')
    print('=' * 90)
    print()

    # 全銘柄データ load
    all_data = {}
    for a in ASSETS:
        candles = data_fetcher.fetch_candles(a, '1h', 5000)
        funding = data_fetcher.fetch_funding_history(a, 5000)
        all_data[a] = {'candles': candles, 'funding': funding}

    # entry mode 2つ × exit mode 3つ で比較
    entry_modes = {
        'random_1pct': lambda c, f: entries.random_entries(c, prob=0.01, seed=42),
        'momentum_0.5pct': lambda c, f: entries.momentum_entries(c, lookback=3, threshold_pct=0.5),
    }
    exit_modes = ['current', 'delayed', 'none']

    results = {}  # {entry_name: {exit_mode: summary}}

    for ename, efn in entry_modes.items():
        print(f'\n### Entry: {ename}')
        print(f'{"exit":>10}  {"summary":>1}')
        results[ename] = {}
        # 全銘柄の trades 集約
        for xmode in exit_modes:
            all_trades = []
            for a in ASSETS:
                ents = efn(all_data[a]['candles'], all_data[a]['funding'])
                trades = run_simulation(all_data[a]['candles'], ents,
                                         SL_PCT, TP_PCT, NOTIONAL, xmode)
                all_trades.extend(trades)
            s = summarize(all_trades)
            results[ename][xmode] = s
            print(f'  {xmode:>10}  {fmt_summary(s)}')

    # JSON 保存
    out_path = Path(__file__).parent / 'results_exit_test.json'
    out_path.write_text(json.dumps(results, indent=2))
    print(f'\nsaved: {out_path}')

    return results


if __name__ == '__main__':
    main()
