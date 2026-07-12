# 撤収手順 (大会終了 2026-07-20 以降)

大会期間は 2026-06-11 〜 07-20  決勝は **7/20 04:00 JST** キックオフ (3位決定戦 = 7/19 06:00 JST)
撤収は **決勝の結果通知が Slack に流れたのを確認してから** 実行する (7/20 の昼以降が安全)

---

## 1. いま動いているもの (定期実行の全量)

| workflow | トリガ | 止め忘れると何が起きるか |
|---|---|---|
| `notify.yml` | cron `*/10 * * 6,7 *` + **外部からの workflow_dispatch (5分毎・下記5参照)** | `src/main.py` の期間ガード (`TOURNAMENT_END_UTC = 2026-07-21`) で即 return するので **Slack 投稿はしない**  ただし run 自体は起動し続け、pages / enrich への dispatch 判定も走る |
| `digest.yml` | cron `30 0 * 6,7 *` | `is_digest_period` (〜7/20 JST) で即 return  投稿しない |
| `enrich.yml` | cron `15 1,7,13 * 6,7 *` + notify から毎時 dispatch | **期間ガード無し**  YouTube Data API / Google News RSS / ESPN / Slack `reactions.get` を叩き続ける  `data/` への無意味なコミットと pages 再デプロイの dispatch も継続する |
| `pages.yml` | cron `0 21` / `0 9` (6,7月) + main への push (`site/` `scripts/` `src/` `data/`) + 他 workflow からの dispatch | **期間ガード無し**  1日2回サイトを再ビルドし続ける |
| `announce.yml` | cron `45 0 11 6 *` (6/11 のみ) | 本体に `if now.year != 2026` ガードがあるので誤投稿はしない |
| `squads.yml` | cron `10 0 11 6 *` (6/11 のみ) | **期間ガード無し**  2027-06-11 に squads を再取得してコミットする |
| `lineup.yml` / `lineup-dryrun.yml` / `test-post.yml` / `verify.yml` | 手動のみ | 放置しても勝手には動かない |

> **最重要**: GitHub の cron に「年」の指定は無い  月が `6,7` のワークフローは **2027年の6〜7月に全部また動き出す**
> notify / digest は期間ガードで無害だが、**enrich / pages / squads はガードが無いので実際に走る**

### 誤投稿・コストの実態
- **Slack 誤投稿リスクは実質なし**: notify / digest は期間ガードで投稿前に return する
- ただし enrich の `build_match_predictions.py` は Slack を **読み取る** (`reactions.get`)  投稿はしないがトークンは使い続ける
- 金銭コストはほぼゼロ (public repo の Actions は無料枠)  実害は **YouTube Data API のクォータ消費 / Slack トークンの継続利用 / 無意味なコミットと run 履歴**
- 日本代表は R32 敗退済み (6/29 Brazil 2-1 Japan) なので、日本戦のスタメン自動投稿・勝敗ポールはもう発火しない

---

## 2. 撤収コマンド

```bash
bash scripts/teardown.sh            # dry-run: 何を止めるか表示するだけ
bash scripts/teardown.sh --apply    # cron / 自動 dispatch を持つ workflow を止める
bash scripts/teardown.sh --apply --all   # 手動専用の workflow も含めて全部止める
```

- `gh workflow disable` は **cron と workflow_dispatch の両方**を止める
- 復活は `gh workflow enable <file>`

---

## 3. 期間ガードはどこにあるか

| 場所 | 内容 |
|---|---|
| `src/main.py:34-35` | `TOURNAMENT_START_UTC` / `TOURNAMENT_END_UTC` (= 2026-07-21 UTC)  → `is_notify_period()` |
| `src/main.py:226-228` | `is_digest_period()` (2026-06-11 〜 07-20 JST) |
| `src/main.py:580-588` | `main()` の冒頭で期間外なら **API 初期化前に return** する |
| `.github/workflows/*.yml` | cron の月指定 `6,7` (= 年をまたぐと再発火する弱いガード) |
| `scripts/build_*.py` の `TOURNAMENT_START` / `TOURNAMENT_END` | **実行ガードではなく取得日付レンジ**  期間外に呼ばれても素通りで走る (要注意) |

