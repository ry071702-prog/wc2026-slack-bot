from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from scripts import build_match_predictions as bmp
from src.providers.base import Match, MatchScore


def make_match(
    match_id: int,
    *,
    home: str = "Spain",
    away: str = "Saudi Arabia",
    status: str = "FINISHED",
) -> Match:
    return Match(
        id=match_id,
        utc_kickoff=datetime(2026, 6, 21, 3, 0, tzinfo=timezone.utc),
        home=home,
        away=away,
        stage="GROUP_STAGE",
        group="GROUP_H",
        matchday=1,
        status=status,
        score=MatchScore(),
    )


def reactions_response(reactions: list[dict[str, Any]]) -> dict[str, Any]:
    return {"ok": True, "message": {"reactions": reactions}}


# ---- aggregate_reactions --------------------------------------------------


def test_aggregate_reactions_counts_votes_minus_seed() -> None:
    # Bot の種リアクション1票を除外して数える (count - 1, 最低0)
    reactions = [
        {"name": "flag-es", "count": 5},  # home = Spain
        {"name": "handshake", "count": 4},
        {"name": "flag-sa", "count": 3},  # away = Saudi Arabia
    ]
    result = bmp.aggregate_reactions(reactions, "Spain", "Saudi Arabia")
    assert result == {"home": 4, "draw": 3, "away": 2, "total": 9}


def test_aggregate_reactions_floor_at_zero() -> None:
    # 種すら無い (count 0) / 種だけ (count 1) は 0 票
    reactions = [{"name": "handshake", "count": 1}]
    result = bmp.aggregate_reactions(reactions, "Spain", "Saudi Arabia")
    assert result == {"home": 0, "draw": 0, "away": 0, "total": 0}


def test_aggregate_reactions_handles_slack_flag_canonicalization() -> None:
    # Slack が flag-es を es に正規化しても home(スペイン)票を正しく数える
    reactions = [
        {"name": "es", "count": 7},  # flag-es の正規化形
        {"name": "handshake", "count": 2},
        {"name": "flag-sa", "count": 4},
    ]
    result = bmp.aggregate_reactions(reactions, "Spain", "Saudi Arabia")
    assert result["home"] == 6  # 7 - 1
    assert result["draw"] == 1  # 2 - 1
    assert result["away"] == 3  # 4 - 1
    assert result["total"] == 10


def test_aggregate_reactions_sums_flag_and_canonical() -> None:
    # flag-es と es が両方ある場合は合算する
    reactions = [
        {"name": "flag-es", "count": 2},
        {"name": "es", "count": 3},
    ]
    result = bmp.aggregate_reactions(reactions, "Spain", "Saudi Arabia")
    assert result["home"] == 4  # (2 + 3) - 1


# ---- update_predictions ---------------------------------------------------


def test_update_predictions_finished_sets_final() -> None:
    matches = [make_match(101, status="FINISHED")]
    poll_map = {"101": "ts-101"}
    data: dict[str, Any] = {}

    def getter(ts: str) -> Optional[dict[str, Any]]:
        return reactions_response(
            [
                {"name": "flag-es", "count": 5},
                {"name": "handshake", "count": 2},
                {"name": "flag-sa", "count": 3},
            ]
        )

    updated = bmp.update_predictions(matches, poll_map, data, getter)

    assert updated == 1
    assert data["101"] == {
        "home": 4,
        "draw": 1,
        "away": 2,
        "total": 7,
        "final": True,
    }


def test_update_predictions_live_match_not_final() -> None:
    matches = [make_match(102, status="IN_PLAY")]
    poll_map = {"102": "ts-102"}
    data: dict[str, Any] = {}

    bmp.update_predictions(
        matches,
        poll_map,
        data,
        lambda ts: reactions_response([{"name": "flag-es", "count": 3}]),
    )

    assert data["102"]["final"] is False
    assert data["102"]["home"] == 2


