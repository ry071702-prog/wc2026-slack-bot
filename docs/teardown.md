# 撤収手順 (大会終了 2026-07-20 以降)

大会期間は 2026-06-11 〜 07-20  決勝は **7/20 04:00 JST** キックオフ (3位決定戦 = 7/19 06:00 JST)
撤収は **決勝の結果通知が Slack に流れたのを確認してから** 実行する (7/20 の昼以降が安全)

**なぜ撤収が必要か** — GitHub の cron に「年」は指定できない  cron の月指定が `6,7` のワークフローは、放置すると **2027年6〜7月にまた全部動き出す**
しかも期間ガード (`TOURNAMENT_END_UTC`) が守っているのは **Slack 投稿 (notify / digest) だけ**で、`enrich` / `pages` / `squads` はガード無しで実際に走る

---

## 1. 7/20 当日にやること (上から順に実行するだけ)

- [ ] **1. 決勝 (7/20 04:00 JST) の結果通知が Slack に流れたのを確認する**
- [ ] **2. 最終日のダイジェスト (7/20 09:30 JST) が流れたのを確認する**
- [ ] **3. (任意) 優勝予想の結果発表を手動で投稿する** — 自動投稿の仕組みは無い (`/ranking` は bolt_app の Socket Mode 常駐が要る)  やるならここで

- [ ] **4. 何が止まるか確認する (dry-run  何も起きない)**
      ```bash
      cd ~/wc2026-slack-bot && bash scripts/teardown.sh
      ```

- [ ] **5. 止める**
      ```bash
      bash scripts/teardown.sh --apply
      ```
      → cron / 自動 dispatch を持つ 6本 (notify / enrich / pages / squads / digest / announce) を disable する
      → 最後に自動で検証し、止めきれていなければ `NG` を出して exit 1 する  `OK` が出れば完了
      → 手動専用の 4本 (lineup / lineup-dryrun / test-post / verify) も封じたいなら `--apply --all`

- [ ] **6. 外部の5分毎ディスパッチャを特定して止める** ← **これをやらないと撤収は完了しない** (下記 4 を読む)
      workflow を disable した時点で dispatch は弾かれるので **実害は消える**  ただし向こうは失敗し続けるので、見つけて止める

- [ ] **7. Slack Bot Token を無効化する** (下記 5 を読む)
      ワークフローを再有効化しただけでは投稿できない状態にする第二の防壁  Slack App をアーカイブ or `SLACK_BOT_TOKEN` / `SLACK_WEBHOOK_URL` を repo から削除

- [ ] **8. (任意) サイトを残すか決める** — GitHub Pages は静的で無料なので記念に残してよい  止めるなら Settings → Pages → Unpublish

> `data/` `state/` は GitHub Actions が repo に書き戻している  ローカルは origin より behind なことがあるので、撤収前後で手元から `git push` する用事があるときは必ず `git fetch` してから意図したファイルだけ `git add` する

---

## 2. いま動いているもの / 止め忘れると何が起きるか

| workflow | トリガ | 期間ガード | **止め忘れると (= 2027年6〜7月に)** |
|---|---|---|---|
| `notify.yml` | cron `*/10 * * 6,7 *` + **外部から5分毎の dispatch** | 投稿のみ有 | Slack 投稿はしない (`main.py` が即 return)  **だが "Hourly enrich dispatch" ステップは期間ガードの外にあり無条件で走る** → **毎時 enrich を叩き起こす**  notify を止めないと enrich は死なない |
| `enrich.yml` | cron `15 1,7,13 * 6,7 *` + **notify から毎時 dispatch** | **無し** | **実害の本体**  YouTube Data API (`search.list` = 100 unit/回  日次上限 10,000) を消費 / Google News RSS・ESPN・TheSportsDB を叩く / Slack `reactions.get` を読む / `data/` に無意味なコミットを積む / さらに pages を dispatch する |
| `pages.yml` | cron `0 21` `0 9` (6,7月) + main への push (`site/` `scripts/` `src/` `data/`) + 他 workflow から dispatch | **無し** | 1日2回 + dispatch の度にサイトを再ビルド・再デプロイし続ける |
| `squads.yml` | cron `10 0 11 6 *` (6/11 のみ) | **無し** | **2027-06-11 に発火**  football-data / API-Football から 2026年大会のスカッドを再取得して `data/` にコミットする |
| `digest.yml` | cron `30 0 * 6,7 *` | 有 | `is_digest_period` で即 return  **投稿はしない**  run だけ毎日空回りする |
| `announce.yml` | cron `45 0 11 6 *` (6/11 のみ) | 有 (yml 内に `year != 2026` ガード) | `SystemExit` で終了  **誤投稿はしない**  run だけ空回りする |
| `lineup.yml` `lineup-dryrun.yml` `test-post.yml` `verify.yml` | 手動 (`workflow_dispatch`) のみ | — | 勝手には動かない  ただし `test-post.yml` / `lineup.yml` は **手で叩くと Slack に投稿する**  誤操作も封じたいなら `--apply --all` |

