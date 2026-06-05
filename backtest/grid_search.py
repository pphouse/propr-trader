"""戦略パラメータ全探索 + IS/OOS 分割検証.

設計:
1. データを 70% In-Sample / 30% OOS に分割 (時系列順)
2. 全戦略 × 全パラメータ × 全銘柄 を IS で評価
3. IS で EV プラスかつ trade数 >= 50 の戦略のみ OOS 評価
4. OOS でも EV プラスのものを「採用候補」 として出力
5. R:R も 複数 (0.8/1.0/1.5/2.0/3.0) 試す
"""
import json
import time
from pathlib import Path
from itertools import product

import data_fetcher
from strategies import STRATEGY_REGISTRY
from engine import run_simulation, summarize

ASSETS = ['BTC', 'ETH', 'SOL', 'HYPE', 'LINK', 'ZEC', 'WLD', 'NEAR']
NOTIONAL = 1000

# SL/TP 組合せ (R:R 0.5 〜 3.0)
SLTP_GRID = [
    (1.0, 0.8),   # R:R 0.8 (平均回帰向き)
    (1.5, 1.5),   # R:R 1.0
    (2.0, 2.0),
    (1.0, 1.5),   # R:R 1.5
    (2.0, 3.0),
    (1.5, 3.0),   # R:R 2.0
    (2.0, 4.0),
    (3.0, 6.0),
    (1.0, 3.0),   # R:R 3.0
    (2.0, 6.0),
]


def split_data(candles, split_ratio=0.7):
    """時系列順に IS / OOS 分割."""
    n = len(candles)
    split_idx = int(n * split_ratio)
    return candles[:split_idx], candles[split_idx:]


def split_funding(funding, candles_is, candles_oos):
    """funding records も IS/OOS 分割 (candle bar 時間で)."""
    if not candles_is or not candles_oos:
        return funding, []
    split_t = int(candles_oos[0]['t'])
    is_f = [r for r in funding if int(r['time']) < split_t]
    oos_f = [r for r in funding if int(r['time']) >= split_t]
    return is_f, oos_f


def evaluate_strategy(strat_fn, params, sl_pct, tp_pct, all_data, period='IS'):
    """全銘柄合算で 1パラメータ評価."""
    all_trades = []
    for a in ASSETS:
        ents = strat_fn(all_data[a][f'candles_{period}'],
                        all_data[a][f'funding_{period}'], **params)
        trades = run_simulation(all_data[a][f'candles_{period}'], ents,
                                 sl_pct, tp_pct, NOTIONAL, 'none')  # 出口は none固定
        all_trades.extend(trades)
    s = summarize(all_trades)
    return s


