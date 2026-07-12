# wc2026-slack-bot — 進捗ボード
<!-- statusline / session-start / /board がこのファイルを読みます。自由に編集してOK。 -->

## 状態
進行中 (決勝T本番中・**撤収の用意は完了  実行は 7/20 以降**)

## いま
決勝トーナメント本番中 (決勝 = 7/20 04:00 JST、3位決定戦 = 7/19 06:00 JST)  日本は R32 敗退済み (6/29 Brazil 2-1 Japan) のため日本戦演出・スタメン自動投稿はもう発火しない
Actions は全系統 (notify / digest / enrich / pages) が正常稼働に復帰  Pages の3日間停止 (7/09〜7/12) は復旧済みで、サイトも最新に追いついている
**撤収は「用意だけ」完了した状態**  ワークフローはまだ1本も止めていない (大会運用中のため意図的)  実行は 7/20 の決勝後

## 次にやること
- [ ] **[期限 7/20 決勝後] 撤収を実行する** — `docs/teardown.md` の「1. 7/20 当日にやること」を上から順に実行するだけ  中核は `bash scripts/teardown.sh --apply` (dry-run で確認 → apply → 自動検証で `OK` が出れば完了)
- [ ] **[撤収に必須] 外部ディスパッチャの特定と停止** — notify.yml が cron とは別に **5分毎に workflow_dispatch されている** (actor=ry071702-prog)  repo 内・launchd・crontab のいずれにも該当なし  **PAT の「最終使用日時が数分前」のトークンを探して revoke するのが最短** (`docs/teardown.md` の 4)
- [ ] **[撤収に必須] Slack Bot Token の無効化** — workflow を誤って再有効化しても投稿できなくする第二の防壁  Slack App のアーカイブ一発が最短 (`docs/teardown.md` の 5)
- [ ] 7/20 以降の内定者イベントbot (`~/内定者イベントbot`) への転用方針を決める (材料は下記「転用の材料」)

### 止め忘れると何が起きるか (要点)
cron の月指定が `6,7` で「年」を指定できないため、**放置すると 2027年6〜7月に再発火する**
期間ガードが守るのは **Slack 投稿 (notify / digest / announce) だけ**  誤投稿は起きないが、
**notify の "Hourly enrich dispatch" ステップは期間ガードの外**にあり、notify を止めないと **enrich (ガード無し) が毎時走り続ける** → YouTube クォータ消費 / Slack 読み取り / `data/` へのゴミコミット / pages 再デプロイ
→ 詳細な影響表は `docs/teardown.md` の 2

## 完了 (直近)
- [x] **撤収の用意を完成** (2026-07-12) — `scripts/teardown.sh` を GitHub 上の実在 workflow と突き合わせる方式に改修 (リストに無い workflow は警告した上で安全側に倒して停止対象に含める / `--apply` 後に自動検証して止め残しがあれば exit 1 / bash 3.2 互換)  `docs/teardown.md` に「7/20 当日のチェックリスト」「workflow 別の止め忘れ影響」「外部ディスパッチャの追跡手順」「Secrets の判断材料」を追加  dry-run 検証済み (10 workflow 全数カバー確認)
- [x] Pages 詰まりの復旧 — `github-pages` 環境に `waiting` で残ったデプロイを inactive 化して環境ロックを解除  直近の pages run は全 success でサイトも最新 (2026-07-12)
- [x] Pages デプロイ停止の原因特定 + 再発防止 — notify / enrich / squads の pages dispatch すべてに in-flight ガードを追加  concurrency group も `pages` → `pages-deploy` に変更して幽霊ロックから脱出 (2026-07-12)
- [x] Actions 稼働実態の確認 — notify (5分毎) / digest (日次) / enrich (毎時) は直近 100 run で失敗ゼロ (2026-07-12)
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
