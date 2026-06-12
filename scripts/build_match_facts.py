"""TheSportsDB から得点詳細を取得して data/match_facts.json に登録する。

TheSportsDB 無料API (eventsday.php) の strHomeGoalDetails /
strAwayGoalDetails はベストエフォート (空のことも多い) なので、
data/match_facts_manual.json があれば最優先でマージする。
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.providers.base import Match
from src.providers.football_data import FootballDataProvider

TOURNAMENT_START = date(2026, 6, 11)
TOURNAMENT_END = date(2026, 7, 20)
MATCH_FACTS_PATH = ROOT_DIR / "data" / "match_facts.json"
MANUAL_PATH = ROOT_DIR / "data" / "match_facts_manual.json"
EVENTSDAY_URL = "https://www.thesportsdb.com/api/v1/json/123/eventsday.php"
NOT_FOUND_DEADLINE = timedelta(hours=72)

# "23':Lionel Messi;45+2':X;" 形式
GOAL_DETAIL_RE = re.compile(r"(\d+)(?:\+(\d+))?'?\s*:\s*([^;]+)")

# football-data 名 ⇔ TheSportsDB 名の表記差を吸収する正規化エイリアス
TEAM_ALIASES = {
    "korea republic": "south korea",
    "korea": "south korea",
    "usa": "united states",
    "united states of america": "united states",
    "ir iran": "iran",
    "cape verde islands": "cape verde",
    "dr congo": "congo dr",
    "congo": "congo dr",
    "turkiye": "turkey",
    "cote d'ivoire": "ivory coast",
    "china pr": "china",
    "czech republic": "czechia",
    "bosnia and herzegovina": "bosnia-herzegovina",
}


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


def normalize_team(name: str) -> str:
    """アクセント除去 + 小文字化 + エイリアス解決。"""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = " ".join(text.lower().replace("’", "'").split())
    return TEAM_ALIASES.get(text, text)


def team_matches(name_a: str, name_b: str) -> bool:
    """表記差を吸収した部分一致 (どちらかがどちらかを含めばOK)。"""
    a = normalize_team(name_a)
    b = normalize_team(name_b)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def parse_goal_details(text: Optional[str], team: str) -> list[dict[str, Any]]:
    """"23':Lionel Messi;45+2':X;" を goals 配列にパースする。"""
    goals: list[dict[str, Any]] = []
    for matched in GOAL_DETAIL_RE.finditer(text or ""):
        minute = int(matched.group(1))
        extra = matched.group(2)
        player = matched.group(3).strip()
        if not player:
            continue
        goal: dict[str, Any] = {
            "minute": minute,
            "player": player,
            "team": team,
        }
        if extra:
            goal["minute_label"] = f"{minute}+{extra}"
        goals.append(goal)
    return goals


def _goal_sort_key(goal: dict[str, Any]) -> tuple[int, int]:
    label = goal.get("minute_label", "")
    extra = int(label.split("+")[1]) if "+" in label else 0
    return (int(goal.get("minute", 0)), extra)


def event_goals(event: dict[str, Any]) -> list[dict[str, Any]]:
    goals = parse_goal_details(event.get("strHomeGoalDetails"), "home")
    goals += parse_goal_details(event.get("strAwayGoalDetails"), "away")
    return sorted(goals, key=_goal_sort_key)


def is_world_cup_event(event: dict[str, Any]) -> bool:
    return "world cup" in str(event.get("strLeague") or "").lower()


def find_event(
    events: list[dict[str, Any]], home: str, away: str
) -> Optional[dict[str, Any]]:
    for event in events:
        if not is_world_cup_event(event):
            continue
        if team_matches(str(event.get("strHomeTeam") or ""), home) and (
            team_matches(str(event.get("strAwayTeam") or ""), away)
        ):
            return event
    return None


def fetch_events_for_day(
    session: requests.Session, day: date
) -> list[dict[str, Any]]:
    response = session.get(
        EVENTSDAY_URL,
        params={"d": day.isoformat(), "s": "Soccer"},
        timeout=15,
    )
    response.raise_for_status()
    events = response.json().get("events") or []
    return events if isinstance(events, list) else []


def candidate_days(match: Match) -> list[date]:
    """UTC日付とJST日付の両方を試す (重複は除く)。"""
    utc_day = match.utc_kickoff.astimezone(timezone.utc).date()
    jst_day = match.kickoff_jst.date()
    return [utc_day] if utc_day == jst_day else [utc_day, jst_day]


def update_match_facts(
    matches: list[Match],
    data: dict[str, Any],
    session: requests.Session,
    now: Optional[datetime] = None,
) -> int:
    """FINISHED かつ未登録の試合の得点詳細を探す。更新件数を返す。"""
    now = now or datetime.now(timezone.utc)
    events_cache: dict[date, list[dict[str, Any]]] = {}
    updated = 0

    finished = [m for m in matches if m.status == "FINISHED"]
    for match in sorted(finished, key=lambda m: m.utc_kickoff):
        key = str(match.id)
        if key in data:
            continue

        goals: list[dict[str, Any]] = []
        for day in candidate_days(match):
            if day not in events_cache:
                events_cache[day] = fetch_events_for_day(session, day)
            event = find_event(events_cache[day], match.home, match.away)
            if event:
                goals = event_goals(event)
                if goals:
                    break

        if goals:
            data[key] = {"goals": goals, "source": "thesportsdb"}
            updated += 1
            print(
                f"facts: {match.home} vs {match.away} ({len(goals)} goals)"
            )
        elif now - match.utc_kickoff > NOT_FOUND_DEADLINE:
            data[key] = {"status": "not_found"}
            updated += 1
            print(f"facts not found (>72h, give up): {match.home} vs {match.away}")
        else:
            print(f"facts not found (retry next run): {match.home} vs {match.away}")
    return updated


def merge_manual(data: dict[str, Any], manual: dict[str, Any]) -> None:
    """手動補完ファイルを最優先でマージする。"""
    for key, value in manual.items():
        if isinstance(value, dict):
            entry = dict(value)
            entry.setdefault("source", "manual")
            data[key] = entry


def main() -> None:
    football_data_key = os.environ.get("FOOTBALL_DATA_API_KEY", "")
    if not football_data_key:
        raise SystemExit("FOOTBALL_DATA_API_KEY is required")

    matches = FootballDataProvider(football_data_key).fetch_matches(
        TOURNAMENT_START, TOURNAMENT_END
    )

    data = load_json(MATCH_FACTS_PATH)
    before = json.dumps(data, ensure_ascii=False, sort_keys=True)
    update_match_facts(matches, data, requests.Session())
    merge_manual(data, load_json(MANUAL_PATH))
    after = json.dumps(data, ensure_ascii=False, sort_keys=True)
    if before != after:
        save_json(MATCH_FACTS_PATH, data)
        print(f"match facts saved -> {MATCH_FACTS_PATH}")
    else:
        print("no match facts changes")


if __name__ == "__main__":
    main()
