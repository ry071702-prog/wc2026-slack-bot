from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from scripts import build_site_data
from src.providers.base import Match, MatchScore


def make_match(
    *,
    match_id: int = 1001,
    home: str = "Tunisia",
    away: str = "Japan",
) -> Match:
    return Match(
        id=match_id,
        utc_kickoff=datetime(2026, 6, 21, 4, 0, tzinfo=timezone.utc),
        home=home,
        away=away,
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


def test_match_to_schedule_entry_converts_to_jst() -> None:
    entry = build_site_data.match_to_schedule_entry(make_match())

    assert entry == {
        "id": 1001,
        "kickoff_jst": "2026-06-21T13:00:00+09:00",
        "date_jst": "2026-06-21",
        "home": "Tunisia",
        "away": "Japan",
        "home_ja": "チュニジア",
        "away_ja": "日本",
        "stage": "GROUP_STAGE",
        "stage_ja": "グループF 第2節",
        "group": "GROUP_F",
        "matchday": 2,
        "status": "FINISHED",
        "score": {
            "home": 1,
            "away": 2,
            "duration": "REGULAR",
            "penalties_home": None,
            "penalties_away": None,
        },
        "is_japan": True,
    }


def test_generate_site_data_joins_rankings_and_squads(
    tmp_path: Path,
) -> None:
    rankings_path = tmp_path / "fifa_rankings.json"
    squads_path = tmp_path / "squads.json"
    output_dir = tmp_path / "site-data"
    rankings_path.write_text(
        json.dumps({"ranks": {"Japan": 18}}),
        encoding="utf-8",
    )
    squads_path.write_text(
        json.dumps(
            {
                "Japan": [
                    {
                        "name": "Sample Player",
                        "name_ja": "サンプル選手",
                        "position": "MF",
                        "number": 10,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    schedule, teams = build_site_data.generate_site_data(
        [make_match()],
        rankings_path=rankings_path,
        squads_path=squads_path,
        output_dir=output_dir,
    )

    japan = next(team for team in teams if team["name"] == "Japan")
    tunisia = next(team for team in teams if team["name"] == "Tunisia")
    assert japan["rank"] == 18
    assert japan["squad"][0]["number"] == 10
    assert tunisia["rank"] is None
    assert tunisia["squad"] == []
    assert json.loads(
        (output_dir / "schedule.json").read_text(encoding="utf-8")
    ) == schedule
    assert json.loads(
        (output_dir / "teams.json").read_text(encoding="utf-8")
    ) == teams


def test_build_teams_excludes_tbd() -> None:
    schedule = build_site_data.build_schedule(
        [make_match(home="TBD", away="Japan")]
    )

    teams = build_site_data.build_teams(schedule, {}, {})

    assert [team["name"] for team in teams] == ["Japan"]


def test_generate_site_data_handles_missing_optional_files(
    tmp_path: Path,
) -> None:
    _, teams = build_site_data.generate_site_data(
        [make_match()],
        rankings_path=tmp_path / "missing-rankings.json",
        squads_path=tmp_path / "missing-squads.json",
        output_dir=tmp_path / "site-data",
    )

    assert all(team["rank"] is None for team in teams)
    assert all(team["squad"] == [] for team in teams)


def test_fetch_matches_uses_full_tournament_range(monkeypatch) -> None:
    calls: list[tuple[str, date, date]] = []

    class FakeProvider:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key

        def fetch_matches(
            self, date_from: date, date_to: date
        ) -> list[Match]:
            calls.append((self.api_key, date_from, date_to))
            return [make_match()]

    monkeypatch.setattr(build_site_data, "FootballDataProvider", FakeProvider)

    matches = build_site_data.fetch_matches("test-key")

    assert len(matches) == 1
    assert calls == [
        ("test-key", date(2026, 6, 11), date(2026, 7, 20))
    ]
