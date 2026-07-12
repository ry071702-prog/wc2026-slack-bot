#!/usr/bin/env bash
# 大会終了 (2026-07-20) 後の撤収スクリプト
#
#   bash scripts/teardown.sh           # dry-run: 何を止めるか表示するだけ (既定)
#   bash scripts/teardown.sh --apply   # 実際に gh workflow disable する
#   bash scripts/teardown.sh --apply --all   # 手動専用の workflow も含めて全部止める
#
# gh workflow disable は cron と workflow_dispatch の両方を止める
# → 外部スケジューラからの dispatch も 403 で弾かれる (詳細は docs/teardown.md)
# 復活させたいときは: gh workflow enable <file>
set -euo pipefail

APPLY=0
ALL=0
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    --all) ALL=1 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 1 ;;
  esac
done

# cron / 自動 dispatch を持つ = 放置すると動き続けるもの (月指定が 6,7 なので 2027年にも再発火する)
SCHEDULED=(
  notify.yml   # cron */10 (6,7月) + 外部からの workflow_dispatch (5分毎)
  digest.yml   # cron 30 0 (6,7月)
  enrich.yml   # cron 15 1,7,13 (6,7月) + notify から毎時 dispatch  ※期間ガード無し
  pages.yml    # cron 0 21 / 0 9 (6,7月) + push + 他 workflow から dispatch  ※期間ガード無し
  announce.yml # cron 45 0 11 6 (6/11のみ)  本体に year!=2026 ガードあり
  squads.yml   # cron 10 0 11 6 (6/11のみ)  ※期間ガード無し
)
# 手動 (workflow_dispatch) 専用 = 放置しても勝手には動かない
MANUAL=(
  lineup.yml
  lineup-dryrun.yml
  test-post.yml
  verify.yml
)

targets=("${SCHEDULED[@]}")
if [ "$ALL" -eq 1 ]; then
  targets+=("${MANUAL[@]}")
fi

echo "== 撤収対象 =="
printf '  %s\n' "${targets[@]}"
echo

if [ "$APPLY" -eq 0 ]; then
  echo "[dry-run] 停止はしていない  実行するには --apply を付ける"
  echo
  echo "== 現在の状態 =="
  gh workflow list --all
  exit 0
fi

for wf in "${targets[@]}"; do
  if gh workflow disable "$wf"; then
    echo "disabled: $wf"
  else
    echo "::warning::failed to disable $wf" >&2
  fi
done

echo
echo "== 停止後の状態 (cron 系が disabled_manually になっていること) =="
gh workflow list --all
echo
echo "残タスク: 外部の5分毎ディスパッチャの停止 / Secrets のローテート判断 (docs/teardown.md の チェックリスト 参照)"
