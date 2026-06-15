"""ESPN の非公式 JSON から試合スタッツを取得して data/match_stats.json に保存する。

ESPN (site.api.espn.com) は無料・キー不要だが User-Agent ヘッダが必須。
スコアボード(日付別)で football-data の試合に対応する ESPN event を特定し、
summary?event=ID の boxscore.teams[] から支配率・シュート等を抽出する。

ベストエフォート: event が見つからない / 例外が出た試合はスキップし
(次回実行で再試行)、クラッシュしない。data/match_stats_manual.json が
あれば最優先でマージする。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.providers.base import Match
from src.providers.football_data import FootballDataProvider

TOURNAMENT_START = date(2026, 6, 11)
TOURNAMENT_END = date(2026, 7, 20)
MATCH_STATS_PATH = ROOT_DIR / "data" / "match_stats.json"
MANUAL_PATH = ROOT_DIR / "data" / "match_stats_manual.json"

SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
)
SUMMARY_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary"
)
USER_AGENT = "Mozilla/5.0"
REQUEST_TIMEOUT = 20
# 1実行あたりの取得試合数の上限 (ESPNへの負荷とAction時間の抑制)
MAX_MATCHES_PER_RUN = 20

# football-data 名 ⇔ ESPN 名の表記差を吸収する正規化エイリアス。
# 正規化 (アクセント除去 + 小文字) した結果を共通表記に寄せる。
TEAM_ALIASES = {
    "korea republic": "south korea",
    "korea": "south korea",
    "usa": "united states",
    "united states of america": "united states",
    "ir iran": "iran",
    "cape verde islands": "cape verde",
    "dr congo": "congo dr",
    "turkiye": "turkey",
    "cote d'ivoire": "ivory coast",
    "cote d ivoire": "ivory coast",
    "cote divoire": "ivory coast",
    "china pr": "china",
    "czech republic": "czechia",
    "bosnia and herzegovina": "bosnia-herzegovina",
}

# ESPN stat name -> (出力キー, 数値化関数)。possession のみ float、他は int。
STAT_MAP: dict[str, tuple[str, Callable[[float], Any]]] = {
    "possessionPct": ("possession", float),
    "totalShots": ("shots", int),
    "shotsOnTarget": ("shots_on_target", int),
    "accuratePasses": ("passes_accurate", int),
    "totalPasses": ("passes", int),
    "wonCorners": ("corners", int),
    "foulsCommitted": ("fouls", int),
    "yellowCards": ("yellow", int),
    "redCards": ("red", int),
    "offsides": ("offsides", int),
    "saves": ("saves", int),
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
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = " ".join(text.lower().replace("’", "'").split())
    return TEAM_ALIASES.get(text, text)


def team_matches(name_a: str, name_b: str) -> bool:
    """エイリアス解決後の完全一致で判定する。
    部分一致は Mali↔Somalia / Guinea↔Equatorial Guinea のような誤マッチ
    (home/away 取り違え) を生むため使わない。表記差は TEAM_ALIASES で吸収する。"""
    a = normalize_team(name_a)
    b = normalize_team(name_b)
    return bool(a) and a == b


def to_number(raw: Any, converter: Callable[[float], Any]) -> Optional[Any]:
    """ESPN の displayValue ("61.1" / "310" / "1,234" / "55%") を数値化する。"""
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "").rstrip("%").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return converter(value)


def extract_team_stats(statistics: list[dict[str, Any]]) -> dict[str, Any]:
    """boxscore の statistics[] (各 name / displayValue) を出力キーに写す。"""
    result: dict[str, Any] = {}
    for stat in statistics or []:
        mapping = STAT_MAP.get(str(stat.get("name") or ""))
        if not mapping:
            continue
        key, converter = mapping
        number = to_number(stat.get("displayValue"), converter)
        if number is not None:
            result[key] = number
    return result


def parse_boxscore(
    boxscore: dict[str, Any], home: str, away: str
) -> dict[str, Any]:
    """boxscore.teams[] を displayName で home/away に正しく対応付ける。

    ESPN の homeAway と schedule の home/away が逆のことがあるため、
    必ずチーム名 (正規化 + エイリアス) で突き合わせる。
    """
    result: dict[str, Any] = {}
    for team in boxscore.get("teams") or []:
        name = str((team.get("team") or {}).get("displayName") or "")
        stats = extract_team_stats(team.get("statistics") or [])
        if not stats:
            continue
        if "home" not in result and team_matches(name, home):
            result["home"] = stats
        elif "away" not in result and team_matches(name, away):
            result["away"] = stats
    return result


def competitor_names(event: dict[str, Any]) -> list[str]:
    competition = (event.get("competitions") or [{}])[0]
    names: list[str] = []
    for competitor in competition.get("competitors") or []:
        name = str((competitor.get("team") or {}).get("displayName") or "")
        if name:
            names.append(name)
    return names


def find_espn_event(
    events: list[dict[str, Any]], home: str, away: str
) -> Optional[dict[str, Any]]:
    """competitors の displayName が home/away 両方に一致する event を探す。

    ESPN と schedule で home/away が逆でも拾えるよう順不同で照合する。
    """
    for event in events:
        names = competitor_names(event)
        if len(names) < 2:
            continue
        first, second = names[0], names[1]
        forward = team_matches(first, home) and team_matches(second, away)
        reverse = team_matches(second, home) and team_matches(first, away)
        if forward or reverse:
            return event
    return None


def candidate_days(match: Match) -> list[date]:
    """date_jst とその前日を試す (ESPNの日付はUTC寄りでJSTより前日になりうる)。"""
    jst_day = match.kickoff_jst.date()
    return [jst_day, jst_day - timedelta(days=1)]


def fetch_scoreboard(
    session: requests.Session, day: date
) -> list[dict[str, Any]]:
    response = session.get(
        SCOREBOARD_URL,
        params={"dates": day.strftime("%Y%m%d")},
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    events = response.json().get("events") or []
    return events if isinstance(events, list) else []


def fetch_summary(session: requests.Session, event_id: str) -> dict[str, Any]:
    response = session.get(
        SUMMARY_URL,
        params={"event": event_id},
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def build_stats_entry(
    match: Match,
    session: requests.Session,
    scoreboard_cache: dict[date, list[dict[str, Any]]],
) -> Optional[dict[str, Any]]:
    """1試合分のスタッツを ESPN から取得する。見つからなければ None。"""
    for day in candidate_days(match):
        if day not in scoreboard_cache:
            scoreboard_cache[day] = fetch_scoreboard(session, day)
        event = find_espn_event(scoreboard_cache[day], match.home, match.away)
        if not event:
            continue
        event_id = event.get("id")
        if not event_id:
            continue
        summary = fetch_summary(session, str(event_id))
        boxscore = summary.get("boxscore") or {}
        stats = parse_boxscore(boxscore, match.home, match.away)
        if stats.get("home") or stats.get("away"):
            return {**stats, "source": "espn"}
    return None


def score_confirmed(match: Match) -> bool:
    return match.score.home is not None and match.score.away is not None


def update_match_stats(
    matches: list[Match],
    data: dict[str, Any],
    session: requests.Session,
    limit: int = MAX_MATCHES_PER_RUN,
) -> int:
    """FINISHED かつ score確定かつ未登録の試合のスタッツを取得する。更新件数を返す。"""
    finished = [
        m
        for m in matches
        if m.status == "FINISHED" and score_confirmed(m)
    ]
    pending = [m for m in finished if str(m.id) not in data]
    pending.sort(key=lambda m: m.utc_kickoff)

    scoreboard_cache: dict[date, list[dict[str, Any]]] = {}
    updated = 0
    for match in pending[:limit]:
        try:
            entry = build_stats_entry(match, session, scoreboard_cache)
        except Exception as error:  # noqa: BLE001 - ベストエフォート
            print(f"stats error ({match.home} vs {match.away}): {error}")
            continue
        if entry:
            data[str(match.id)] = entry
            updated += 1
            print(f"stats: {match.home} vs {match.away} -> ESPN")
        else:
            print(
                "stats not found (retry next run): "
                f"{match.home} vs {match.away}"
            )
    return updated


def merge_manual(data: dict[str, Any], manual: dict[str, Any]) -> None:
    """手動補完ファイルを最優先でマージする。"""
    for key, value in manual.items():
        if isinstance(value, dict):
            entry = dict(value)
            entry.setdefault("source", "manual")
            data[key] = entry


def main() -> None:
    parser = argparse.ArgumentParser(description="Build match stats from ESPN.")
    parser.add_argument(
        "--only", help="特定の試合ID 1件だけ取得する", default=None
    )
    args = parser.parse_args()

    football_data_key = os.environ.get("FOOTBALL_DATA_API_KEY", "")
    if not football_data_key:
        raise SystemExit("FOOTBALL_DATA_API_KEY is required")

    matches = FootballDataProvider(football_data_key).fetch_matches(
        TOURNAMENT_START, TOURNAMENT_END
    )
    if args.only:
        matches = [m for m in matches if str(m.id) == str(args.only)]
        if not matches:
            print(f"match {args.only} not found in schedule")

    data = load_json(MATCH_STATS_PATH)
    before = json.dumps(data, ensure_ascii=False, sort_keys=True)
    update_match_stats(matches, data, requests.Session())
    merge_manual(data, load_json(MANUAL_PATH))
    after = json.dumps(data, ensure_ascii=False, sort_keys=True)
    if before != after:
        save_json(MATCH_STATS_PATH, data)
        print(f"match stats saved -> {MATCH_STATS_PATH}")
    else:
        print("no match stats changes")


if __name__ == "__main__":
    main()
