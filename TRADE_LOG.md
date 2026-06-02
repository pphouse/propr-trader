# TRADE LOG — 主要トレード記録(概要)

各トレードの生JSONは Google Drive `propr-trader-logs` フォルダに格納:
https://drive.google.com/drive/folders/1TQqCOozs7OBji5t7P_dnzlDhOgG-QQUe

ここはハイレベルなサマリ。

---

## 2026-06-02

### Session 1: 初期セットアップ + ペアトレード構築

| 時刻(UTC) | アセット | アクション | 数量 | 価格 | PnL | メモ |
|---|---|---|---|---|---|---|
| 17:01:53 | HYPE | open short | 1.387 | $72.116 | — | 初期テスト |
| 17:14:23 | HYPE | close short | 1.387 | $71.713 | **+$0.56** | 直近の小幅利確 |
| 17:15:07 | HYPE | open long | 13.88 | $71.762 | — | メインのHYPE longポジ |
| 17:51:27 | HYPE | SL set | 13.88 | trig $70.50 | — | (pending) |
| 17:51:28 | HYPE | TP set | 13.88 | trig $76.00 | — | (pending) |
| 17:53:46 | BTC | open short (5x) | 0.030 | $67,440 | — | 下落トレンド本体 |
| 17:53:46 | BTC | SL/TP set | — | trig $68,553/$64,540 | — | bracket |
| 18:03:52 | ETH | open short (5x) | 0.78 | $1,925 | — | BTCに乗せて強化 |
| 18:03:52 | ETH | SL/TP set | — | trig $1,958.7/$1,832.6 | — | bracket |
| **19:17:19** | **HYPE** | **SL hit** | **13.88** | **$70.50** | **-$17.52** | 想定通りの損切り |

**Session 1 累計**: realized -$16.96, 含み益 +$43.6 (BTC short +$22.57 / ETH short +$21.22)
ネット: **+$26.08** (口座 $5,024.33 / +0.49%)
