"""出口ロジック。

各シミュレーション:
- entry_price, side, sl_pct, tp_pct を所与
- candles_after (entry bar以降の OHLC) を走査
- exit_mode (current / delayed / none) に応じて SL を動的に更新
- TP/SLどちらかにヒットした bar で exit
- 同一bar SL+TP両方タッチ → SL優先 (保守的)

戻り値:
  {'exit_price', 'exit_reason', 'bars_held', 'realized_pct', 'realized_usd'}
"""
from typing import Optional


FEE_RATE = 0.00045    # propr/Hyperliquid taker
SLIPPAGE_BPS = 5      # 5bp slippage


def apply_costs(realized_pct: float, notional: float) -> float:
    """fee + slippage を引いた realized USD."""
    gross_usd = realized_pct / 100 * notional
    # 往復 entry+exit で 2回 fee + 2回 slippage
    cost_usd = (FEE_RATE * 2 + SLIPPAGE_BPS / 10000 * 2) * notional
    return gross_usd - cost_usd


def simulate_exit(candles_after: list, entry_price: float, side: str,
                  sl_pct: float, tp_pct: float, notional: float,
                  mode: str = 'none', max_bars: int = 200) -> dict:
    """1 trade のシミュレーション."""
    # 初期 SL/TP 計算
    if side == 'long':
        sl_price = entry_price * (1 - sl_pct / 100)
        tp_price = entry_price * (1 + tp_pct / 100)
    else:
        sl_price = entry_price * (1 + sl_pct / 100)
        tp_price = entry_price * (1 - tp_pct / 100)

    breakeven_triggered = [False, False]  # [level1, level2]

    for bar_idx, c in enumerate(candles_after[:max_bars]):
        high = float(c['h'])
        low = float(c['l'])
        # 現在 unrealized (bar中間で評価) — 簡易: high or low ベース最大利益
        if side == 'long':
            unrealized_pct = (high / entry_price - 1) * 100
        else:
            unrealized_pct = (entry_price / low - 1) * 100
        unrealized_usd = unrealized_pct / 100 * notional

        # mode 別 SL 更新
        if mode == 'current':
            # +$10 → BE+$2
            if not breakeven_triggered[0] and unrealized_usd >= 10:
                new_sl_offset_pct = (2 / notional) * 100
                if side == 'long':
                    new_sl = entry_price * (1 + new_sl_offset_pct / 100)
                    sl_price = max(sl_price, new_sl)
                else:
                    new_sl = entry_price * (1 - new_sl_offset_pct / 100)
                    sl_price = min(sl_price, new_sl)
                breakeven_triggered[0] = True
            # +$25 → BE+$10
            if not breakeven_triggered[1] and unrealized_usd >= 25:
                new_sl_offset_pct = (10 / notional) * 100
                if side == 'long':
                    new_sl = entry_price * (1 + new_sl_offset_pct / 100)
                    sl_price = max(sl_price, new_sl)
                else:
                    new_sl = entry_price * (1 - new_sl_offset_pct / 100)
                    sl_price = min(sl_price, new_sl)
                breakeven_triggered[1] = True

        elif mode == 'delayed':
            # +$25 → BE+$5
            if not breakeven_triggered[0] and unrealized_usd >= 25:
                new_sl_offset_pct = (5 / notional) * 100
                if side == 'long':
                    new_sl = entry_price * (1 + new_sl_offset_pct / 100)
                    sl_price = max(sl_price, new_sl)
                else:
                    new_sl = entry_price * (1 - new_sl_offset_pct / 100)
                    sl_price = min(sl_price, new_sl)
                breakeven_triggered[0] = True
            # +$50 → BE+$20
            if not breakeven_triggered[1] and unrealized_usd >= 50:
                new_sl_offset_pct = (20 / notional) * 100
                if side == 'long':
                    new_sl = entry_price * (1 + new_sl_offset_pct / 100)
                    sl_price = max(sl_price, new_sl)
                else:
                    new_sl = entry_price * (1 - new_sl_offset_pct / 100)
                    sl_price = min(sl_price, new_sl)
                breakeven_triggered[1] = True
        # mode == 'none' は何もしない

        # SL/TP判定 (SL優先で保守的)
        if side == 'long':
            sl_hit = low <= sl_price
            tp_hit = high >= tp_price
        else:
            sl_hit = high >= sl_price
            tp_hit = low <= tp_price

        if sl_hit:
            exit_price = sl_price
            reason = 'SL'
            realized_pct = ((exit_price / entry_price - 1) if side == 'long' else (entry_price / exit_price - 1)) * 100
            return {
                'exit_price': exit_price, 'exit_reason': reason,
                'bars_held': bar_idx + 1, 'realized_pct': realized_pct,
                'realized_usd': apply_costs(realized_pct, notional)
            }
        if tp_hit:
            exit_price = tp_price
            reason = 'TP'
            realized_pct = ((exit_price / entry_price - 1) if side == 'long' else (entry_price / exit_price - 1)) * 100
            return {
                'exit_price': exit_price, 'exit_reason': reason,
                'bars_held': bar_idx + 1, 'realized_pct': realized_pct,
                'realized_usd': apply_costs(realized_pct, notional)
            }

    # max_bars に到達 → 強制クローズ (最後のcloseで)
    last_close = float(candles_after[min(max_bars - 1, len(candles_after) - 1)]['c'])
    realized_pct = ((last_close / entry_price - 1) if side == 'long' else (entry_price / last_close - 1)) * 100
    return {
        'exit_price': last_close, 'exit_reason': 'TIMEOUT',
        'bars_held': max_bars, 'realized_pct': realized_pct,
        'realized_usd': apply_costs(realized_pct, notional)
    }
