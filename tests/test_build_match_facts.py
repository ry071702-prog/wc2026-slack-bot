from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Any

from scripts import build_match_facts
from src.providers.base import Match


def test_parse_goal_details_basic() -> None:
    goals = build_match_facts.parse_goal_details(
        "23':Lionel Messi;45+2':Julian Alvarez;", "home"
    )

    assert goals == [
        {"minute": 23, "player": "Lionel Messi", "team": "home"},
        {
            "minute": 45,
            "player": "Julian Alvarez",
            "team": "home",
            "minute_label": "45+2",
        },
    ]


def test_parse_goal_details_handles_empty_and_none() -> None:
    assert build_match_facts.parse_goal_details("", "home") == []
    assert build_match_facts.parse_goal_details(None, "away") == []


def test_event_goals_merges_and_sorts_both_sides() -> None:
    event = {
        "strHomeGoalDetails": "67':Home Scorer;",
        "strAwayGoalDetails": "12':Away Scorer;90+3':Late Scorer;",
    }

    goals = build_match_facts.event_goals(event)

    assert [goal["player"] for goal in goals] == [
        "Away Scorer",
        "Home Scorer",
        "Late Scorer",
    ]
    assert goals[0]["team"] == "away"
    assert goals[1]["team"] == "home"


def test_team_matches_handles_aliases_and_partial() -> None:
    assert build_match_facts.team_matches("Korea Republic", "South Korea")
    assert build_match_facts.team_matches("USA", "United States")
    assert build_match_facts.team_matches("IR Iran", "Iran")
    assert build_match_facts.team_matches("Türkiye", "Turkey")
    assert build_match_facts.team_matches(
        "Cape Verde Islands", "Cape Verde"
    )
    assert not build_match_facts.team_matches("South Korea", "South Africa")
    assert not build_match_facts.team_matches("Japan", "Jordan")


def test_find_event_filters_league_and_teams() -> None:
    events = [
        {
            "strLeague": "English Premier League",
            "strHomeTeam": "Tunisia",
            "strAwayTeam": "Japan",
        },
        {
            "strLeague": "FIFA World Cup",
            "strHomeTeam": "Tunisia",
            "strAwayTeam": "Japan",
            "idEvent": "777",
        },
    ]

    event = build_match_facts.find_event(events, "Tunisia", "Japan")

    assert event is not None
    assert event["idEvent"] == "777"
    assert build_match_facts.find_event(events, "Spain", "Japan") is None


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeSession:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self.events = events
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return FakeResponse({"events": self.events})


def finished(match: Match) -> Match:
    return replace(match, status="FINISHED")


def wc_event(goal_details: str = "52':Takumi Minamino;") -> dict[str, Any]:
    return {
        "strLeague": "FIFA World Cup",
        "strHomeTeam": "Tunisia",
        "strAwayTeam": "Japan",
        "strHomeGoalDetails": "",
        "strAwayGoalDetails": goal_details,
    }


def test_update_match_facts_registers_goals(japan_match: Match) -> None:
    session = FakeSession([wc_event()])
    data: dict[str, Any] = {}

    updated = build_match_facts.update_match_facts(
        [finished(japan_match)],
        data,
        session,  # type: ignore[arg-type]
        now=japan_match.utc_kickoff + timedelta(hours=6),
    )

    assert updated == 1
    assert data["1"] == {
        "goals": [
            {"minute": 52, "player": "Takumi Minamino", "team": "away"}
        ],
        "source": "thesportsdb",
    }


def test_update_match_facts_retries_when_details_empty(
    japan_match: Match,
) -> None:
    session = FakeSession([wc_event(goal_details="")])
    data: dict[str, Any] = {}

    build_match_facts.update_match_facts(
        [finished(japan_match)],
        data,
        session,  # type: ignore[arg-type]
        now=japan_match.utc_kickoff + timedelta(hours=6),
    )

    assert "1" not in data


def test_update_match_facts_gives_up_after_72h(japan_match: Match) -> None:
    session = FakeSession([])
    data: dict[str, Any] = {}

    build_match_facts.update_match_facts(
        [finished(japan_match)],
        data,
        session,  # type: ignore[arg-type]
        now=japan_match.utc_kickoff + timedelta(hours=73),
    )

    assert data["1"] == {"status": "not_found"}


def test_update_match_facts_skips_registered(japan_match: Match) -> None:
    session = FakeSession([wc_event()])
    data: dict[str, Any] = {"1": {"goals": [], "source": "manual"}}

    updated = build_match_facts.update_match_facts(
        [finished(japan_match)],
        data,
        session,  # type: ignore[arg-type]
    )

    assert updated == 0
    assert session.calls == []


def test_merge_manual_overrides_auto_data() -> None:
    data: dict[str, Any] = {
        "1": {"status": "not_found"},
        "2": {"goals": [], "source": "thesportsdb"},
    }
    manual = {
        "1": {
            "goals": [{"minute": 9, "player": "手動 太郎", "team": "home"}]
        }
    }

    build_match_facts.merge_manual(data, manual)

    assert data["1"] == {
        "goals": [{"minute": 9, "player": "手動 太郎", "team": "home"}],
        "source": "manual",
    }
    assert data["2"]["source"] == "thesportsdb"


def test_candidate_days_covers_utc_and_jst(japan_match: Match) -> None:
    # 2026-06-21T04:00Z はJSTでも同日 → 1日だけ
    assert build_match_facts.candidate_days(japan_match) == [
        japan_match.utc_kickoff.date()
    ]
    late = replace(
        japan_match,
        utc_kickoff=japan_match.utc_kickoff.replace(hour=20),
    )
    days = build_match_facts.candidate_days(late)
    assert [day.isoformat() for day in days] == [
        "2026-06-21",
        "2026-06-22",
    ]
