from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.messages import stage_name, team_name
from src.providers.base import Match
from src.providers.football_data import FootballDataProvider

TOURNAMENT_START = date(2026, 6, 11)
TOURNAMENT_END = date(2026, 7, 20)
SITE_DATA_DIR = ROOT_DIR / "site" / "data"
RANKINGS_PATH = ROOT_DIR / "data" / "fifa_rankings.json"
SQUADS_PATH = ROOT_DIR / "data" / "squads.json"
TEAM_HISTORY_PATH = ROOT_DIR / "data" / "team_history.json"
PREDICTIONS_RAW_PATH = ROOT_DIR / "data" / "predictions.json"
HIGHLIGHTS_PATH = ROOT_DIR / "data" / "highlights.json"
MATCH_FACTS_PATH = ROOT_DIR / "data" / "match_facts.json"
MATCH_STATS_PATH = ROOT_DIR / "data" / "match_stats.json"
NEWS_PATH = ROOT_DIR / "data" / "news.json"
JAPAN_OPPONENTS_PATH = ROOT_DIR / "data" / "japan_opponents.json"


def fetch_matches(api_key: str) -> list[Match]:
    provider = FootballDataProvider(api_key)
    return provider.fetch_matches(TOURNAMENT_START, TOURNAMENT_END)


def match_to_schedule_entry(match: Match) -> dict[str, Any]:
    kickoff_jst = match.kickoff_jst
    return {
        "id": match.id,
        "kickoff_jst": kickoff_jst.isoformat(),
        "date_jst": kickoff_jst.date().isoformat(),
        "home": match.home,
        "away": match.away,
        "home_ja": team_name(match.home),
        "away_ja": team_name(match.away),
        "stage": match.stage,
        "stage_ja": stage_name(match),
        "group": match.group,
        "matchday": match.matchday,
        "status": match.status,
        "venue": match.venue,
        "score": {
            "home": match.score.home,
            "away": match.score.away,
            "duration": match.score.duration,
            "penalties_home": match.score.penalties_home,
            "penalties_away": match.score.penalties_away,
        },
        "is_japan": match.is_japan,
    }


def build_schedule(matches: list[Match]) -> list[dict[str, Any]]:
    return [
        match_to_schedule_entry(match)
        for match in sorted(matches, key=lambda item: item.utc_kickoff)
    ]


def build_teams(
    schedule: list[dict[str, Any]],
    rankings: dict[str, int],
    squads: dict[str, list[dict[str, Any]]],
    history: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    team_names = {
        name
        for match in schedule
        for name in (str(match["home"]), str(match["away"]))
        if name and name != "TBD"
    }
    history = history or {}
    return [
        {
            "name": name,
            "name_ja": team_name(name),
            "rank": rankings.get(name),
            "squad": squads.get(name, []),
            "history": history.get(name),
        }
        for name in sorted(team_names, key=lambda item: (team_name(item), item))
    ]


def build_predictions_summary(raw: dict[str, Any]) -> dict[str, Any]:
    """/yosou の生データ (user_id キー) を優勝予想の分布に集計する。"""
    champions: dict[str, int] = {}
    for entry in raw.values():
        champion = entry.get("champion")
        if champion:
            champions[champion] = champions.get(champion, 0) + 1
    distribution = dict(
        sorted(champions.items(), key=lambda item: (-item[1], item[0]))
    )
    return {"total": len(raw), "distribution": distribution}


def load_rankings(path: Path = RANKINGS_PATH) -> dict[str, int]:
    payload = load_optional_json(path, {})
    ranks = payload.get("ranks", {})
    return ranks if isinstance(ranks, dict) else {}


def load_squads(
    path: Path = SQUADS_PATH,
) -> dict[str, list[dict[str, Any]]]:
    payload = load_optional_json(path, {})
    return payload if isinstance(payload, dict) else {}


def load_team_history(
    path: Path = TEAM_HISTORY_PATH,
) -> dict[str, dict[str, Any]]:
    payload = load_optional_json(path, {})
    teams = payload.get("teams", {})
    return teams if isinstance(teams, dict) else {}


def load_optional_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def generate_site_data(
    matches: list[Match],
    rankings_path: Path = RANKINGS_PATH,
    squads_path: Path = SQUADS_PATH,
    output_dir: Path = SITE_DATA_DIR,
    highlights_path: Path = HIGHLIGHTS_PATH,
    match_facts_path: Path = MATCH_FACTS_PATH,
    match_stats_path: Path = MATCH_STATS_PATH,
    news_path: Path = NEWS_PATH,
    team_history_path: Path = TEAM_HISTORY_PATH,
    japan_opponents_path: Path = JAPAN_OPPONENTS_PATH,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    schedule = build_schedule(matches)
    teams = build_teams(
        schedule,
        load_rankings(rankings_path),
        load_squads(squads_path),
        load_team_history(team_history_path),
    )
    write_json(output_dir / "schedule.json", schedule)
    write_json(output_dir / "teams.json", teams)
    predictions = build_predictions_summary(
        load_optional_json(PREDICTIONS_RAW_PATH, {})
    )
    write_json(output_dir / "predictions.json", predictions)
    # 試合詳細ページ用の付随データ (無ければ空オブジェクトで配信)
    write_json(
        output_dir / "highlights.json",
        load_optional_json(highlights_path, {}),
    )
    write_json(
        output_dir / "match_facts.json",
        load_optional_json(match_facts_path, {}),
    )
    # 試合スタッツ (ESPN) — 無ければ空オブジェクトで配信
    write_json(
        output_dir / "match_stats.json",
        load_optional_json(match_stats_path, {}),
    )
    # ニュース (Google News RSS) — 無ければ空オブジェクトで配信
    write_json(
        output_dir / "news.json",
        load_optional_json(news_path, {}),
    )
    # 日本代表特設ページ用の対戦相手データ — 無ければ空オブジェクトで配信
    write_json(
        output_dir / "japan_opponents.json",
        load_optional_json(japan_opponents_path, {}),
    )
    return schedule, teams


def main() -> None:
    api_key = os.environ.get("FOOTBALL_DATA_API_KEY", "")
    if not api_key:
        raise SystemExit("FOOTBALL_DATA_API_KEY is required")

    matches = fetch_matches(api_key)
    schedule, teams = generate_site_data(matches)
    japan_matches = sum(1 for match in schedule if match["is_japan"])
    print(
        "site data generated: "
        f"{len(schedule)} matches, {len(teams)} teams, "
        f"{japan_matches} Japan matches -> {SITE_DATA_DIR}"
    )


if __name__ == "__main__":
    main()
