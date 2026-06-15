from __future__ import annotations

from dataclasses import replace
from typing import Any, Optional

from scripts import build_match_stats
from src.providers.base import Match, MatchScore


# --- 数値化 / stat マッピング --------------------------------------------------


def test_to_number_parses_float_int_and_messy_values() -> None:
    assert build_match_stats.to_number("61.1", float) == 61.1
    assert build_match_stats.to_number("13", int) == 13
    assert build_match_stats.to_number("1,234", int) == 1234
    assert build_match_stats.to_number("55%", int) == 55
    assert build_match_stats.to_number("", int) is None
    assert build_match_stats.to_number(None, int) is None
    assert build_match_stats.to_number("n/a", int) is None


def test_extract_team_stats_maps_names_and_ignores_unknown() -> None:
    statistics = [
        {"name": "possessionPct", "displayValue": "61.1", "value": None},
        {"name": "totalShots", "displayValue": "13", "value": None},
        {"name": "shotsOnTarget", "displayValue": "4", "value": None},
        {"name": "accuratePasses", "displayValue": "310", "value": None},
        {"name": "totalPasses", "displayValue": "421", "value": None},
        {"name": "wonCorners", "displayValue": "9", "value": None},
        {"name": "foulsCommitted", "displayValue": "10", "value": None},
        {"name": "yellowCards", "displayValue": "2", "value": None},
        {"name": "redCards", "displayValue": "0", "value": None},
        {"name": "offsides", "displayValue": "1", "value": None},
        {"name": "saves", "displayValue": "2", "value": None},
        # 出力対象外の項目は無視される
        {"name": "shotPct", "displayValue": "0.3", "value": None},
        {"name": "interceptions", "displayValue": "4", "value": None},
    ]

    stats = build_match_stats.extract_team_stats(statistics)

    assert stats == {
        "possession": 61.1,
        "shots": 13,
        "shots_on_target": 4,
        "passes_accurate": 310,
        "passes": 421,
        "corners": 9,
        "fouls": 10,
        "yellow": 2,
        "red": 0,
        "offsides": 1,
        "saves": 2,
    }


def boxscore(home_name: str, away_name: str) -> dict[str, Any]:
    """teams[] の順序は ESPN 任せ (homeAway とは無関係に displayName で対応付ける)。"""
    return {
        "teams": [
            {
                "team": {"displayName": home_name},
                "homeAway": "home",
                "statistics": [
                    {"name": "possessionPct", "displayValue": "61.1"},
                    {"name": "totalShots", "displayValue": "13"},
                ],
            },
            {
                "team": {"displayName": away_name},
                "homeAway": "away",
                "statistics": [
                    {"name": "possessionPct", "displayValue": "38.9"},
                    {"name": "totalShots", "displayValue": "8"},
                ],
            },
        ]
    }


def test_parse_boxscore_maps_by_display_name() -> None:
    parsed = build_match_stats.parse_boxscore(
        boxscore("Canada", "Bosnia-Herzegovina"),
        home="Canada",
        away="Bosnia-Herzegovina",
    )

    assert parsed["home"]["possession"] == 61.1
    assert parsed["home"]["shots"] == 13
    assert parsed["away"]["possession"] == 38.9
    assert parsed["away"]["shots"] == 8


def test_parse_boxscore_handles_reversed_home_away() -> None:
    # ESPN の teams[] は Bosnia(home扱い) が先でも、schedule の home=Canada に
    # displayName で正しく対応付ける (順序/homeAway に依存しない)。
    espn_boxscore = {
        "teams": [
            {
                "team": {"displayName": "Bosnia-Herzegovina"},
                "homeAway": "home",
                "statistics": [{"name": "totalShots", "displayValue": "8"}],
            },
            {
                "team": {"displayName": "Canada"},
                "homeAway": "away",
                "statistics": [{"name": "totalShots", "displayValue": "13"}],
            },
        ]
    }

    parsed = build_match_stats.parse_boxscore(
        espn_boxscore, home="Canada", away="Bosnia-Herzegovina"
    )

    # schedule の home=Canada なので Canada のシュート 13 が home に入る
    assert parsed["home"]["shots"] == 13
    assert parsed["away"]["shots"] == 8


def test_parse_boxscore_uses_aliases() -> None:
    parsed = build_match_stats.parse_boxscore(
        boxscore("Türkiye", "South Korea"),
        home="Turkey",
        away="Korea Republic",
    )

    assert parsed["home"]["shots"] == 13
    assert parsed["away"]["shots"] == 8


# --- チーム名マッチ / event 特定 ----------------------------------------------


def test_team_matches_handles_aliases() -> None:
    assert build_match_stats.team_matches("Türkiye", "Turkey")
    assert build_match_stats.team_matches("South Korea", "Korea Republic")
    assert build_match_stats.team_matches("IR Iran", "Iran")
    assert build_match_stats.team_matches("Côte d'Ivoire", "Ivory Coast")
    assert build_match_stats.team_matches("United States", "USA")
    assert not build_match_stats.team_matches("South Korea", "South Africa")


def espn_event(event_id: str, home: str, away: str) -> dict[str, Any]:
    return {
        "id": event_id,
        "competitions": [
            {
                "competitors": [
                    {"homeAway": "home", "team": {"displayName": home}},
                    {"homeAway": "away", "team": {"displayName": away}},
                ]
            }
        ],
    }


def test_find_espn_event_matches_both_teams_any_order() -> None:
    events = [
        espn_event("999", "Mexico", "South Africa"),
        espn_event("760416", "Bosnia-Herzegovina", "Canada"),
    ]

    # schedule の home=Canada / away=Bosnia でも順不同で拾える
    found = build_match_stats.find_espn_event(
        events, "Canada", "Bosnia-Herzegovina"
    )
    assert found is not None and found["id"] == "760416"


