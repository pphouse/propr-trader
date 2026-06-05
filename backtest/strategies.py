"""戦略テンプレート群.

各戦略は (candles, funding, **params) → list of (entry_idx, side) を返す.
"""
import math
from typing import List, Tuple


# ============================================================
# トレンドフォロー系
# ============================================================

def strat_momentum(candles, funding, lookback=3, threshold_pct=0.5):
    """C軸単独: lookback本前との比較で threshold以上動いた方向に順張り."""
    out = []
    for i in range(lookback + 20, len(candles) - 200):
        cur = float(candles[i]['c'])
        prev = float(candles[i - lookback]['c'])
        pct = (cur / prev - 1) * 100
        if pct >= threshold_pct:
            out.append((i, 'long'))
        elif pct <= -threshold_pct:
            out.append((i, 'short'))
    return out


def strat_ema_cross(candles, funding, fast=5, slow=20):
    """EMAクロス: fastEMA > slowEMA で long、 逆で short. クロス転換時のみ entry."""
    closes = [float(c['c']) for c in candles]
    if len(closes) < slow + 20:
        return []
    # 単純 EMA
    def ema(vals, n):
        k = 2 / (n + 1)
        e = vals[0]
        out = [e]
        for v in vals[1:]:
            e = v * k + e * (1 - k)
            out.append(e)
        return out
    ef = ema(closes, fast)
    es = ema(closes, slow)
    out = []
    last_sig = 0
    for i in range(slow + 20, len(candles) - 200):
        diff = ef[i] - es[i]
        sig = 1 if diff > 0 else -1
        if sig != last_sig and last_sig != 0:
            out.append((i, 'long' if sig == 1 else 'short'))
        last_sig = sig
    return out


def strat_breakout(candles, funding, lookback=20):
    """ブレイクアウト: 直近 lookback本の高値/安値 を上抜け/下抜けで entry."""
    out = []
    for i in range(lookback + 20, len(candles) - 200):
        highs = [float(candles[j]['h']) for j in range(i - lookback, i)]
        lows = [float(candles[j]['l']) for j in range(i - lookback, i)]
        cur = float(candles[i]['c'])
        if cur > max(highs):
            out.append((i, 'long'))
        elif cur < min(lows):
            out.append((i, 'short'))
    return out


# ============================================================
# 平均回帰系
# ============================================================

def strat_bollinger_revert(candles, funding, period=20, k=2.0):
    """ボリンジャー逆張り: ±k×σ を超えたら反対方向に entry."""
    closes = [float(c['c']) for c in candles]
    out = []
    for i in range(period + 20, len(candles) - 200):
        window = closes[i - period:i]
        mean = sum(window) / period
        var = sum((x - mean) ** 2 for x in window) / period
        sd = math.sqrt(var)
        upper = mean + k * sd
        lower = mean - k * sd
        cur = closes[i]
        if cur > upper:
            out.append((i, 'short'))  # 上限突破 → 平均回帰short
        elif cur < lower:
            out.append((i, 'long'))   # 下限突破 → 平均回帰long
    return out


def strat_rsi_extreme(candles, funding, period=14, ob=70, os=30):
    """RSI極値: RSI > ob (overbought) で short、 RSI < os (oversold) で long."""
    closes = [float(c['c']) for c in candles]
    if len(closes) < period + 20:
        return []
    # Wilder's RSI 簡易版
    out = []
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    rsis = []
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
        rs = avg_g / avg_l if avg_l > 0 else 100
        rsi = 100 - 100 / (1 + rs)
        rsis.append((i + 1, rsi))
    for i, rsi in rsis:
        if i < 20 or i >= len(candles) - 200:
            continue
        if rsi >= ob:
            out.append((i, 'short'))
        elif rsi <= os:
            out.append((i, 'long'))
    return out


# ============================================================
# Funding 系
# ============================================================