### まとめ (どれが本当に危ないか)
- **Slack 誤投稿**: cron 経由では起きない (notify / digest / announce すべてガード済み)  リスクは「手動 workflow の誤操作」だけ
- **本当の実害**: `notify → enrich` の連鎖  **notify を止めないと enrich が毎時走り続け**、YouTube クォータを食い・Slack を読み・`data/` にゴミコミットを積み・pages を叩き続ける
- **金銭コスト**: public repo の Actions は無料枠なのでほぼゼロ  効いてくるのは **YouTube API クォータ** と **run 履歴 / コミット履歴の汚染**
- 日本代表は R32 敗退済み (6/29 Brazil 2-1 Japan) なので、日本戦のスタメン自動投稿・勝敗ポールはもう発火しない

---

## 3. 撤収コマンド

```bash
bash scripts/teardown.sh              # dry-run: 何を止めるか表示するだけ (既定)
bash scripts/teardown.sh --apply      # cron / 自動 dispatch を持つ 6本を止める
bash scripts/teardown.sh --apply --all   # GitHub 上の全 workflow を止める (手動専用も含む)
```

- `gh workflow disable` は **cron と workflow_dispatch の両方**を止める → 外部スケジューラからの dispatch も弾かれる
- スクリプトは毎回 **GitHub 上の実在 workflow とスクリプト内のリストを突き合わせる**  リストに無い workflow が GitHub にあれば警告した上で**安全側に倒して停止対象に含める** (workflow を足したのに撤収し忘れる事故の防止)
- `--apply` の後は **自動で検証**し、`disabled_manually` になっていないものがあれば `NG` を出して exit 1 する
- 元に戻すには `gh workflow enable <file>` (例: `gh workflow enable notify.yml`)

---

## 4. 外部ディスパッチャ (要特定・要停止  ユーザータスク)

`notify.yml` は workflow 内の cron (`*/10`) とは別に、**5分毎に `workflow_dispatch` されている** (actor = `ry071702-prog` = 個人アカウント / PAT 経由)

**実体は未特定**  調べて見つからなかった場所:
- リポジトリ内の workflow (他の workflow からの dispatch ではない)
- launchd (`~/Library/LaunchAgents`)
- crontab (`crontab -l`)
- 他のローカルリポジトリ

**手掛かり**:
- 間隔はきっちり5分  actor は `ry071702-prog` なので **個人の PAT (Personal Access Token) を使う何か**
- 外部サービス (cron-job.org / Zapier / Make / GAS のトリガ / 別ホストの cron) の線が濃い
- PAT 側から辿るのが早い: GitHub → Settings → Developer settings → Personal access tokens で **最終使用日時が「数分前」になっているトークン**を探す  それがディスパッチャの正体  用途不明なら revoke する (= ディスパッチャが止まる)

**止めなくても実害は消える** (`gh workflow disable notify.yml` すれば dispatch は弾かれる)  ただし向こうは延々とエラーを吐き続けるので、**PAT を revoke するのが一番確実**

---

## 5. Secrets の後始末 (判断材料)

現在 repo に登録されている Secrets と、それを使っている workflow:

