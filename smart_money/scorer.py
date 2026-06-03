"""Hyperliquid公開APIでwalletを採点する。

STRATEGY_SMART_MONEY.md 段階2の実装。
試行回数・Sharpe・最大DD・PF・単一集中度・メイカー比率を計算し、
quailified なwalletかを判定する。

使い方:
  python3 scorer.py 0xbdfa4f4492dd7b7cf211209c4791af8d52bf5c50
  python3 scorer.py --batch wallets_raw.json
"""
import sys
import json
import math
import time
import urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta
from statistics import mean, stdev
from collections import defaultdict

HL_INFO = "https://api.hyperliquid.xyz/info"

# しきい値 (compass_artifact.md 段階2に従う、ただしAPI制約に合わせ調整)
# - `userFillsByTime` は直近~2000件しか返らない (startTime無視) ので期間判定は portfolio由来
THRESHOLDS = {
    "min_portfolio_days": 90,    # portfolio.perpAllTime の accountValueHistory日数
    "min_recent_fills": 50,      # 直近 fills の最低件数 (極端に低頻度を除外)
    "min_sharpe": 1.0,
    "max_dd_pct": 30,
    "min_profit_factor": 1.3,
    "max_top3_pnl_share": 0.50,
}


def hl_post(body, timeout=20):
    req = urllib.request.Request(
        HL_INFO,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def fetch_portfolio(wallet):
    """portfolio API: [[period, {accountValueHistory, pnlHistory, vlm}], ...]"""
    return hl_post({"type": "portfolio", "user": wallet})


def fetch_fills_by_time(wallet, start_ms, end_ms, max_fills=5000):
    """userFillsByTime: 500件/回。ページングして全部取る (上限max_fillsまで)。"""
    all_fills = []
    cursor = start_ms
    pages = 0
    while True:
        r = hl_post({
            "type": "userFillsByTime",
            "user": wallet,
            "startTime": cursor,
            "endTime": end_ms,
        })
        if not r:
            break
        all_fills.extend(r)
        pages += 1
        if len(r) < 500:
            break
        if len(all_fills) >= max_fills:
            break  # 巨大bot保護(MM bot は 10万件超もある)
        last_t = max(f["time"] for f in r)
        if last_t == cursor:
            break
        cursor = last_t + 1
        time.sleep(0.5)  # 重いAPI、rate limit保護
    # dedup
    seen = set()
    uniq = []
    for f in all_fills:
        key = (f.get("hash"), f.get("oid"), f.get("tid"))
        if key in seen: continue
        seen.add(key)
        uniq.append(f)
    return uniq, pages


def fetch_clearinghouse(wallet):
    return hl_post({"type": "clearinghouseState", "user": wallet, "dex": ""})


def calc_pnl_based_metrics(portfolio, period="perpAllTime"):
    """pnlHistoryベースで日次リターン+max DD計算 (入出金フリー)。

    Returns: dict with rets, days, dd_pct, days_count
    """
    for label, data in portfolio:
        if label != period:
            continue
        pnl_hist = data.get("pnlHistory", [])
        avh = data.get("accountValueHistory", [])
        if len(pnl_hist) < 2 or not avh:
            return {}

        # 初期account value (リターン正規化の分母)
        initial_av = float(avh[0][1])
        if initial_av <= 0:
            # 初期0なら最大値を使う
            initial_av = max(float(v) for _, v in avh) or 1

        # 日次binning: 各UTC日の最終pnl値
        by_day = {}
        for ms, v in pnl_hist:
            day = datetime.fromtimestamp(int(ms)/1000, tz=timezone.utc).date()
            by_day[day] = float(v)
        days = sorted(by_day.keys())
        if len(days) < 2:
            return {}
        pnl_vals = [by_day[d] for d in days]

        # 日次リターン (pnl差分 / 初期av)
        rets = []
        for i in range(1, len(pnl_vals)):
            rets.append((pnl_vals[i] - pnl_vals[i-1]) / initial_av)

        # max DD (累積PnL曲線のpeak-to-trough、初期av基準で%表示)
        peak = pnl_vals[0]
        max_dd_abs = 0
        for v in pnl_vals:
            peak = max(peak, v)
            max_dd_abs = max(max_dd_abs, peak - v)
        dd_pct = (max_dd_abs / initial_av) * 100

        return {
            "rets": rets,
            "days": days,
            "days_count": len(days),
            "dd_pct": dd_pct,
            "max_dd_abs": max_dd_abs,
            "initial_av": initial_av,
            "final_pnl": pnl_vals[-1],
            "peak_pnl": peak,
        }
    return {}


def sharpe(rets, rf_annual=0.045):
    if len(rets) < 30:
        return None
    rf_daily = rf_annual / 365
    excess = [r - rf_daily for r in rets]
    m = mean(excess)
    s = stdev(excess) if len(excess) > 1 else 0
    if s == 0:
        return None
    return m / s * math.sqrt(365)


def max_drawdown_pct(vals):
    if len(vals) < 2:
        return None
    peak = vals[0]
    max_dd = 0
    for v in vals:
        peak = max(peak, v)
        if peak > 0:
            dd = (peak - v) / peak * 100
            max_dd = max(max_dd, dd)
    return max_dd


def analyze_fills(fills):
    """fills: list of {closedPnl, coin, dir, px, sz, time, fee, crossed, ...}"""
    if not fills:
        return {}
    # 期間 (time は ms epoch のはずだが、念のためチェック)
    times = [int(f["time"]) for f in fills]
    span_days = (max(times) - min(times)) / (1000 * 86400)
    # debug: 単位異常検知
    first_t_iso = datetime.fromtimestamp(min(times)/1000, tz=timezone.utc).isoformat()
    last_t_iso = datetime.fromtimestamp(max(times)/1000, tz=timezone.utc).isoformat()

    # PnL列 (closedPnlが意味あるのは決済fillのみ。openなら0)
    pnls = [float(f.get("closedPnl", 0)) for f in fills]
    wins = [p for p in pnls if p > 0]
    losses = [-p for p in pnls if p < 0]
    win_rate = len(wins) / (len(wins) + len(losses)) if (wins or losses) else None
    pf = (sum(wins) / sum(losses)) if losses and sum(losses) > 0 else None

    # 単一集中度: PnL絶対額上位3件 / 総|PnL|
    abs_pnls = sorted([abs(p) for p in pnls if p != 0], reverse=True)
    top3_share = (sum(abs_pnls[:3]) / sum(abs_pnls)) if abs_pnls else None

    # メイカー比率
    makers = sum(1 for f in fills if not f.get("crossed", True))
    maker_ratio = makers / len(fills) if fills else None

    # アセット分布
    by_asset = defaultdict(int)
    for f in fills:
        by_asset[f["coin"]] += 1
    top_assets = sorted(by_asset.items(), key=lambda x: -x[1])[:5]

    # 累計fees, gross PnL
    total_fees = sum(float(f.get("fee", 0)) for f in fills)
    gross_pnl = sum(pnls)

    return {
        "trade_count": len(fills),
        "span_days": round(span_days, 1),
        "first_fill_utc": first_t_iso,
        "last_fill_utc": last_t_iso,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 3) if win_rate else None,
        "profit_factor": round(pf, 2) if pf else None,
        "top3_pnl_share": round(top3_share, 3) if top3_share else None,
        "maker_ratio": round(maker_ratio, 3) if maker_ratio is not None else None,
        "total_fees": round(total_fees, 2),
        "gross_realized_pnl": round(gross_pnl, 2),
        "top_assets": top_assets,
    }