def strat_funding_extreme(candles, funding, threshold_pct=0.005):
    """B軸: funding 極端値 → 逆張り."""
    fund_by_hour = {int(rec['time']) // 3600000: float(rec['fundingRate']) * 100 for rec in funding}
    out = []
    for i in range(20, len(candles) - 200):
        bar_hour = int(candles[i]['t']) // 3600000
        rate = fund_by_hour.get(bar_hour)
        if rate is None:
            continue
        if rate >= threshold_pct:
            out.append((i, 'short'))
        elif rate <= -threshold_pct:
            out.append((i, 'long'))
    return out


def strat_funding_momentum(candles, funding, lookback=3, mom_threshold=0.5, fund_threshold=0.005):
    """C+B 同方向のみ."""
    fund_by_hour = {int(rec['time']) // 3600000: float(rec['fundingRate']) * 100 for rec in funding}
    out = []
    for i in range(lookback + 20, len(candles) - 200):
        cur = float(candles[i]['c'])
        prev = float(candles[i - lookback]['c'])
        mom_pct = (cur / prev - 1) * 100
        bar_hour = int(candles[i]['t']) // 3600000
        rate = fund_by_hour.get(bar_hour)
        if rate is None:
            continue
        mom_side = 'long' if mom_pct >= mom_threshold else ('short' if mom_pct <= -mom_threshold else None)
        fund_side = 'short' if rate >= fund_threshold else ('long' if rate <= -fund_threshold else None)
        if mom_side and fund_side and mom_side == fund_side:
            out.append((i, mom_side))
    return out


def strat_funding_followthrough(candles, funding, lookback=3, mom_threshold=0.5, fund_threshold=0.001):
    """funding と同方向順張り (funding高 = ロング多 → ロング follow)."""
    fund_by_hour = {int(rec['time']) // 3600000: float(rec['fundingRate']) * 100 for rec in funding}
    out = []
    for i in range(lookback + 20, len(candles) - 200):
        cur = float(candles[i]['c'])
        prev = float(candles[i - lookback]['c'])
        mom_pct = (cur / prev - 1) * 100
        bar_hour = int(candles[i]['t']) // 3600000
        rate = fund_by_hour.get(bar_hour)
        if rate is None:
            continue
        # funding 同方向順張り
        if rate >= fund_threshold and mom_pct >= mom_threshold:
            out.append((i, 'long'))
        elif rate <= -fund_threshold and mom_pct <= -mom_threshold:
            out.append((i, 'short'))
    return out


# ============================================================
# 時間帯依存
# ============================================================

def strat_time_of_day(candles, funding, hour_long_start=8, hour_long_end=14, hour_short_start=20, hour_short_end=2):
    """UTC時間帯依存: 特定時間帯で long/short."""
    out = []
    for i in range(20, len(candles) - 200):
        t = int(candles[i]['t'])
        hour = (t // 3600000) % 24
        in_long = hour_long_start <= hour < hour_long_end
        in_short = (hour_short_start <= hour < 24) or (0 <= hour < hour_short_end if hour_short_end < hour_short_start else False)
        if in_long:
            out.append((i, 'long'))
        elif in_short:
            out.append((i, 'short'))
    return out


def strat_asia_trend(candles, funding):
    """アジア時間 (00:00-08:00 UTC = 朝9時-17時 JST) の方向に乗る。 直近1時間動きでentry."""
    out = []
    for i in range(20, len(candles) - 200):
        hour = (int(candles[i]['t']) // 3600000) % 24
        if not (0 <= hour < 8):
            continue
        cur = float(candles[i]['c'])
        prev = float(candles[i - 1]['c'])
        if cur > prev * 1.003:
            out.append((i, 'long'))
        elif cur < prev * 0.997:
            out.append((i, 'short'))
    return out


# ============================================================
# 出来高ベース
# ============================================================

def strat_volume_spike_momentum(candles, funding, vol_lookback=10, vol_mult=2.0, mom_lookback=3, mom_threshold=0.3):
    """出来高急増 + モメンタム同方向."""
    out = []
    for i in range(max(vol_lookback, mom_lookback) + 20, len(candles) - 200):
        vols = [float(candles[j]['v']) for j in range(i - vol_lookback, i)]
        med_vol = sorted(vols)[len(vols) // 2]
        cur_vol = float(candles[i]['v'])
        if cur_vol < med_vol * vol_mult:
            continue
        cur = float(candles[i]['c'])
        prev = float(candles[i - mom_lookback]['c'])
        pct = (cur / prev - 1) * 100
        if pct >= mom_threshold:
            out.append((i, 'long'))
        elif pct <= -mom_threshold:
            out.append((i, 'short'))
    return out


# ============================================================
# 全戦略レジストリ (grid search用)
# ============================================================

STRATEGY_REGISTRY = {
    # トレンド
    'momentum':           (strat_momentum, [
        {'lookback': lb, 'threshold_pct': th}
        for lb in [2, 3, 5, 10]
        for th in [0.3, 0.5, 1.0, 1.5]
    ]),
    'ema_cross':          (strat_ema_cross, [
        {'fast': f, 'slow': s}
        for f, s in [(5, 20), (8, 21), (10, 30), (12, 26), (20, 50)]
    ]),
    'breakout':           (strat_breakout, [
        {'lookback': lb} for lb in [10, 20, 30, 50, 100]
    ]),
    # 平均回帰
    'bollinger':          (strat_bollinger_revert, [
        {'period': p, 'k': k}
        for p in [10, 20, 30]
        for k in [1.5, 2.0, 2.5, 3.0]
    ]),
    'rsi':                (strat_rsi_extreme, [
        {'period': p, 'ob': ob, 'os': os_}
        for p in [7, 14, 21]
        for ob, os_ in [(70, 30), (75, 25), (80, 20)]
    ]),
    # funding
    'funding_extreme':    (strat_funding_extreme, [
        {'threshold_pct': th} for th in [0.002, 0.005, 0.01, 0.02]
    ]),
    'funding_momentum':   (strat_funding_momentum, [
        {'lookback': lb, 'mom_threshold': mt, 'fund_threshold': ft}
        for lb in [3, 5]
        for mt in [0.3, 0.5, 1.0]
        for ft in [0.002, 0.005]
    ]),
    'funding_followthrough': (strat_funding_followthrough, [
        {'lookback': lb, 'mom_threshold': mt, 'fund_threshold': ft}
        for lb in [3, 5]
        for mt in [0.3, 0.5]
        for ft in [0.001, 0.003]
    ]),
    # 時間帯
    'time_of_day':        (strat_time_of_day, [
        {'hour_long_start': 8, 'hour_long_end': 14, 'hour_short_start': 20, 'hour_short_end': 2},
        {'hour_long_start': 14, 'hour_long_end': 20, 'hour_short_start': 2, 'hour_short_end': 8},
    ]),
    'asia_trend':         (strat_asia_trend, [{}]),
    # 出来高
    'volume_spike_momentum': (strat_volume_spike_momentum, [
        {'vol_lookback': vl, 'vol_mult': vm, 'mom_lookback': ml, 'mom_threshold': mt}
        for vl in [5, 10, 20]
        for vm in [1.5, 2.0, 3.0]
        for ml in [3, 5]
        for mt in [0.3, 0.5]
    ]),
}
