from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts import build_site_data
from src.providers.base import Match, MatchScore


def _schedule_entry(
    *,
    match_id: int,
    stage: str,
    kickoff_jst: str,
    home: str = "TBD",
    away: str = "TBD",
    status: str = "TIMED",
    score: dict | None = None,
    is_japan: bool = False,
) -> dict:
    return {
        "id": match_id,
        "kickoff_jst": kickoff_jst,
        "stage": stage,
        "home": home,
        "away": away,
        "home_ja": {"Japan": "日本", "Spain": "スペイン"}.get(home, home),
        "away_ja": {"Japan": "日本", "Spain": "スペイン"}.get(away, away),
        "status": status,
        "score": score,
        "is_japan": is_japan,
    }


def _static_bracket() -> dict:
    return {
        "rounds": ["LAST_32"],
        "matches": [
            {
                "match_no": 73,
                "stage": "LAST_32",
                "venue": "SoFi Stadium",
                "city_ja": "ロサンゼルス",
                "home": {"type": "group", "label": "A組 2位"},
                "away": {"type": "group", "label": "B組 2位"},
            },
            {
                "match_no": 74,
                "stage": "LAST_32",
                "venue": "Gillette Stadium",
                "city_ja": "ボストン",
                "home": {"type": "group", "label": "E組 1位"},
                "away": {"type": "third", "label": "3位(A/B/C/D/F組)"},
            },
        ],
    }


def test_build_bracket_overlays_live_results_in_kickoff_order() -> None:
    # ライブの2試合をキックオフ昇順で match_no 73, 74 に対応付ける
    schedule = [
        _schedule_entry(
            match_id=900,
            stage="LAST_32",
            kickoff_jst="2026-06-30T05:00:00+09:00",
            home="Japan",
            away="Spain",
            status="FINISHED",
            score={
                "home": 2,
                "away": 1,
                "duration": "REGULAR",
                "penalties_home": None,
                "penalties_away": None,
            },
            is_japan=True,
        ),
        _schedule_entry(
            match_id=901,
            stage="LAST_32",
            kickoff_jst="2026-06-29T04:00:00+09:00",
        ),
    ]

    result = build_site_data.build_bracket(schedule, _static_bracket())
    by_no = {node["match_no"]: node for node in result["matches"]}

    # 先にキックオフする 901 (TBD) が M73、後の 900 (確定) が M74
    assert by_no[73]["fd_id"] == 901
    assert by_no[73]["home_team"] is None  # TBD はスロット表記にフォールバック
    assert by_no[73]["away_team"] is None
    assert by_no[73]["venue"] == "SoFi Stadium"  # 静的な会場は常に保持

    assert by_no[74]["fd_id"] == 900
    assert by_no[74]["home_team"] == "Japan"
    assert by_no[74]["home_ja"] == "日本"
    assert by_no[74]["away_team"] == "Spain"
    assert by_no[74]["score"]["home"] == 2
    assert by_no[74]["is_japan"] is True


def test_build_bracket_maps_by_official_kickoff_not_match_no() -> None:
    """静的スロットに公式 kickoff_jst がある場合、ライブ試合は match_no 順ではなく
    キックオフ時刻順で対応付けられる。FIFA の match番号はキックオフ順ではないため
    (例: ブラジル×日本=M76 だが時刻は早い)、これが無いと別スロットに乗ってしまう。"""
    static = {
        "rounds": ["LAST_32"],
        "matches": [
            {
                "match_no": 74,  # 公式は遅い時刻 (5:30)
                "stage": "LAST_32",
                "venue": "Gillette Stadium",
                "kickoff_jst": "2026-06-30T05:30:00+09:00",
                "home": {"type": "group", "label": "E組 1位"},
                "away": {"type": "third", "label": "3位(A/B/C/D/F組)"},
            },
            {
                "match_no": 76,  # 公式は早い時刻 (2:00)
                "stage": "LAST_32",
                "venue": "NRG Stadium",
                "kickoff_jst": "2026-06-30T02:00:00+09:00",
                "home": {"type": "group", "label": "C組 1位"},
                "away": {"type": "group", "label": "F組 2位"},
            },
        ],
    }
    schedule = [
        _schedule_entry(
            match_id=823,
            stage="LAST_32",
            kickoff_jst="2026-06-30T02:00:00+09:00",  # 早い → M76 に乗るべき
            home="Brazil",
            away="Japan",
            is_japan=True,
        ),
        _schedule_entry(
            match_id=815,
            stage="LAST_32",
            kickoff_jst="2026-06-30T05:30:00+09:00",  # 遅い → M74 に乗るべき
            home="Germany",
            away="Paraguay",
        ),
    ]

    result = build_site_data.build_bracket(schedule, static)
    by_no = {node["match_no"]: node for node in result["matches"]}

    # 早いキックオフの ブラジル×日本 は M76、遅い ドイツ×パラグアイ は M74
    assert by_no[76]["home_team"] == "Brazil"
    assert by_no[76]["away_team"] == "Japan"
    assert by_no[76]["fd_id"] == 823
    assert by_no[74]["home_team"] == "Germany"
    assert by_no[74]["fd_id"] == 815
    # 出力は match_no 昇順で安定
    assert [n["match_no"] for n in result["matches"]] == [74, 76]


def test_build_bracket_without_live_keeps_static_slots() -> None:
    result = build_site_data.build_bracket([], _static_bracket())

    assert [node["match_no"] for node in result["matches"]] == [73, 74]
    for node in result["matches"]:
        assert "fd_id" not in node
        assert node["home"]["label"]  # スロット表記は維持
        assert node["venue"]


def test_generate_site_data_writes_full_bracket(tmp_path: Path) -> None:
    # 実 data/bracket.json (32試合) を使って site/data/bracket.json を出力する
    group_match = Match(
        id=1001,
        utc_kickoff=datetime(2026, 6, 21, 4, 0, tzinfo=timezone.utc),
        home="Tunisia",
        away="Japan",
        stage="GROUP_STAGE",
        group="GROUP_F",
        matchday=2,
        status="FINISHED",
        score=MatchScore(
            home=1,
            away=2,
            duration="REGULAR",
            penalties_home=None,
            penalties_away=None,
        ),
    )
    output_dir = tmp_path / "site-data"

    build_site_data.generate_site_data(
        [group_match],
        rankings_path=tmp_path / "missing-rankings.json",
        squads_path=tmp_path / "missing-squads.json",
        output_dir=output_dir,
    )

    bracket = json.loads(
        (output_dir / "bracket.json").read_text(encoding="utf-8")
    )
    assert len(bracket["matches"]) == 32
    # グループ戦しか無いので決勝Tはライブ未対応 (会場・スロットのみ)
    assert all(node.get("venue") for node in bracket["matches"])
    assert all("fd_id" not in node for node in bracket["matches"])
    finals = [n for n in bracket["matches"] if n["stage"] == "FINAL"]
    assert len(finals) == 1
    assert finals[0]["venue"] == "MetLife Stadium"