def classify_alpha_source(fills_stats, daily_funding_pct=None):
    """アルファ源泉の分類: 方向性 / ファンディング / MM"""
    mr = fills_stats.get("maker_ratio") or 0
    tc = fills_stats.get("trade_count") or 0
    if mr > 0.7:
        return "market_making"
    if tc > 0 and (fills_stats.get("win_rate") or 0) > 0.7 and (fills_stats.get("profit_factor") or 0) > 2:
        # 異常に高い勝率+PFはファンディングファーミングかMM
        return "likely_funding_farming"
    return "directional"


def qualify(score):
    """しきい値判定。reasonのリスト返す(空なら合格)"""
    reasons = []
    if score.get("portfolio_days", 0) < THRESHOLDS["min_portfolio_days"]:
        reasons.append(f"portfolio<{THRESHOLDS['min_portfolio_days']}d")
    if score.get("trade_count", 0) < THRESHOLDS["min_recent_fills"]:
        reasons.append(f"recent_fills<{THRESHOLDS['min_recent_fills']}")
    sh = score.get("sharpe_annual")
    if sh is None or sh < THRESHOLDS["min_sharpe"]:
        reasons.append(f"sharpe<{THRESHOLDS['min_sharpe']}")
    dd = score.get("max_drawdown_pct")
    if dd is not None and dd > THRESHOLDS["max_dd_pct"]:
        reasons.append(f"dd>{THRESHOLDS['max_dd_pct']}%")
    pf = score.get("profit_factor")
    if pf is None or pf < THRESHOLDS["min_profit_factor"]:
        reasons.append(f"pf<{THRESHOLDS['min_profit_factor']}")
    top3 = score.get("top3_pnl_share")
    if top3 is not None and top3 > THRESHOLDS["max_top3_pnl_share"]:
        reasons.append(f"top3_concentration>{THRESHOLDS['max_top3_pnl_share']}")
    alpha = score.get("alpha_source")
    if alpha != "directional":
        reasons.append(f"alpha={alpha}")
    return reasons


