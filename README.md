# propr-trader

[propr.xyz](https://www.propr.xyz/) (Hyperliquid上のcrypto prop firm) で自動売買bot を運用するためのツールとナレッジ集積場所。

## 構成

```
.
├── free/              # Free Trial challenge ($5,000 paper account) 用
│   ├── api.py         # propr API ラッパー (auth/orders/positions)
│   ├── snapshot.py    # 現状スナップショットを snapshots/ に保存
│   ├── set_hype_sltp.py
│   ├── btc_short.py
│   ├── eth_short.py
│   └── .env           # PROPR_API_KEY (git管理外)
├── snapshots/         # 時系列スナップショット (snapshots/YYYY-MM-DD/HH-MM-utc-snapshot.json)
├── KNOWLEDGE.md             # API の罠、Hyperliquid連携メモ、市況観察
├── STRATEGY.md              # 現在運用中の戦略と根拠
├── STRATEGY_SMART_MONEY.md  # 別枠: スマートマネー追従シグナル(設計フェーズ)
└── TRADE_LOG.md             # 主要トレードの記録(概要)
```

## 運用パターン: 知見の二重保存

**GitHub (このリポジトリ)** — コード + 知見ドキュメント + ローカルスナップショット
- `KNOWLEDGE.md` `STRATEGY.md` `TRADE_LOG.md` を毎セッション更新
- `python3 snapshot.py "context note"` でローカルにJSON保存

**Google Drive `propr-trader-logs`** — クロスデバイス閲覧用ミラー
- URL: https://drive.google.com/drive/folders/1TQqCOozs7OBji5t7P_dnzlDhOgG-QQUe
- 構造: `propr-trader-logs/YYYY-MM-DD/HH-MM-utc-snapshot.json`
- ローカル snapshotを撮ったら、対応する日付フォルダにアップロード(Claude側で MCP `create_file` を実行)

スナップショットは**上書きせず時系列で蓄積**。過去状態を後から見返せる。

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
