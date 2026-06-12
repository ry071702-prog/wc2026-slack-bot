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
        "venue": None,
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
                        "photo": "https://media.api-sports.io/football/players/1.png",
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
    # photo (選手顔写真URL) はそのまま通す
    assert japan["squad"][0]["photo"] == (
        "https://media.api-sports.io/football/players/1.png"
    )
    assert tunisia["rank"] is None
    assert tunisia["squad"] == []
    assert json.loads(
        (output_dir / "schedule.json").read_text(encoding="utf-8")
    ) == schedule
    assert json.loads(
        (output_dir / "teams.json").read_text(encoding="utf-8")
    ) == teams


def test_generate_site_data_copies_highlights_and_match_facts(
    tmp_path: Path,
) -> None:
    highlights_path = tmp_path / "highlights.json"
    highlights = {
        "1001": {
            "url": "https://www.youtube.com/watch?v=HxHaup6d_wM",
            "title": "ハイライト動画",
        }
    }
    highlights_path.write_text(
        json.dumps(highlights, ensure_ascii=False), encoding="utf-8"
    )
    output_dir = tmp_path / "site-data"

    build_site_data.generate_site_data(
        [make_match()],
        rankings_path=tmp_path / "missing-rankings.json",
        squads_path=tmp_path / "missing-squads.json",
        output_dir=output_dir,
        highlights_path=highlights_path,
        match_facts_path=tmp_path / "missing-match-facts.json",
        news_path=tmp_path / "missing-news.json",
    )

    assert json.loads(
        (output_dir / "highlights.json").read_text(encoding="utf-8")
    ) == highlights
    # 元データが無い場合は空オブジェクトを配信する
    assert json.loads(
        (output_dir / "match_facts.json").read_text(encoding="utf-8")
    ) == {}
    assert json.loads(
        (output_dir / "news.json").read_text(encoding="utf-8")
    ) == {}


def test_generate_site_data_copies_japan_opponents(tmp_path: Path) -> None:
    opponents_path = tmp_path / "japan_opponents.json"
    opponents = {
        "opponents": {
            "Tunisia": {
                "name_ja": "チュニジア",
                "match_id": 537360,
                "blurb": "組織的守備が持ち味の北アフリカ勢。",
                "key_players": ["ハンニバル・メジブリ (バーンリー)"],
                "vs_japan": "過去対戦は通算6戦で日本の5勝1敗。",
            }
        }
    }
    opponents_path.write_text(
        json.dumps(opponents, ensure_ascii=False), encoding="utf-8"
    )
    output_dir = tmp_path / "site-data"

    build_site_data.generate_site_data(
        [make_match()],
        rankings_path=tmp_path / "missing-rankings.json",
        squads_path=tmp_path / "missing-squads.json",
        output_dir=output_dir,
        japan_opponents_path=opponents_path,
    )

    assert json.loads(
        (output_dir / "japan_opponents.json").read_text(encoding="utf-8")
    ) == opponents


def test_generate_site_data_japan_opponents_missing_file(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "site-data"

    build_site_data.generate_site_data(
        [make_match()],
        rankings_path=tmp_path / "missing-rankings.json",
        squads_path=tmp_path / "missing-squads.json",
        output_dir=output_dir,
        japan_opponents_path=tmp_path / "missing-opponents.json",
    )

    # 元データが無い場合は空オブジェクトを配信する
    assert json.loads(
        (output_dir / "japan_opponents.json").read_text(encoding="utf-8")
    ) == {}


def test_generate_site_data_joins_team_history(tmp_path: Path) -> None:
    history_path = tmp_path / "team_history.json"
    japan_history = {
        "appearances": 8,
        "titles": 0,
        "title_years": [],
        "best": "ベスト16",
        "last": {"year": 2022, "result": "ベスト16"},
    }
    history_path.write_text(
        json.dumps({"teams": {"Japan": japan_history}}, ensure_ascii=False),
        encoding="utf-8",
    )

    _, teams = build_site_data.generate_site_data(
        [make_match()],
        rankings_path=tmp_path / "missing-rankings.json",
        squads_path=tmp_path / "missing-squads.json",
        output_dir=tmp_path / "site-data",
        team_history_path=history_path,
    )

    japan = next(team for team in teams if team["name"] == "Japan")
    tunisia = next(team for team in teams if team["name"] == "Tunisia")
    assert japan["history"] == japan_history
    # 戦績データが無い国は null
    assert tunisia["history"] is None


def test_generate_site_data_history_missing_file(tmp_path: Path) -> None:
    _, teams = build_site_data.generate_site_data(
        [make_match()],
        rankings_path=tmp_path / "missing-rankings.json",
        squads_path=tmp_path / "missing-squads.json",
        output_dir=tmp_path / "site-data",
        team_history_path=tmp_path / "missing-history.json",
    )

    assert all(team["history"] is None for team in teams)


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
