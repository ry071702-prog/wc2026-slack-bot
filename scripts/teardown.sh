#!/usr/bin/env bash
# 大会終了 (2026-07-20) 後の撤収スクリプト
#
#   bash scripts/teardown.sh           # dry-run: 何を止めるか表示するだけ (既定)
#   bash scripts/teardown.sh --apply   # cron / 自動 dispatch を持つ workflow を止める
#   bash scripts/teardown.sh --apply --all   # GitHub 上の全 workflow を止める (手動専用も含む)
#
# gh workflow disable は cron と workflow_dispatch の両方を止める
# → 外部スケジューラからの dispatch も弾かれる (詳細は docs/teardown.md)
# 復活させたいときは: gh workflow enable <file>
#
# GitHub 上の実在 workflow と下のリストを毎回突き合わせ、どちらかにしか無いものを
# 警告する (workflow を足したのに撤収し忘れる事故を防ぐ)
# macOS の bash 3.2 で動くように書いてある (mapfile / 連想配列は使わない)
set -euo pipefail

APPLY=0
ALL=0
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    --all) ALL=1 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 1 ;;
  esac
done

command -v gh >/dev/null 2>&1 || { echo "error: gh が無い" >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "error: gh が未認証  gh auth login を先に実行する" >&2; exit 1; }

# cron / 自動 dispatch を持つ = 放置すると動き続ける
# (cron の月指定が 6,7 で「年」を指定できないため 2027年6〜7月に再発火する)
SCHEDULED='notify.yml
enrich.yml
pages.yml
squads.yml
digest.yml
announce.yml'

# 手動 (workflow_dispatch) 専用 = 放置しても勝手には動かない
# ただし test-post.yml / lineup.yml は手で叩くと Slack に投稿する (誤操作を封じたければ --all)
MANUAL='lineup.yml
lineup-dryrun.yml
test-post.yml
verify.yml'

# --- GitHub 上に実在する workflow を取得して突き合わせる ---
REMOTE=$(gh workflow list --all --json path --jq '.[].path | sub(".*/"; "")' | sort)
[ -n "$REMOTE" ] || { echo "error: gh workflow list が空  リポジトリ/権限を確認する" >&2; exit 1; }

KNOWN=$(printf '%s\n%s\n' "$SCHEDULED" "$MANUAL" | sort)

# GitHub にあるのに撤収リストに無い = 撤収漏れ予備軍
UNLISTED=$(printf '%s\n' "$REMOTE" | grep -vxF -f <(printf '%s\n' "$KNOWN") || true)
# 撤収リストにあるのに GitHub に無い = 消された workflow (リストが古い)
STALE=$(printf '%s\n' "$KNOWN" | grep -vxF -f <(printf '%s\n' "$REMOTE") || true)

if [ "$ALL" -eq 1 ]; then
  # --all は GitHub 上の全 workflow  リストのメンテ漏れに影響されない
  TARGETS="$REMOTE"
else
  # 既定は cron 系  素性不明 (未登録) のものも安全側に倒して含める
  TARGETS=$(printf '%s\n%s\n' "$SCHEDULED" "$UNLISTED" | grep -v '^$' | sort -u)
  # 消えた workflow は対象から外す
  if [ -n "$STALE" ]; then
    TARGETS=$(printf '%s\n' "$TARGETS" | grep -vxF -f <(printf '%s\n' "$STALE") || true)
  fi
fi

if [ -n "$UNLISTED$STALE" ]; then
  echo "== !! 撤収リストと GitHub のズレ !! =="
  printf '%s\n' "$UNLISTED" | grep -v '^$' | while read -r wf; do
    echo "  [未登録] $wf は GitHub にあるが撤収リストに無い"
    echo "           → 安全側に倒して停止対象に含めた  scripts/teardown.sh のリストに追記すること"
  done
  printf '%s\n' "$STALE" | grep -v '^$' | while read -r wf; do
    echo "  [消滅]   $wf はリストにあるが GitHub に無い → 対象から除外  リストから消してよい"
  done
  echo
fi

echo "== 停止する ($(printf '%s\n' "$TARGETS" | grep -c . | tr -d ' ')件) =="
printf '%s\n' "$TARGETS" | sed 's/^/  /'
echo

if [ "$ALL" -eq 0 ]; then
  NOT_STOPPED=$(printf '%s\n' "$MANUAL" | grep -vxF -f <(printf '%s\n' "$TARGETS") || true)
  if [ -n "$NOT_STOPPED" ]; then
    echo "== 停止しない (手動専用・勝手には動かない) =="
    printf '%s\n' "$NOT_STOPPED" | sed 's/^/  /'
    echo "  → test-post.yml / lineup.yml は手で叩けば Slack に投稿する  誤操作も封じたいなら --all"
    echo
  fi
fi

if [ "$APPLY" -eq 0 ]; then
  echo "[dry-run] 停止はしていない  実行するには --apply を付ける"
  echo
  echo "== 現在の状態 =="
  gh workflow list --all
  exit 0
fi

# --- 実行 ---
FAILED=""
for wf in $TARGETS; do
  if gh workflow disable "$wf" >/dev/null 2>&1; then
    echo "disabled: $wf"
  else
    echo "::warning::failed to disable $wf" >&2
    FAILED="$FAILED $wf"
  fi
done
echo

# --- 検証: 本当に止まったか GitHub に問い直す ---
echo "== 検証 =="
NG=""
for wf in $TARGETS; do
  state=$(gh workflow list --all --json path,state \
            --jq ".[] | select(.path | endswith(\"/$wf\")) | .state" 2>/dev/null || true)
  case "$state" in
    disabled_manually) ;;
    "") echo "  ?  $wf : 状態を取得できなかった"; NG="$NG $wf" ;;
    *)  echo "  NG $wf : state=$state (まだ止まっていない)"; NG="$NG $wf" ;;
  esac
done
[ -z "$NG$FAILED" ] && echo "  OK 停止対象はすべて disabled_manually になった"
echo

echo "== 停止後の状態 =="
gh workflow list --all
echo

cat <<'EOS'
== workflow を止めただけでは撤収は完了しない ==
  1. 外部の5分毎ディスパッチャを特定して止める
     notify.yml を repo 外の何かが5分毎に workflow_dispatch し続けている (actor=ry071702-prog)
     disable 後は弾かれるので実害は消えるが、向こうはエラーを吐き続ける
     手掛かり: 5分間隔 / PAT 経由 / cron-job.org・Zapier・GAS 等の外部サービスの線
     → docs/teardown.md 「5. 外部ディスパッチャ (要特定・要停止)」
  2. Secrets のローテート / 削除を判断する (gh secret list)
     → docs/teardown.md 「6. Secrets の後始末」
EOS

if [ -n "$NG$FAILED" ]; then
  echo
  echo "::error::停止しきれていない workflow がある  上の NG を確認する" >&2
  exit 1
fi
