"""銘柄別パラメータ最適化.

各銘柄に対して全 strategies × params × SL/TP を再探索、
銘柄ごとに最適 OOS EV を選ぶ。 銘柄別に異なるパラメータでも構わない。
"""
import json
from pathlib import Path

import data_fetcher
from strategies import STRATEGY_REGISTRY
from engine import run_simulation, summarize

ASSETS = ['BTC', 'ETH', 'SOL', 'HYPE', 'LINK', 'ZEC', 'WLD', 'NEAR']
NOTIONAL = 1000
SLTP_GRID = [
    (1.0, 0.8), (1.5, 1.5), (2.0, 2.0),
    (1.0, 1.5), (2.0, 3.0), (1.5, 3.0),
    (2.0, 4.0), (3.0, 6.0), (1.0, 3.0),
    (2.0, 6.0), (4.0, 4.0), (0.5, 1.0),
    (1.5, 4.5),
]


def main():
    print('=' * 95)
    print('ASSET-SPECIFIC PARAMETER OPTIMIZATION (IS 70% / OOS 30%)')
    print('=' * 95)

    all_data = {}
    for a in ASSETS:
        c = data_fetcher.fetch_candles(a, '1h', 5000)
        f = data_fetcher.fetch_funding_history(a, 5000)
        split = int(len(c) * 0.7)
        all_data[a] = {
            'candles_IS': c[:split], 'candles_OOS': c[split:],
            'funding_IS': [r for r in f if int(r['time']) < int(c[split]['t'])],
            'funding_OOS': [r for r in f if int(r['time']) >= int(c[split]['t'])],
        }

    asset_best = {}
    for asset in ASSETS:
        print(f'\n## {asset}')
        candidates = []
        for sname, (sfn, params_list) in STRATEGY_REGISTRY.items():
            for p in params_list:
                for sl, tp in SLTP_GRID:
                    try:
                        # IS
                        ents_is = sfn(all_data[asset]['candles_IS'], all_data[asset]['funding_IS'], **p)
                        trades_is = run_simulation(all_data[asset]['candles_IS'], ents_is, sl, tp, NOTIONAL, 'none')
                        s_is = summarize(trades_is)
                        if s_is.get('n', 0) < 30 or s_is.get('ev_per_trade', -999) <= 0:
                            continue
                        # OOS
                        ents_oos = sfn(all_data[asset]['candles_OOS'], all_data[asset]['funding_OOS'], **p)
                        trades_oos = run_simulation(all_data[asset]['candles_OOS'], ents_oos, sl, tp, NOTIONAL, 'none')
                        s_oos = summarize(trades_oos)
                        if s_oos.get('n', 0) < 15 or s_oos.get('ev_per_trade', -999) <= 0:
                            continue
                        candidates.append({
                            'strategy': sname, 'params': p, 'sl_pct': sl, 'tp_pct': tp,
                            'IS_n': s_is['n'], 'IS_ev': s_is['ev_per_trade'], 'IS_winrate': s_is['win_rate'],
                            'OOS_n': s_oos['n'], 'OOS_ev': s_oos['ev_per_trade'], 'OOS_winrate': s_oos['win_rate'],
                            'OOS_pf': s_oos.get('profit_factor'),
                            'OOS_maxDD': s_oos.get('max_drawdown_usd'),
                        })
                    except Exception:
                        pass
        candidates.sort(key=lambda x: x['OOS_ev'], reverse=True)
        if candidates:
            best = candidates[0]
            asset_best[asset] = best
            print(f'  best: [{best["strategy"]}] {best["params"]} SL={best["sl_pct"]}/TP={best["tp_pct"]}')
            print(f'    IS: n={best["IS_n"]} ev=${best["IS_ev"]:+.2f} win={best["IS_winrate"]*100:.1f}%')
            print(f'    OOS: n={best["OOS_n"]} ev=${best["OOS_ev"]:+.2f} win={best["OOS_winrate"]*100:.1f}% PF={best["OOS_pf"]} maxDD=${best["OOS_maxDD"]}')
            # TOP 3も
            print(f'  top3:')
            for c in candidates[:3]:
                print(f'    [{c["strategy"]}] {c["params"]} SL{c["sl_pct"]}/TP{c["tp_pct"]} → OOS n={c["OOS_n"]} ev=${c["OOS_ev"]:+.2f}')
        else:
            print(f'  no IS+/OOS+ candidate found')
            asset_best[asset] = None

    # 結果保存
    out = Path(__file__).parent / 'results_asset_specific.json'
    out.write_text(json.dumps(asset_best, indent=2, default=str))
    print(f'\nsaved: {out}')
    return asset_best


if __name__ == '__main__':
    main()
