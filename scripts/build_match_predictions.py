"""全試合の勝敗予想 (リアクション投票) を集計して data/match_predictions.json に保存する。

「まもなくキックオフ」通知 (src/main.py run_notify) が prematch メッセージに
ホーム国旗 / handshake / アウェイ国旗 の3リアクションを種付けし、その ts を
state/notified.json の prematch_poll ({match_id: ts}) に記録している。
本スクリプトは各 prematch メッセージの reactions.get を集計し、サイトの
試合詳細ページ (site/match.html) に「みんなの予想」として反映する。

ベストエフォート: 取得失敗・例外が出た試合はスキップし (次回実行で再試行)、
クラッシュしない。FINISHED の試合は集計後 final=true にし以降は再集計しない
(API 節約)。未確定/進行中の試合は毎回再集計してライブ更新する。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.flags import opponent_reaction
from src.providers.base import Match
from src.providers.football_data import FootballDataProvider
from src.slack import SlackBotClient
from src.state import StateStore

TOURNAMENT_START = date(2026, 6, 11)
TOURNAMENT_END = date(2026, 7, 20)
STATE_PATH = ROOT_DIR / "state" / "notified.json"
PREDICTIONS_PATH = ROOT_DIR / "data" / "match_predictions.json"
# 1実行あたりの reactions.get 呼び出し上限 (Slack レート制限と Action 時間の抑制)
MAX_REACTIONS_PER_RUN = 25

# reactions.get の戻り値を受け取り集計するコール可能 (ts -> レスポンス JSON or None)。
ReactionsGetter = Callable[[str], Optional[dict[str, Any]]]


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _reaction_count(by_name: dict[str, Any], name: str) -> int:
    """種リアクション名に対応する合計 count を返す。

    Slack は flag-es → es のように国旗ショートコードを2文字エイリアスへ正規化
    することがあるため、flag-xx は xx も合算して数える (src/main.py
    _reaction_entry と同じ吸収ロジック)。
    """
    candidates = {name}
    if name.startswith("flag-"):
        candidates.add(name[len("flag-"):])
    count = 0
    for candidate in candidates:
        found = by_name.get(candidate)
        if found:
            count += found.get("count", 0)
    return count


def aggregate_reactions(
    reactions: list[dict[str, Any]], home: str, away: str
) -> dict[str, int]:
    """reactions.get の reactions[] からホーム/引分/アウェイ票を集計する。

    各票は count から Bot の種リアクション1票を除外する (最低 0)。
    """
    by_name = {item.get("name"): item for item in reactions}
    home_name = opponent_reaction(home)
    away_name = opponent_reaction(away)
    draw_votes = max(0, _reaction_count(by_name, "handshake") - 1)
    if home_name == away_name:
        # 両チームとも国旗未マッピング (共に ⚽ にフォールバック) の防御。
        # 同じリアクションを home/away に二重計上しないよう、勝敗票は不可算とする。
        home_votes = away_votes = 0
    else:
        home_votes = max(0, _reaction_count(by_name, home_name) - 1)
        away_votes = max(0, _reaction_count(by_name, away_name) - 1)
    return {
        "home": home_votes,
        "draw": draw_votes,
        "away": away_votes,
        "total": home_votes + draw_votes + away_votes,
    }


def update_predictions(
    matches: list[Match],
    poll_map: dict[str, str],
    data: dict[str, Any],
    get_reactions: ReactionsGetter,
    limit: int = MAX_REACTIONS_PER_RUN,
) -> int:
    """prematch_poll の各試合を集計して data を更新する。更新件数を返す。

    - ts が空 (旧シードで未記録) の試合はスキップする。
    - 既に final=true の試合は再集計しない (API 節約)。
    - FINISHED の試合は集計後 final=true、それ以外は final=false (毎回再集計)。
    - reactions.get の呼び出しは limit 件まで。例外/取得失敗はスキップする。
    """
    matches_by_id = {str(match.id): match for match in matches}
    processed = 0
    for match_id, ts in poll_map.items():
        if processed >= limit:
            break
        if not ts:
            continue
        existing = data.get(match_id)
        if isinstance(existing, dict) and existing.get("final"):
            continue
        match = matches_by_id.get(match_id)
        if match is None:
            continue
        processed += 1
        try:
            response = get_reactions(ts)
        except Exception as error:  # noqa: BLE001 - ベストエフォート
            print(f"predictions error for {match_id}: {error}")
            continue
        if response is None:
            print(f"predictions: reactions.get returned nothing for {match_id}")
            continue
        reactions = (response.get("message") or {}).get("reactions") or []
        entry = aggregate_reactions(reactions, match.home, match.away)
        entry["final"] = match.status == "FINISHED"
        data[match_id] = entry
        print(
            f"predictions: {match.home} vs {match.away} -> "
            f"home={entry['home']} draw={entry['draw']} away={entry['away']} "
            f"(final={entry['final']})"
        )
    return processed


def main() -> None:
    football_key = os.environ.get("FOOTBALL_DATA_API_KEY", "")
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    channel = os.environ.get("SLACK_CHANNEL_ID", "")
    if not football_key:
        raise SystemExit("FOOTBALL_DATA_API_KEY is required")
    if not (token and channel):
        raise SystemExit("SLACK_BOT_TOKEN and SLACK_CHANNEL_ID are required")

    poll_map = StateStore(STATE_PATH).load()["prematch_poll"]
    if not poll_map:
        print("no prematch polls recorded; nothing to aggregate")
        return

    matches = FootballDataProvider(football_key).fetch_matches(
        TOURNAMENT_START, TOURNAMENT_END
    )
    client = SlackBotClient(token=token, channel=channel)
    data = load_json(PREDICTIONS_PATH)
    before = json.dumps(data, ensure_ascii=False, sort_keys=True)
    updated = update_predictions(matches, poll_map, data, client.get_reactions)
    after = json.dumps(data, ensure_ascii=False, sort_keys=True)
    if before != after:
        save_json(PREDICTIONS_PATH, data)
        print(f"match predictions saved ({updated} processed) -> {PREDICTIONS_PATH}")
    else:
        print("no match prediction changes")


if __name__ == "__main__":
    main()