def score_wallet(wallet, days_back=90, verbose=True):
    """1walletを採点。"""
    if verbose:
        print(f"\n[{wallet}]")
        print("  fetching clearinghouseState...")
    state = fetch_clearinghouse(wallet)
    ms = state.get("marginSummary", {})
    account_value = float(ms.get("accountValue", 0))

    if account_value == 0 and not state.get("assetPositions"):
        if verbose:
            print(f"  empty wallet (accountValue=0). Skip.")
        return {"wallet": wallet, "error": "empty_wallet"}

    if verbose:
        print(f"  accountValue=${account_value:,.0f}")
        print(f"  fetching portfolio...")
    portfolio = fetch_portfolio(wallet)

    if verbose:
        print(f"  fetching userFillsByTime (recent ~2000)...")
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - days_back * 86400 * 1000
    # 注: API は startTime 無視で直近~2000件しか返さない。max_fills=2000で1ページのみ
    fills, pages = fetch_fills_by_time(wallet, start_ms, now_ms, max_fills=2000)
    if verbose and fills:
        span_recent = (max(f['time'] for f in fills) - min(f['time'] for f in fills)) / (1000*86400)
        print(f"  {len(fills)} recent fills covering {span_recent:.2f}d ({pages} pages)")

    fills_stats = analyze_fills(fills)
    metrics = calc_pnl_based_metrics(portfolio, period="perpAllTime")
    sh = sharpe(metrics.get("rets", [])) if metrics else None
    dd = metrics.get("dd_pct") if metrics else None
    days_count = metrics.get("days_count", 0)

    alpha = classify_alpha_source(fills_stats)

    result = {
        "wallet": wallet,
        "account_value_now": account_value,
        "portfolio_days": days_count,
        "initial_av": round(metrics.get("initial_av", 0), 2) if metrics else None,
        "final_pnl": round(metrics.get("final_pnl", 0), 2) if metrics else None,
        "peak_pnl": round(metrics.get("peak_pnl", 0), 2) if metrics else None,
        **fills_stats,
        "sharpe_annual": round(sh, 2) if sh else None,
        "max_drawdown_pct": round(dd, 1) if dd else None,
        "alpha_source": alpha,
    }
    result["qualified"] = not bool(qualify(result))
    result["reject_reasons"] = qualify(result)
    return result


def print_score(s):
    if "error" in s:
        print(f"  ERROR: {s['error']}")
        return
    print(f"  account_value:     ${s['account_value_now']:,.0f}  (initial_av ${s.get('initial_av')})")
    print(f"  portfolio_days:    {s.get('portfolio_days')}")
    print(f"  pnl peak/final:    ${s.get('peak_pnl')} / ${s.get('final_pnl')}")
    print(f"  recent_fills:      {s.get('trade_count', 0)} (span {s.get('span_days')}d)")
    print(f"  win_rate:          {s.get('win_rate')}")
    print(f"  profit_factor:     {s.get('profit_factor')}")
    print(f"  top3_concentr.:    {s.get('top3_pnl_share')}")
    print(f"  maker_ratio:       {s.get('maker_ratio')}")
    print(f"  sharpe_annual:     {s.get('sharpe_annual')}")
    print(f"  max_dd_pct:        {s.get('max_drawdown_pct')}")
    print(f"  alpha_source:      {s.get('alpha_source')}")
    print(f"  top_assets:        {s.get('top_assets')}")
    print(f"  gross_realized:    ${s.get('gross_realized_pnl')}")
    if s["qualified"]:
        print(f"  ✓ QUALIFIED")
    else:
        print(f"  ✗ rejected: {', '.join(s['reject_reasons'])}")


def main():
    if len(sys.argv) < 2:
        print("usage: scorer.py <wallet> [<wallet>...] | --batch <wallets.json>")
        sys.exit(1)

    if sys.argv[1] == "--batch":
        wallets = json.load(open(sys.argv[2]))
        if isinstance(wallets, dict):
            wallets = wallets.get("wallets") or list(wallets.values())
    else:
        wallets = sys.argv[1:]

    out_dir = Path(__file__).parent / "scored"
    out_dir.mkdir(exist_ok=True)

    qualified = []
    rejected = []
    for i, w in enumerate(wallets):
        try:
            s = score_wallet(w)
            print_score(s)
            (out_dir / f"{w}.json").write_text(json.dumps(s, indent=2, default=str))
            if s.get("qualified"):
                qualified.append(w)
            else:
                rejected.append(w)
        except Exception as e:
            print(f"\n[{w}] FAILED: {e}")
            rejected.append(w)
        # wallet間 sleep でrate limit避ける
        if i < len(wallets) - 1:
            print(f"  ...sleep 8s before next wallet (rate limit guard)")
            time.sleep(8)

    print(f"\n=== SUMMARY ===")
    print(f"qualified: {len(qualified)} / {len(wallets)}")
    for w in qualified:
        print(f"  ✓ {w}")
    print(f"rejected:  {len(rejected)}")

    # qualified を別ファイルにdump
    q_path = Path(__file__).parent / "wallets_qualified.json"
    q_path.write_text(json.dumps({"updated_at": datetime.now(timezone.utc).isoformat(),
                                  "wallets": qualified}, indent=2))
    print(f"\nqualified list saved: {q_path}")


if __name__ == "__main__":
    main()
