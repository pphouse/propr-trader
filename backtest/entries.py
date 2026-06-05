"""エントリーシグナル生成。

各 signal 関数: candles (list) → list of (entry_idx, side) tuples
"""
import random
from typing import List, Tuple, Dict


def random_entries(candles: list, prob: float = 0.01, seed: int = 42) -> List[Tuple[int, str]]:
    """ベースライン: 各bar に prob 確率で long/short ランダムentry."""
    rng = random.Random(seed)
    out = []
    for i in range(20, len(candles) - 200):  # warm-up と先読み余裕
        if rng.random() < prob:
            side = 'long' if rng.random() < 0.5 else 'short'
            out.append((i, side))
    return out


def momentum_entries(candles: list, lookback: int = 3, threshold_pct: float = 0.5) -> List[Tuple[int, str]]:
    """単純順張り: 直近 lookback本前と比較して threshold%以上動いた方向にentry."""
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


def funding_extreme_entries(candles: list, funding: list,
                            threshold_pct_per_hr: float = 0.005) -> List[Tuple[int, str]]:
    """B軸: funding 極端値 → 逆張り (funding高 = 買われ過ぎ → short, 低 = short過剰 → long)
    funding は 1h ごと、 candles の各 bar と時刻マッチング."""
    # funding を時刻 → rate にマップ
    fund_by_hour = {int(rec['time']) // 3600000: float(rec['fundingRate']) * 100 for rec in funding}
    out = []
    for i in range(20, len(candles) - 200):
        bar_hour = int(candles[i]['t']) // 3600000
        rate = fund_by_hour.get(bar_hour)
        if rate is None:
            continue
        if rate >= threshold_pct_per_hr:
            out.append((i, 'short'))  # ロング過剰 → 逆張りショート
        elif rate <= -threshold_pct_per_hr:
            out.append((i, 'long'))   # ショート過剰 → 逆張りロング
    return out


def momentum_and_funding(candles: list, funding: list,
                         mom_lookback: int = 3, mom_threshold: float = 0.5,
                         fund_threshold: float = 0.005) -> List[Tuple[int, str]]:
    """C+B 軸: モメンタムと funding が同方向の時のみ entry."""
    fund_by_hour = {int(rec['time']) // 3600000: float(rec['fundingRate']) * 100 for rec in funding}
    out = []
    for i in range(mom_lookback + 20, len(candles) - 200):
        cur = float(candles[i]['c'])
        prev = float(candles[i - mom_lookback]['c'])
        mom_pct = (cur / prev - 1) * 100
        bar_hour = int(candles[i]['t']) // 3600000
        rate = fund_by_hour.get(bar_hour)
        if rate is None:
            continue
        # mom long + funding low (short過剰) = LONG
        # mom short + funding high = SHORT
        mom_side = 'long' if mom_pct >= mom_threshold else ('short' if mom_pct <= -mom_threshold else None)
        fund_side = 'short' if rate >= fund_threshold else ('long' if rate <= -fund_threshold else None)
        if mom_side and fund_side and mom_side == fund_side:
            out.append((i, mom_side))
    return out


def three_axis_entries(candles: list, funding: list,
                       mom_lookback: int = 3, mom_threshold: float = 0.5,
                       fund_threshold: float = 0.005,
                       price_1h_threshold: float = 1.0) -> List[Tuple[int, str]]:
    """C軸 (momentum) + B軸 (funding) + D軸代替 (1h前との価格変化) 3軸一致."""
    fund_by_hour = {int(rec['time']) // 3600000: float(rec['fundingRate']) * 100 for rec in funding}
    out = []
    for i in range(max(mom_lookback, 1) + 20, len(candles) - 200):
        cur = float(candles[i]['c'])
        prev_mom = float(candles[i - mom_lookback]['c'])
        prev_1h = float(candles[i - 1]['c']) if i - 1 >= 0 else cur  # 1h前 = 1bar前 (1h足なので)
        mom_pct = (cur / prev_mom - 1) * 100
        price_1h_pct = (cur / prev_1h - 1) * 100
        bar_hour = int(candles[i]['t']) // 3600000
        rate = fund_by_hour.get(bar_hour)
        if rate is None:
            continue
        # 方向scoring (+1 long / -1 short / 0 neutral)
        mom_score = 1 if mom_pct >= mom_threshold else (-1 if mom_pct <= -mom_threshold else 0)
        fund_score = -1 if rate >= fund_threshold else (1 if rate <= -fund_threshold else 0)
        price_score = 1 if price_1h_pct >= price_1h_threshold else (-1 if price_1h_pct <= -price_1h_threshold else 0)
        total = mom_score + fund_score + price_score
        # 3軸一致 (絶対値3) のみ
        if total >= 3:
            out.append((i, 'long'))
        elif total <= -3:
            out.append((i, 'short'))
    return out
