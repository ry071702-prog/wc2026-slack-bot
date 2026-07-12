# wc2026-slack-bot — 進捗ボード
<!-- statusline / session-start / /board がこのファイルを読みます。自由に編集してOK。 -->

## 状態
進行中 (決勝T本番中・撤収準備)

## いま
決勝トーナメント本番中 (決勝 = 7/20 04:00 JST、3位決定戦 = 7/19 06:00 JST)  日本は R32 敗退済み (6/29 Brazil 2-1 Japan) のため日本戦演出・スタメン自動投稿はもう発火しない
Actions の通知系 (notify / digest / enrich) は直近まで全 run success で、Slack 投稿・state コミットとも正常
**ただし GitHub Pages のデプロイが 2026-07-09 12:23 UTC から停止している** (特設サイトが3日分古い)  原因は特定済み・再発防止コードは投入済み・復旧は手動オペ待ち (下記)

## 次にやること
- [ ] **[要オペ・最優先] Pages 詰まりの復旧** — `github-pages` 環境に `waiting` のまま残ったデプロイ (id=5376495428 / 2026-07-09T13:08:56Z) が環境をロックし、以後の pages run が全て pending → cancelled  手順は `docs/teardown.md` の「4. Pages が詰まったときの復旧」  復旧しないと決勝までサイトが古いままになる
- [ ] **[要確認] 外部ディスパッチャの特定** — notify.yml が cron とは別に **5分毎に workflow_dispatch されている** (actor=ry071702-prog)  repo 内・launchd・crontab に該当なし  撤収時に止める必要あり (`docs/teardown.md` の 5)
- [ ] 7/20 の決勝後に撤収 — `bash scripts/teardown.sh --apply` (手順・チェックリストは `docs/teardown.md`)
- [ ] 7/20 以降の内定者イベントbot (`~/内定者イベントbot`) への転用方針を決める (材料は下記「転用の材料」)

## 完了 (直近)
- [x] Actions 稼働実態の確認 — notify (5分毎) / digest (日次) / enrich (毎時) は直近 100 run で失敗ゼロ  pages のみ全滅 (2026-07-12)
- [x] Pages デプロイ停止の原因特定 + 再発防止 — notify.yml の "Trigger site rebuild" に in-flight ガードを追加  実行中/待機中の pages run がある間は dispatch せず、20分以上 pending なら `::warning::` を出す (2026-07-12)
- [x] 撤収手順の明文化 — `docs/teardown.md` + `scripts/teardown.sh` (dry-run 既定・`--apply` で `gh workflow disable`) を追加 (2026-07-12)
- [x] 決勝T表示の実データ検証 — 組順位シード (12組48チーム)・勝ち上がり文言・FIFAランク・勝率予想バーが実データで正しいことを確認  未確定カード (TBD) はバー非表示で degrade する (2026-07-12、343テスト pass)
- [x] 決勝T向けに結果通知へ勝ち上がり文言・FIFAランク・組順位を付与し、日本突破の特別演出を追加 (2026-06-23)
- [x] サイトの試合カードに FIFAランク差ベースの勝率予想バーを表示、rankings.json を出力
- [x] トーナメント表ページを追加しメイン導線化、左右対称ツリー化・スマホ最適化

## 転用の材料 (7/20 以降・内定者イベントbot 向け)
判断はユーザー  ここは材料の整理のみ

- **そのまま流用可**
  - Actions cron 基盤 (`notify.yml` の骨格: checkout → setup-python → 実行 → state を repo にコミット)  ephemeral な runner で状態を持つための「state を git にコミットする」パターン
  - `concurrency` グループで多重起動を防ぐ形 / `vars` で `DRY_RUN` を切れる運用
  - 副作用 dispatch の作法 (リトライ + 失敗しても本体ジョブを落とさない + **in-flight ガード** ← 今回の教訓)
  - `bolt_app/storage.py` の `GitHubStore` (SQLite が置けない常駐環境で JSON を GitHub API 経由で永続化する層)
- **概念のみ流用 (コードは内定者bot 側に既にある)**
  - Slack 送信層: wc2026 は `requests` 直叩き (`src/slack.py`)、内定者bot は Bolt + WebClient  移植価値があるのは blocks 組み立て・`fallback_text`・リアクション付与のリトライ実装
  - 通知の冪等性: `state/notified.json` で「送信済み ID」を持つ考え方 → 内定者bot は SQLite で同等のことをしている
- **作り直し / 転用不可 (W杯ドメイン固有)**
  - `src/providers/` (football-data.org)、`src/standings.py`、`src/messages.py`、`src/flags.py`
  - `scripts/build_*` (highlights / news / stats / facts / matchups / lineup)、`site/` 一式、`bracket.json`
- **運用面の論点 (要決定)**
  - 内定者bot は Socket Mode = 常駐が要る  cron を Actions に置く (wc2026 踏襲) のか、常駐ホスト側 (launchd/systemd) に寄せるのかで state 永続化の設計が変わる
  - Slack App / トークンは別ワークスペース想定のため新規発行  流用できるのは manifest の書式のみ
