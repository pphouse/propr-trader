# Hetzner Cloud VPS セットアップ手順

ローカル Mac の cron / GitHub Actions に依存せず、Hetzner の CX11 (€4.59/月) で autopilot を回す。

## Step 1: Hetzner Cloud アカウント

1. https://console.hetzner.cloud にアクセス、サインアップ (メール認証のみ)
2. 支払い方法: クレジットカード or PayPal
3. プロジェクト作成 (名前: `propr-trader`)

## Step 2: SSH 鍵を登録

ローカル Mac で:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/hetzner_propr -C "propr-trader hetzner" -N ""
cat ~/.ssh/hetzner_propr.pub
```

出力を Hetzner Console → Security → SSH Keys → Add SSH Key に貼り付け。

## Step 3: VM 作成

Console → Servers → New Server:

| 項目 | 値 |
|---|---|
| Location | Helsinki (fsn1, eu-central) または Singapore (sin) ※近い方 |
| Image | Ubuntu 24.04 |
| Type | **CX22** (Shared vCPU x86, 2 vCPU/4GB/40GB SSD, €4.59/月) |
| Networking | IPv4 + IPv6 both ON |
| SSH Keys | 先ほど登録した鍵を選択 |
| Name | `propr-trader` |

※ CX11 は2024年廃止済。後継は CX22 (実質同価格でスペックUP)

「Create & Buy now」→ IPv4 が割り振られる。

## Step 4: SSH 接続

```bash
ssh -i ~/.ssh/hetzner_propr root@<IPv4>
```

初回は host fingerprint 確認、yes。

## Step 5: 一般ユーザー作成 (root 直運用は避ける)

VPS 内で:

```bash
adduser --disabled-password --gecos "" naoto
usermod -aG sudo naoto
mkdir -p /home/naoto/.ssh
cp ~/.ssh/authorized_keys /home/naoto/.ssh/
chown -R naoto:naoto /home/naoto/.ssh
chmod 700 /home/naoto/.ssh
chmod 600 /home/naoto/.ssh/authorized_keys
echo "naoto ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/naoto
```

`exit` して、改めて `ssh -i ~/.ssh/hetzner_propr naoto@<IPv4>`。

## Step 6: bootstrap 実行

```bash
curl -fsSL https://raw.githubusercontent.com/pphouse/propr-trader/master/vps/bootstrap.sh | bash
```

これで:
- Node 22 + npm + Claude Code CLI install
- python3 + python-ulid install
- `~/propr-trader` に repo clone
- `~/.propr-env` テンプレ作成
- cron entry 追加 (`*/10 * * * *`)

## Step 7: secret 設定

```bash
nano ~/.propr-env
```

`REPLACE_ME` を実値に書き換える:

```
export PROPR_API_KEY="pk_live_sRjnI6P17zdQuux0RVyE9MsZSwJCmjtX9MgthytNcGyyDTHy"
export CLAUDE_CODE_OAUTH_TOKEN="sk-ant-oat01-..."
```

CLAUDE_CODE_OAUTH_TOKEN は、ローカル Mac で `claude setup-token` 再実行して新しいやつを貼る (前のは公開チャットに出たので rotation 必須)。

## Step 8: 手動テスト

```bash
~/propr-trader/vps/run.sh 2>&1 | tee /tmp/first-run.log
```

期待される動き:
1. `git pull` で repo 最新化
2. claude が起動 → autopilot/prompt.md 実行 → snapshot/news/judge/execute
3. 5〜7分で終了
4. propr account に変動 (新規ポジ or 既存ポジ調整)

## Step 9: cron 確認

```bash
crontab -l
# 期待: */10 * * * * /home/naoto/propr-trader/vps/run.sh >> /home/naoto/autopilot.log 2>&1

tail -f ~/autopilot.log
```

## Step 10: GitHub Actions 停止

ローカル Mac から:

```bash
gh workflow disable autopilot.yml --repo pphouse/propr-trader
```

(後で戻したくなったら `gh workflow enable autopilot.yml`)

## 運用 Tips

- ログローテーション (任意): `~/autopilot.log` が肥大化したら `truncate -s 0 ~/autopilot.log`
- VPS 再起動後も cron は自動復帰
- repo を更新したい時: `cd ~/propr-trader && git pull` (`run.sh` 内で毎回 pull もしてる)
- 緊急停止: `crontab -r` (cron 全消し) or `crontab -e` で行頭に `#` 付ける
- VPS 削除: Hetzner Console → Server → Delete (請求は時間単位で停止)

## 月額コスト

- VPS: **€4.59** (≈ $5)
- データ転送: 20TB 含む (autopilotで使うのは数百MB/月)
- 他費用なし

## トラブルシュート

| 症状 | 対処 |
|---|---|
| `claude: command not found` | `which claude` → `/usr/bin/claude` に symlink 作成 or PATH 修正 |
| `PROPR_API_KEY not found` | `~/.propr-env` の中身確認、`source ~/.propr-env && echo $PROPR_API_KEY` |
| `401 Unauthorized` (claude) | OAuth token expire、ローカルで `claude setup-token` 再実行 → ~/.propr-env 更新 |
| cron 動かない | `systemctl status cron` で daemon 確認、`grep CRON /var/log/syslog` |