def test_update_predictions_skips_already_final() -> None:
    matches = [make_match(103, status="FINISHED")]
    poll_map = {"103": "ts-103"}
    data: dict[str, Any] = {
        "103": {"home": 1, "draw": 1, "away": 1, "total": 3, "final": True}
    }
    calls: list[str] = []

    def getter(ts: str) -> Optional[dict[str, Any]]:
        calls.append(ts)
        return reactions_response([])

    updated = bmp.update_predictions(matches, poll_map, data, getter)

    # final 済みは reactions.get を呼ばず、データも変えない
    assert calls == []
    assert updated == 0
    assert data["103"]["total"] == 3


def test_update_predictions_re_aggregates_non_final() -> None:
    # 以前 final=False で集計済みの試合は毎回再集計する (ライブ更新)
    matches = [make_match(104, status="IN_PLAY")]
    poll_map = {"104": "ts-104"}
    data: dict[str, Any] = {
        "104": {"home": 1, "draw": 0, "away": 0, "total": 1, "final": False}
    }

    bmp.update_predictions(
        matches,
        poll_map,
        data,
        lambda ts: reactions_response([{"name": "flag-es", "count": 6}]),
    )

    assert data["104"]["home"] == 5  # 再集計された


def test_update_predictions_skips_empty_ts() -> None:
    # ts が空 (旧シードで未記録) の試合は集計対象外
    matches = [make_match(105)]
    poll_map = {"105": ""}
    data: dict[str, Any] = {}
    calls: list[str] = []

    bmp.update_predictions(
        matches, poll_map, data, lambda ts: calls.append(ts) or reactions_response([])
    )

    assert calls == []
    assert data == {}


def test_update_predictions_skips_unknown_match() -> None:
    # poll_map に schedule に存在しない試合 ID があってもスキップする
    matches = [make_match(106)]
    poll_map = {"999": "ts-999"}
    data: dict[str, Any] = {}
    calls: list[str] = []

    bmp.update_predictions(
        matches, poll_map, data, lambda ts: calls.append(ts) or reactions_response([])
    )

    assert calls == []
    assert data == {}


def test_update_predictions_skips_on_exception() -> None:
    matches = [make_match(201), make_match(202)]
    poll_map = {"201": "ts-201", "202": "ts-202"}
    data: dict[str, Any] = {}

    def getter(ts: str) -> Optional[dict[str, Any]]:
        if ts == "ts-201":
            raise RuntimeError("boom")
        return reactions_response([{"name": "flag-es", "count": 4}])

    # 例外はスキップしてクラッシュしない
    updated = bmp.update_predictions(matches, poll_map, data, getter)

    assert "201" not in data  # 例外側はスキップ
    assert data["202"]["home"] == 3
    # processed は reactions.get の呼び出し回数 (例外含む)
    assert updated == 2


def test_update_predictions_skips_on_none_response() -> None:
    matches = [make_match(203)]
    poll_map = {"203": "ts-203"}
    data: dict[str, Any] = {}

    updated = bmp.update_predictions(matches, poll_map, data, lambda ts: None)

    assert data == {}  # 取得失敗はスキップ (次回再試行)
    assert updated == 1  # 呼び出しはカウントされる


def test_update_predictions_respects_limit() -> None:
    matches = [make_match(300 + i) for i in range(30)]
    poll_map = {str(300 + i): f"ts-{i}" for i in range(30)}
    data: dict[str, Any] = {}
    calls: list[str] = []

    def getter(ts: str) -> Optional[dict[str, Any]]:
        calls.append(ts)
        return reactions_response([{"name": "flag-es", "count": 2}])

    updated = bmp.update_predictions(matches, poll_map, data, getter, limit=25)

    assert updated == 25
    assert len(calls) == 25
    assert len(data) == 25


# ---- I/O ------------------------------------------------------------------


def test_load_json_missing_returns_empty(tmp_path: Path) -> None:
    assert bmp.load_json(tmp_path / "nope.json") == {}


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "match_predictions.json"
    payload = {"101": {"home": 4, "draw": 1, "away": 2, "total": 7, "final": True}}
    bmp.save_json(path, payload)
    assert json.loads(path.read_text(encoding="utf-8")) == payload