つまり「期間ガード」で守られているのは **Slack 投稿 (notify / digest) だけ**
enrich / pages を止めるには **workflow を disable するしかない**

---

## 4. Pages が詰まったときの復旧 (2026-07-09 に発生した実障害)

**症状**: `pages.yml` の run が `pending` のまま、または全て `cancelled`  サイトが何日も更新されない

**原因**: notify (5分毎) が pages を無条件に dispatch していたため queue が捌けず、後から来た run が古い pending run をキャンセルし続けた
デプロイ着手後にキャンセルされた run が `github-pages` 環境に **`waiting` のままのデプロイ**を残し、環境がロックされて以後すべての pages run が pending で詰まった

**復旧**:

```bash
REPO=ry071702-prog/wc2026-slack-bot

# 1. 詰まっている pending run を止める
gh run list --workflow pages.yml --status pending --json databaseId --jq '.[].databaseId' \
  | xargs -r -I{} gh run cancel {}

# 2. waiting のまま残っているデプロイを特定する
gh api "repos/$REPO/deployments?environment=github-pages&per_page=10" --jq '.[] | "\(.id) \(.created_at)"'
gh api "repos/$REPO/deployments/<ID>/statuses" --jq '.[0].state'   # waiting なら これが詰まりの原因

# 3. 無効化する (GitHub UI: Settings → Environments → github-pages → 該当デプロイを Cancel でも可)
gh api -X POST "repos/$REPO/deployments/<ID>/statuses" -f state=inactive

# 4. 再デプロイして確認する
gh workflow run pages.yml
gh run watch "$(gh run list --workflow pages.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
curl -sI https://ry071702-prog.github.io/wc2026-slack-bot/ | grep last-modified
```

**再発防止** (2026-07-12 実装): `notify.yml` の "Trigger site rebuild" に in-flight ガードを追加した
実行中/待機中の pages run がある間は dispatch せず、20分以上 pending の run があれば `::warning::` を出す

---

## 5. 外部ディスパッチャ (要特定・要停止)

`notify.yml` は workflow 内の cron (`*/10`) とは別に、**5分毎に `workflow_dispatch` されている** (actor = `ry071702-prog` = 個人アカウント/PAT 経由)

- リポジトリ内の workflow・launchd (`~/Library/LaunchAgents`)・crontab のいずれにも該当する定義が **見つからない**
- → 外部サービス (cron-job.org 等) か別ホストのスケジューラの可能性が高い
- `gh workflow disable notify.yml` すれば dispatch は拒否されるので **投稿・コストの実害は消える**  ただしディスパッチャ側はエラーを吐き続けるので、見つけて止めるのが望ましい

---

## 6. その他の後片付け

- **サイト**: GitHub Pages は静的で無料  記念に残してよい (止めるなら Settings → Pages → Unpublish)
- **予想アプリ (bolt_app)**: launchd の `com.wc2026.bolt.plist` は既に `.disabled`  常駐プロセスは無い
- **優勝予想の結果発表**: 自動投稿の仕組みは無い (`/ranking` = bolt_app の Socket Mode 常駐が必要)  やるなら決勝後に手動で
- **Secrets**: 転用しないなら `SLACK_BOT_TOKEN` / `SLACK_WEBHOOK_URL` / `FOOTBALL_DATA_API_KEY` / `YOUTUBE_API_KEY` / `GOOGLE_API_KEY` をローテート or 削除  Slack App はアーカイブ

---

## 7. 撤収チェックリスト

- [ ] 決勝 (7/20 04:00 JST) の結果通知が Slack に流れた
- [ ] 最終日のダイジェストが流れた
- [ ] (任意) 優勝予想の結果発表を手動で投稿した
- [ ] `bash scripts/teardown.sh --apply` を実行した
- [ ] `gh workflow list --all` で cron 系が全て `disabled_manually` になっている
- [ ] 外部の5分毎ディスパッチャを特定して止めた
- [ ] (任意) Secrets のローテート / Slack App のアーカイブ
- [ ] (任意) サイトを残すか決めた