def main():
    print('=' * 100)
    print('STRATEGY GRID SEARCH (IS/OOS split, exit=none)')
    print('=' * 100)

    # data load + IS/OOS分割
    all_data = {}
    for a in ASSETS:
        candles = data_fetcher.fetch_candles(a, '1h', 5000)
        funding = data_fetcher.fetch_funding_history(a, 5000)
        c_is, c_oos = split_data(candles, 0.7)
        f_is, f_oos = split_funding(funding, c_is, c_oos)
        all_data[a] = {
            'candles_IS': c_is, 'candles_OOS': c_oos,
            'funding_IS': f_is, 'funding_OOS': f_oos,
        }

    total_configs = sum(len(p) for _, p in STRATEGY_REGISTRY.values()) * len(SLTP_GRID)
    print(f'Total configs to evaluate: {total_configs}  ({len(STRATEGY_REGISTRY)} strategies × params × {len(SLTP_GRID)} SL/TP)')
    print(f'Train period: {len(all_data["BTC"]["candles_IS"])} bars (~{len(all_data["BTC"]["candles_IS"])/24:.0f}d)')
    print(f'OOS period:   {len(all_data["BTC"]["candles_OOS"])} bars (~{len(all_data["BTC"]["candles_OOS"])/24:.0f}d)')
    print()

    # Phase 1: IS 評価
    print('--- Phase 1: In-Sample 評価 ---')
    is_results = []
    t0 = time.time()
    cfg_idx = 0
    for strat_name, (strat_fn, param_list) in STRATEGY_REGISTRY.items():
        for params in param_list:
            for sl_pct, tp_pct in SLTP_GRID:
                cfg_idx += 1
                try:
                    s = evaluate_strategy(strat_fn, params, sl_pct, tp_pct, all_data, 'IS')
                    if s.get('n', 0) >= 50:  # 統計的に意味あるサンプル
                        s_entry = {
                            'strategy': strat_name,
                            'params': params,
                            'sl_pct': sl_pct,
                            'tp_pct': tp_pct,
                            'rr_design': round(tp_pct / sl_pct, 2),
                            'IS': s,
                        }
                        is_results.append(s_entry)
                except Exception as e:
                    pass
                if cfg_idx % 50 == 0:
                    elapsed = time.time() - t0
                    eta = elapsed / cfg_idx * (total_configs - cfg_idx)
                    print(f'  {cfg_idx}/{total_configs} ({elapsed:.1f}s elapsed, ~{eta:.0f}s ETA)')

    print(f'\nIS configs with >=50 trades: {len(is_results)}')

    # IS 期待値プラスのみ OOS 評価
    is_positive = [r for r in is_results if r['IS']['ev_per_trade'] > 0]
    print(f'IS EV+ configs: {len(is_positive)}')

    # Phase 2: OOS 評価 (IS+ のもののみ)
    print('\n--- Phase 2: OOS 評価 (IS+ のみ) ---')
    oos_results = []
    for r in is_positive:
        strat_fn = STRATEGY_REGISTRY[r['strategy']][0]
        try:
            s_oos = evaluate_strategy(strat_fn, r['params'], r['sl_pct'], r['tp_pct'], all_data, 'OOS')
            r['OOS'] = s_oos
            oos_results.append(r)
        except Exception as e:
            pass

    # IS+ かつ OOS+ のみ採用候補
    accepted = [r for r in oos_results
                if r.get('OOS', {}).get('ev_per_trade', -999) > 0
                and r.get('OOS', {}).get('n', 0) >= 20]

    # 評価指標で並べる: OOS EV/trade
    accepted.sort(key=lambda r: r['OOS']['ev_per_trade'], reverse=True)

    # 結果出力
    print()
    print('=' * 100)
    print(f'採用候補 (IS+ AND OOS+, OOS n>=20): {len(accepted)}')
    print('=' * 100)
    for r in accepted[:30]:
        print(f'\n[{r["strategy"]}] {r["params"]}  SL={r["sl_pct"]}%/TP={r["tp_pct"]}% (R:R {r["rr_design"]})')
        print(f'  IS:  n={r["IS"]["n"]:>4}  win={r["IS"]["win_rate"]*100:>5.1f}%  R:R={r["IS"]["effective_rr"]}  EV/t=${r["IS"]["ev_per_trade"]:+.2f}  PF={r["IS"]["profit_factor"]}')
        print(f'  OOS: n={r["OOS"]["n"]:>4}  win={r["OOS"]["win_rate"]*100:>5.1f}%  R:R={r["OOS"]["effective_rr"]}  EV/t=${r["OOS"]["ev_per_trade"]:+.2f}  PF={r["OOS"]["profit_factor"]}')

    # 全結果保存
    out_path = Path(__file__).parent / 'results_grid_search.json'
    out_path.write_text(json.dumps({
        'total_configs_tested': cfg_idx,
        'is_with_min_trades': len(is_results),
        'is_positive': len(is_positive),
        'is_and_oos_positive': len(accepted),
        'top_accepted': accepted[:50],
        'all_oos_evaluated': oos_results[:100],  # OOS評価したやつ全部 (採用基準満たさなくても)
    }, indent=2, default=str))
    print(f'\nsaved: {out_path}')

    return accepted


if __name__ == '__main__':
    main()
