"""API-FOOTBALL (無料プラン) から出場48カ国の登録スカッドを取得して data/squads.json を作る。

無料プランは100req/日のため、途中保存・再実行で続きから取得できる。
season 依存エンドポイントは無料プラン不可のため、/teams?search と /players/squads のみ使う。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.providers.football_data import FootballDataProvider

BASE_URL = "https://v3.football.api-sports.io"
SQUADS_PATH = ROOT_DIR / "data" / "squads.json"
TEAM_IDS_PATH = ROOT_DIR / "data" / "api_football_team_ids.json"
QUOTA_RESERVE = 4

# football-data 表記 → API-FOOTBALL 検索語 (表記が異なる国のみ)
SEARCH_ALIASES = {
    "South Korea": "South Korea",
    "Czechia": "Czech Republic",
    "Bosnia-Herzegovina": "Bosnia",
    "Cape Verde Islands": "Cape Verde",
    "Congo DR": "Congo DR",
    "United States": "USA",
    "Ivory Coast": "Ivory Coast",
}

POSITION_JA = {
    "Goalkeeper": "GK",
    "Defender": "DF",
    "Midfielder": "MF",
    "Attacker": "FW",
}


class QuotaExhausted(Exception):
    pass


class ApiFootballClient:
    def __init__(self, api_key: str) -> None:
        self.session = requests.Session()
        self.session.headers["x-apisports-key"] = api_key
        self.remaining = None

    def get(self, path: str, **params) -> list:
        if self.remaining is not None and self.remaining <= QUOTA_RESERVE:
            raise QuotaExhausted(f"quota残 {self.remaining} で停止")
        time.sleep(6.5)  # 無料プランの 10req/分 制限対策
        response = self.session.get(
            f"{BASE_URL}/{path}", params=params, timeout=10
        )
        response.raise_for_status()
        remaining = response.headers.get("x-ratelimit-requests-remaining")
        if remaining is not None:
            self.remaining = int(remaining)
        data = response.json()
        if data.get("errors"):
            raise RuntimeError(f"{path}: {data['errors']}")
        return data["response"]


def load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def tournament_team_names() -> list[str]:
    provider = FootballDataProvider(os.environ["FOOTBALL_DATA_API_KEY"])
    from datetime import date

    matches = provider.fetch_matches(date(2026, 6, 11), date(2026, 7, 20))
    return sorted(
        {
            name
            for match in matches
            for name in (match.home, match.away)
            if name and name != "TBD"
        }
    )


def resolve_team_id(client: ApiFootballClient, name: str) -> int | None:
    search = SEARCH_ALIASES.get(name, name)
    results = client.get("teams", search=search)
    nationals = [r["team"] for r in results if r["team"].get("national")]
    if not nationals:
        return None
    exact = [t for t in nationals if t["name"].lower() == search.lower()]
    return (exact or nationals)[0]["id"]


def fetch_squad(client: ApiFootballClient, team_id: int) -> list[dict]:
    results = client.get("players/squads", team=team_id)
    players = results[0]["players"] if results else []
    return [
        {
            "name": p.get("name"),
            "name_ja": p.get("name"),
            "position": POSITION_JA.get(p.get("position"), p.get("position")),
            "number": p.get("number"),
        }
        for p in players
    ]


def main() -> None:
    client = ApiFootballClient(os.environ["API_FOOTBALL_KEY"])
    squads = load_json(SQUADS_PATH)
    team_ids = load_json(TEAM_IDS_PATH)
    names = tournament_team_names()
    unresolved: list[str] = []
    print(f"対象 {len(names)}カ国, 取得済み {len(squads)}")

    try:
        for name in names:
            if name in squads and squads[name]:
                continue
            if name not in team_ids:
                team_id = resolve_team_id(client, name)
                if team_id is None:
                    unresolved.append(name)
                    print(f"  ID未解決: {name}")
                    continue
                team_ids[name] = team_id
                save_json(TEAM_IDS_PATH, team_ids)
            squad = fetch_squad(client, team_ids[name])
            squads[name] = squad
            save_json(SQUADS_PATH, squads)
            print(f"  {name}: {len(squad)}人 (quota残 {client.remaining})")
    except QuotaExhausted as exc:
        print(f"クォータ上限のため中断 (続きは翌日再実行): {exc}")

    done = sum(1 for s in squads.values() if s)
    print(f"完了 {done}/{len(names)}, ID未解決: {unresolved or 'なし'}")


if __name__ == "__main__":
    main()
