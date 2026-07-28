# wc2026-slack-bot — 進捗ボード
<!-- statusline / session-start / /board がこのファイルを読みます。自由に編集してOK。 -->

## 状態
撤収ほぼ完了 (**workflow 全停止済 + cron 全撤去済**  残りは PAT revoke と Slack Token 無効化の2点)

## いま
大会終了 (決勝 7/20)  撤収は実行済み: 全10 workflow が `disabled_manually` (7/22)、外部ディスパッチャの発火も workflow 無効化により 7/22 14:50 JST で停止 (無効化された workflow は dispatch を受け付けない)
さらに第二の防壁として **全6本の cron を schedule ごと撤去** (d9e18a1, 2026-07-23)  誰かが workflow を再有効化しても 2027年に再発火しない

## 次にやること
- [ ] **外部ディスパッチャの PAT を revoke** — 発火自体は止まっているが発生源の PAT は生きている可能性  github.com/settings/tokens で「最終使用 7/22」のトークンを探して revoke すれば完全決着 (`docs/teardown.md` の 4)  ※全repo横断のコード検索でも dispatch 元は見つからず (2026-07-27)  ローカル/repo外の PAT 利用が濃厚
- [x] **Slack Secrets の削除** (確認 2026-07-27) — `SLACK_BOT_TOKEN` / `SLACK_WEBHOOK_URL` は repo Secrets から削除済み  誤って再有効化しても投稿不能  Slack App 自体のアーカイブ (`docs/teardown.md` の 5) は任意の仕上げ
- [ ] 内定者イベントbot (`~/内定者イベントbot`) への転用方針を決める (材料は下記「転用の材料」)

### 止め忘れると何が起きるか (要点  ※cron は d9e18a1 で全撤去済み・以下は経緯の記録)
cron の月指定が `6,7` で「年」を指定できないため、**放置すると 2027年6〜7月に再発火する** (→ 撤去で解消)
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
