"""シミュレーション実行 + 統計集計."""
from typing import List, Callable, Dict
from statistics import mean, median, stdev

from exits import simulate_exit


def run_simulation(candles: list, entries: List[tuple],
                   sl_pct: float, tp_pct: float, notional: float,
                   exit_mode: str) -> List[dict]:
    """全 entries について exit シミュレーション実行."""
    trades = []
    for entry_idx, side in entries:
        if entry_idx + 1 >= len(candles):
            continue
        entry_price = float(candles[entry_idx]['c'])
        candles_after = candles[entry_idx + 1:]
        result = simulate_exit(candles_after, entry_price, side,
                               sl_pct, tp_pct, notional, exit_mode)
        trades.append({
            'entry_idx': entry_idx, 'side': side,
            'entry_price': entry_price, **result
        })
    return trades


def summarize(trades: List[dict]) -> Dict:
    """trade list の統計."""
    if not trades:
        return {'n': 0}
    realized = [t['realized_usd'] for t in trades]
    wins = [r for r in realized if r > 0]
    losses = [r for r in realized if r < 0]
    n = len(trades)
    n_wins = len(wins)
    n_losses = len(losses)
    win_rate = n_wins / n if n else 0
    avg_win = mean(wins) if wins else 0
    avg_loss = mean(losses) if losses else 0
    effective_rr = abs(avg_win / avg_loss) if avg_loss else None
    total_pnl = sum(realized)
    ev = total_pnl / n if n else 0
    pf = (sum(wins) / abs(sum(losses))) if losses else None
    # max drawdown (equity curve)
    eq = 0; peak = 0; max_dd = 0
    for r in realized:
        eq += r
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)
    # TP/SL 内訳
    by_reason = {}
    for t in trades:
        by_reason[t['exit_reason']] = by_reason.get(t['exit_reason'], 0) + 1
    return {
        'n': n, 'n_wins': n_wins, 'n_losses': n_losses,
        'win_rate': round(win_rate, 3),
        'avg_win': round(avg_win, 2), 'avg_loss': round(avg_loss, 2),
        'effective_rr': round(effective_rr, 2) if effective_rr else None,
        'total_pnl': round(total_pnl, 2),
        'ev_per_trade': round(ev, 2),
        'profit_factor': round(pf, 2) if pf else None,
        'max_drawdown_usd': round(max_dd, 2),
        'by_exit_reason': by_reason,
    }


def fmt_summary(s: dict) -> str:
    """human-readable 1行."""
    if s.get('n', 0) == 0:
        return 'no trades'
    return (f"n={s['n']:>4}  win={s['win_rate']*100:>5.1f}%  "
            f"avgW=${s['avg_win']:>+7.2f}  avgL=${s['avg_loss']:>+7.2f}  "
            f"R:R={str(s['effective_rr']):>5}  EV/t=${s['ev_per_trade']:>+6.2f}  "
            f"PF={str(s['profit_factor']):>5}  "
            f"net=${s['total_pnl']:>+8.2f}  maxDD=${s['max_drawdown_usd']:.0f}")
