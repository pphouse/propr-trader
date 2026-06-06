"""現戦略を long/short 反転したら勝てるのか検証.

各銘柄の best strategy + params で、 全 entry を反転 (long↔short) させて
SL/TP は同じまま (= 反転戦略の SL/TP 比率も同じ R:R) で OOS 評価。

もし元戦略が EV+ なら、 反転すると -2×手数料 だけ悪化して期待値マイナスのはず。
データで確認。
"""
import json
from pathlib import Path

import data_fetcher
from strategies import STRATEGY_REGISTRY
from engine import run_simulation, summarize, fmt_summary


BEST = json.loads((Path(__file__).parent / 'results_asset_specific.json').read_text())
ASSETS = list(BEST.keys())
NOTIONAL = 500


def invert_entries(entries):
    return [(i, 'short' if s == 'long' else 'long') for i, s in entries]


def main():
    print('=' * 95)
    print('INVERSE STRATEGY BACKTEST (OOS 30%)')
    print('=' * 95)

    print(f'\n{"asset":>6}  {"mode":>10}  {"summary":>1}')
    overall = {'normal': [], 'inverse': []}
    for a in ASSETS:
        best = BEST[a]
        strat_fn, _ = STRATEGY_REGISTRY[best['strategy']]
        candles = data_fetcher.fetch_candles(a, '1h', 5000)
        funding = data_fetcher.fetch_funding_history(a, 5000)
        split = int(len(candles) * 0.7)
        c_oos = candles[split:]
        f_oos = [r for r in funding if int(r['time']) >= int(c_oos[0]['t'])]

        # normal
        ents_normal = strat_fn(c_oos, f_oos, **best['params'])
        trades_normal = run_simulation(c_oos, ents_normal,
                                        best['sl_pct'], best['tp_pct'], NOTIONAL, 'none')
        s_normal = summarize(trades_normal)

        # inverse
        ents_inv = invert_entries(ents_normal)
        trades_inv = run_simulation(c_oos, ents_inv,
                                     best['sl_pct'], best['tp_pct'], NOTIONAL, 'none')
        s_inv = summarize(trades_inv)

        # SL/TP も反転 (TP=SL%, SL=TP%) で R:R 0.5
        ents_inv2 = invert_entries(ents_normal)
        trades_inv2 = run_simulation(c_oos, ents_inv2,
                                      best['tp_pct'], best['sl_pct'], NOTIONAL, 'none')
        s_inv2 = summarize(trades_inv2)

        # SL/TP 半分にして tighten (ユーザーの「幅小さめ」)
        ents_tight = strat_fn(c_oos, f_oos, **best['params'])
        trades_tight = run_simulation(c_oos, ents_tight,
                                       best['sl_pct'] * 0.5, best['tp_pct'] * 0.5,
                                       NOTIONAL, 'none')
        s_tight = summarize(trades_tight)

        overall['normal'].extend(trades_normal)
        overall['inverse'].extend(trades_inv)

        print(f'\n  {a}')
        print(f'    normal       {fmt_summary(s_normal)}')
        print(f'    inverse      {fmt_summary(s_inv)}')
        print(f'    inv + SL/TPswap {fmt_summary(s_inv2)}')
        print(f'    tight (×0.5) {fmt_summary(s_tight)}')

    print('\n' + '=' * 95)
    print('AGGREGATE (all 8 assets combined)')
    print('=' * 95)
    print(f'  normal:  {fmt_summary(summarize(overall["normal"]))}')
    print(f'  inverse: {fmt_summary(summarize(overall["inverse"]))}')


if __name__ == '__main__':
    main()