| secret | 使っている workflow | 中身 | 撤収時の判断 |
|---|---|---|---|
| `SLACK_BOT_TOKEN` | notify / digest / enrich / announce / lineup / test-post / verify | この Slack App の bot token | **削除 or revoke 推奨**  ワークフローを誤って再有効化しても投稿できなくする第二の防壁になる  内定者イベントbot は**別ワークスペース想定なので流用しない** |
| `SLACK_WEBHOOK_URL` | notify / digest | Incoming Webhook | 同上  **削除推奨** |
| `SLACK_CHANNEL_ID` | notify / digest / enrich / announce / lineup / verify | チャンネル ID (機密性は低い) | 消しても消さなくてもよい  token を消せば無害 |
| `FOOTBALL_DATA_API_KEY` | notify / digest / enrich / pages / squads / test-post / verify | football-data.org の個人 API キー | **repo からは削除してよい**  ただし**キー自体は他プロジェクトで使い回せる資産**なので、football-data 側で revoke まではしない (削除 ≠ 失効) |
| `API_FOOTBALL_KEY` | squads / verify | API-Football の個人 API キー | 同上 |
| `YOUTUBE_API_KEY` | enrich | YouTube Data API v3 キー | 同上  **クォータを食うのはこれ**  enrich さえ止まれば消費はゼロになる |
| `GOOGLE_API_KEY` | notify / lineup-dryrun | Gemini (スタメン抽出) | 同上 |

**判断の指針**:
- **消す価値が高いのは Slack 系だけ** — 唯一「外に向かって書き込む」権限だから  workflow disable と二重に守る
- **API キー系は repo から消しても消さなくても実害は変わらない** (workflow が止まれば呼ばれない)  キーは個人資産なので **revoke はしない**のが得  転用先 (内定者イベントbot 等) で再利用する
- 最短で安全側に倒すなら: **Slack App をアーカイブする**  これ一発で bot token も webhook も死ぬ

```bash
gh secret list                      # 現状確認
gh secret delete SLACK_BOT_TOKEN    # 消す場合
gh secret delete SLACK_WEBHOOK_URL
```

---

## 6. 期間ガードはどこにあるか

| 場所 | 内容 |
|---|---|
| `src/main.py:34-35` | `TOURNAMENT_START_UTC` / `TOURNAMENT_END_UTC` (= 2026-07-21 UTC) → `is_notify_period()` |
| `src/main.py:226-228` | `is_digest_period()` (2026-06-11 〜 07-20 JST) |
| `src/main.py:580-588` | `main()` の冒頭で期間外なら **API 初期化前に return** する |
| `.github/workflows/announce.yml` | yml 内の heredoc に `if now.year != 2026: raise SystemExit` |
| `.github/workflows/*.yml` の cron | 月指定 `6,7` (= **年をまたぐと再発火する弱いガード**) |
| `scripts/build_*.py` の `TOURNAMENT_START` / `TOURNAMENT_END` | **実行ガードではなく取得日付レンジ**  期間外に呼ばれても素通りで走る (要注意) |

**守られているのは Slack 投稿 (notify / digest / announce) だけ**
`enrich` / `pages` / `squads` に実行ガードは無く、**`notify.yml` の "Hourly enrich dispatch" ステップも期間ガードの外にある**
→ これらを止めるには **workflow を disable するしかない**

---

## 7. Pages が詰まったときの復旧 (2026-07-09 に発生した実障害)

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

**再発防止** (2026-07-12 実装): `notify.yml` / `enrich.yml` / `squads.yml` の pages dispatch すべてに in-flight ガードを入れた
実行中/待機中の pages run がある間は dispatch せず、notify では 20分以上 pending の run があれば `::warning::` を出す
`pages.yml` の concurrency group は幽霊ロックを避けるため `pages` → `pages-deploy` に変更済み

---

## 8. その他の後片付け

- **予想アプリ (bolt_app)**: launchd の `com.wc2026.bolt.plist` は既に `.disabled`  常駐プロセスは無い
- **サイト**: GitHub Pages は静的で無料  記念に残してよい (止めるなら Settings → Pages → Unpublish)
- **転用**: 7/20 以降は内定者イベントbot (`~/内定者イベントbot`) への転用を検討  材料は `NEXT.md` の「転用の材料」
