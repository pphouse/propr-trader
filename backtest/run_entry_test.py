"""エントリー検証.

出口は none mode (実効R:R 1.79) で固定し、 エントリーロジックを比較:
- random: ベースライン (期待値=0付近、 手数料分マイナス)
- momentum: C軸単独 (順張り)
- funding: B軸単独 (逆張り)
- mom+fund: C+B 2軸一致
- three_axis: B+C+D 3軸一致

3軸一致で random より EV が有意に上がるか = bot本番のエッジ検証。
"""
import json
from pathlib import Path

import data_fetcher
import entries
from engine import run_simulation, summarize, fmt_summary

ASSETS = ['BTC', 'ETH', 'SOL', 'HYPE', 'LINK', 'ZEC', 'WLD', 'NEAR']
SL_PCT = 2.0
TP_PCT = 4.0
NOTIONAL = 1000
EXIT_MODE = 'none'


def main():
    print('=' * 95)
    print(f'ENTRY LOGIC BACKTEST  (exit=none, SL={SL_PCT}%, TP={TP_PCT}%, R:R 2.0, ${NOTIONAL})')
    print('=' * 95)

    all_data = {}
    for a in ASSETS:
        candles = data_fetcher.fetch_candles(a, '1h', 5000)
        funding = data_fetcher.fetch_funding_history(a, 5000)
        all_data[a] = {'candles': candles, 'funding': funding}

    entry_modes = {
        'random_1pct':        lambda c, f: entries.random_entries(c, prob=0.01, seed=42),
        'momentum (C only)':  lambda c, f: entries.momentum_entries(c, lookback=3, threshold_pct=0.5),
        'funding (B only)':   lambda c, f: entries.funding_extreme_entries(c, f, threshold_pct_per_hr=0.005),
        'C+B (2軸一致)':      lambda c, f: entries.momentum_and_funding(c, f, mom_lookback=3, mom_threshold=0.5, fund_threshold=0.005),
        '3軸一致 (B+C+D)':    lambda c, f: entries.three_axis_entries(c, f, mom_lookback=3, mom_threshold=0.5, fund_threshold=0.005, price_1h_threshold=1.0),
    }

    results = {}
    print(f'\n{"mode":>22}  {"summary":>1}')
    print('-' * 95)
    for ename, efn in entry_modes.items():
        all_trades = []
        per_asset_stats = {}
        for a in ASSETS:
            ents = efn(all_data[a]['candles'], all_data[a]['funding'])
            trades = run_simulation(all_data[a]['candles'], ents,
                                     SL_PCT, TP_PCT, NOTIONAL, EXIT_MODE)
            all_trades.extend(trades)
            per_asset_stats[a] = summarize(trades)
        s = summarize(all_trades)
        s['per_asset'] = per_asset_stats
        results[ename] = s
        print(f'  {ename:>22}  {fmt_summary(s)}')

    # JSON 保存
    out_path = Path(__file__).parent / 'results_entry_test.json'
    out_path.write_text(json.dumps(results, indent=2))
    print(f'\nsaved: {out_path}')
    return results


if __name__ == '__main__':
    main()
