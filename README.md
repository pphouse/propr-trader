# propr-trader

[propr.xyz](https://www.propr.xyz/) (Hyperliquid上のcrypto prop firm) で自動売買bot を運用するためのツールとナレッジ集積場所。

## 構成

```
.
├── free/              # Free Trial challenge ($5,000 paper account) 用
│   ├── api.py         # propr API ラッパー (auth/orders/positions)
│   ├── set_hype_sltp.py
│   ├── btc_short.py
│   ├── eth_short.py
│   └── .env           # PROPR_API_KEY (git管理外)
├── KNOWLEDGE.md       # API の罠、Hyperliquid連携メモ、市況観察
├── STRATEGY.md        # 現在運用中の戦略と根拠
└── TRADE_LOG.md       # 主要トレードの記録(概要)
```

トレード履歴の生データJSONは Google Drive `propr-trader-logs` フォルダに別途蓄積:
https://drive.google.com/drive/folders/1TQqCOozs7OBji5t7P_dnzlDhOgG-QQUe

## クイックスタート

```bash
cd free
echo "PERPR_API_KEY=pk_live_xxx" > .env  # propr.xyz/settings で生成
pip install python-ulid
python3 -c "import api; print(api.account())"
```

## ドキュメント

- propr 公式: https://github.com/XBorgLabs/propr-docs
- Hyperliquid: https://hyperliquid.gitbook.io/hyperliquid-docs/