def test_find_espn_event_requires_both_teams() -> None:
    events = [espn_event("999", "Mexico", "South Africa")]

    assert build_match_stats.find_espn_event(events, "Mexico", "Canada") is None


def test_candidate_days_includes_previous_day(japan_match: Match) -> None:
    days = build_match_stats.candidate_days(japan_match)

    assert [day.isoformat() for day in days] == ["2026-06-21", "2026-06-20"]


# --- 取得フロー (ネットワークはモック) ----------------------------------------


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeSession:
    def __init__(
        self,
        events_by_day: dict[str, list[dict[str, Any]]],
        summary: Optional[dict[str, Any]] = None,
        raise_on: Optional[str] = None,
    ) -> None:
        self.events_by_day = events_by_day
        self.summary = summary or {}
        self.raise_on = raise_on
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        if self.raise_on and self.raise_on in url:
            raise RuntimeError("boom")
        if url == build_match_stats.SCOREBOARD_URL:
            day = kwargs["params"]["dates"]
            return FakeResponse({"events": self.events_by_day.get(day, [])})
        if url == build_match_stats.SUMMARY_URL:
            return FakeResponse(self.summary)
        raise AssertionError(f"unexpected url: {url}")


def finished(match: Match, home: int = 1, away: int = 2) -> Match:
    return replace(
        match, status="FINISHED", score=MatchScore(home=home, away=away)
    )


def test_update_match_stats_registers_entry(japan_match: Match) -> None:
    session = FakeSession(
        events_by_day={
            "20260621": [espn_event("770", "Tunisia", "Japan")],
        },
        summary={"boxscore": boxscore("Tunisia", "Japan")},
    )
    data: dict[str, Any] = {}

    updated = build_match_stats.update_match_stats(
        [finished(japan_match)], data, session  # type: ignore[arg-type]
    )

    assert updated == 1
    entry = data["1"]
    assert entry["source"] == "espn"
    assert entry["home"]["possession"] == 61.1
    assert entry["away"]["shots"] == 8


def test_update_match_stats_skips_registered(japan_match: Match) -> None:
    session = FakeSession(events_by_day={})
    data: dict[str, Any] = {"1": {"home": {}, "away": {}, "source": "espn"}}

    updated = build_match_stats.update_match_stats(
        [finished(japan_match)], data, session  # type: ignore[arg-type]
    )

    assert updated == 0
    assert session.calls == []


def test_update_match_stats_skips_unfinished_and_no_score(
    japan_match: Match,
) -> None:
    timed = japan_match  # status TIMED, score empty
    no_score = replace(japan_match, status="FINISHED", score=MatchScore())
    session = FakeSession(events_by_day={})
    data: dict[str, Any] = {}

    updated = build_match_stats.update_match_stats(
        [timed, no_score], data, session  # type: ignore[arg-type]
    )

    assert updated == 0
    assert session.calls == []


def test_update_match_stats_retry_when_event_missing(
    japan_match: Match,
) -> None:
    session = FakeSession(events_by_day={"20260621": [], "20260620": []})
    data: dict[str, Any] = {}

    updated = build_match_stats.update_match_stats(
        [finished(japan_match)], data, session  # type: ignore[arg-type]
    )

    assert updated == 0
    assert "1" not in data  # 次回再試行 (not_found を書かない)


def test_update_match_stats_skips_on_exception(japan_match: Match) -> None:
    session = FakeSession(
        events_by_day={"20260621": [espn_event("770", "Tunisia", "Japan")]},
        raise_on="scoreboard",
    )
    data: dict[str, Any] = {}

    # 例外が出てもクラッシュせずスキップする
    updated = build_match_stats.update_match_stats(
        [finished(japan_match)], data, session  # type: ignore[arg-type]
    )

    assert updated == 0
    assert "1" not in data


def test_update_match_stats_respects_limit(regular_match: Match) -> None:
    matches = [
        finished(replace(regular_match, id=index)) for index in range(5)
    ]
    session = FakeSession(events_by_day={})  # 全試合 event 無し

    build_match_stats.update_match_stats(
        matches, data := {}, session, limit=2  # type: ignore[arg-type]
    )

    # limit=2 なので scoreboard 取得は最大 2 試合分 (各2日) = 4 回まで
    scoreboard_calls = [
        call
        for call in session.calls
        if call["url"] == build_match_stats.SCOREBOARD_URL
    ]
    assert len(scoreboard_calls) <= 4
    assert data == {}


def test_update_match_stats_sends_user_agent(japan_match: Match) -> None:
    session = FakeSession(
        events_by_day={"20260621": [espn_event("770", "Tunisia", "Japan")]},
        summary={"boxscore": boxscore("Tunisia", "Japan")},
    )

    build_match_stats.update_match_stats(
        [finished(japan_match)], {}, session  # type: ignore[arg-type]
    )

    assert all(
        call.get("headers", {}).get("User-Agent") == "Mozilla/5.0"
        for call in session.calls
    )


def test_merge_manual_overrides_auto_data() -> None:
    data: dict[str, Any] = {
        "1": {"home": {"shots": 1}, "away": {"shots": 2}, "source": "espn"},
    }
    manual = {
        "1": {"home": {"shots": 9}, "away": {"shots": 0}},
        "2": {"home": {"possession": 50.0}, "away": {"possession": 50.0}},
    }

    build_match_stats.merge_manual(data, manual)

    assert data["1"]["home"]["shots"] == 9
    assert data["1"]["source"] == "manual"
    assert data["2"]["source"] == "manual"
