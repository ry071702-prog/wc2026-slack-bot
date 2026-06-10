# 2026 FIFAワールドカップ Slack通知Bot

football-data.org v4 から試合情報を取得し、GitHub Actions から Slack Incoming Webhook に投稿します。

## セットアップ

1. [football-data.org](https://www.football-data.org/client/register) でアカウントを作成し、APIキーを取得します。
2. 実装前検証として、2026大会のデータが返ることを確認します。

   ```bash
   export KEY="取得したAPIキー"
   curl -H "X-Auth-Token: $KEY" \
     "https://api.football-data.org/v4/competitions/WC/matches?dateFrom=2026-06-11&dateTo=2026-06-13"
   ```

   `matches` に2026大会が返らない場合は、`src/providers/` に同じ `Provider` インターフェースの API-FOOTBALL 実装を追加し、`src/main.py` の生成先を差し替えてください。
3. Slack で Incoming Webhook を作成し、投稿先チャンネルを選びます。
4. GitHub リポジトリの `Settings` → `Secrets and variables` → `Actions` で次を設定します。

   Secrets:

   - `SLACK_WEBHOOK_URL`: Slack Incoming Webhook URL
   - `FOOTBALL_DATA_API_KEY`: football-data.org APIキー

   Variables（任意）:

   - `NOTIFY_MINUTES_BEFORE`: 開始前通知の分数。既定 `15`
   - `MENTION_JAPAN`: 日本戦で `<!here>` を付ける場合は `true`
   - `DRY_RUN`: Slackへ送らずActionsログへJSONを出す場合は `true`

## ローカル実行

Python 3.11 以上を使用します。

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

export FOOTBALL_DATA_API_KEY="..."
export SLACK_WEBHOOK_URL="..."
python -m src.main --mode notify
python -m src.main --mode digest
```

Slackへ投稿せず Block Kit JSON を確認する場合、Webhook URL は不要です。

```bash
export FOOTBALL_DATA_API_KEY="..."
DRY_RUN=true MENTION_JAPAN=true python -m src.main --mode notify
DRY_RUN=true python -m src.main --mode digest
```

APIキーなしでの代替確認は、保存済みfixtureとモックを使うテストで行えます。

```bash
python -m pytest tests/ -q
DRY_RUN=true python -m pytest tests/test_dry_run.py -q -s
```

## 運用

- `notify.yml` は5分ごとに開始前通知と試合結果を確認します。
- `digest.yml` は毎日 `22:30 UTC`（翌日 `07:30 JST`）に当日分を投稿します。
- API呼び出しは各実行1回です。notify はJST基準で昨日から明日を取得します。digest はJST当日を覆うUTC上の2日を取得し、JST日付で当日分だけに絞ります。
- 通知済みIDとdigest日付は `state/notified.json` に保存し、送信成功後だけGitHub Actionsがコミットします。
- `DRY_RUN=true` ではstateを変更しません。
- notify は `2026-06-11 00:00 UTC` から `2026-07-20 23:59:59 UTC`、digest は同期間のJST日付だけ動作します。
- GitHub Actions の遅延により、開始前通知が設定時刻より遅れる可能性があります。

## 大会終了後

GitHub リポジトリの `Actions` から2つのworkflowを無効化してください。無効化しなくても期間ガードによりAPIアクセスとSlack投稿は自然停止します。
