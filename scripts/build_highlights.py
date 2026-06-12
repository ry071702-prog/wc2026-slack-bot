"""DAZN Japan の YouTube ハイライト動画を探して data/highlights.json に登録する。

YouTube Data API v3 (search.list) を使う。クォータは search 100 unit/回・
1日 10,000 unit なので、1実行あたりの検索は最大 20 試合に制限する。
YOUTUBE_API_KEY が無い環境では何もせず正常終了する (skip)。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.messages import team_name
from src.providers.base import Match
from src.providers.football_data import FootballDataProvider

TOURNAMENT_START = date(2026, 6, 11)
TOURNAMENT_END = date(2026, 7, 20)
HIGHLIGHTS_PATH = ROOT_DIR / "data" / "highlights.json"
SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
CHANNEL_QUERY = "DAZN Japan"
CHANNEL_ID_KEY = "channel_id"
NOT_FOUND_DEADLINE = timedelta(hours=72)
MAX_SEARCHES_PER_RUN = 20


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


def title_matches(title: str, home: str, away: str) -> bool:
    """タイトルに両チーム名 (英語名 or 日本語名のどちらか) が入っているか。"""
    lowered = title.lower()

    def team_hit(name: str) -> bool:
        name_ja = team_name(name)
        return name.lower() in lowered or name_ja in title

    return team_hit(home) and team_hit(away)


def pick_video(
    items: list[dict[str, Any]], home: str, away: str
) -> Optional[dict[str, str]]:
    """検索結果からタイトルに両チーム名が入る最初の動画を採用する。"""
    for item in items:
        video_id = (item.get("id") or {}).get("videoId")
        title = (item.get("snippet") or {}).get("title", "")
        if video_id and title_matches(title, home, away):
            return {
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "title": title,
            }
    return None


def _search(
    session: requests.Session, api_key: str, params: dict[str, Any]
) -> list[dict[str, Any]]:
    response = session.get(
        SEARCH_URL,
        params={"part": "snippet", "key": api_key, **params},
        timeout=15,
    )
    response.raise_for_status()
    items = response.json().get("items", [])
    return items if isinstance(items, list) else []


def resolve_channel_id(
    session: requests.Session, api_key: str, data: dict[str, Any]
) -> Optional[str]:
    """DAZN Japan のチャンネルIDを解決する (初回のみ API、以後キャッシュ)。"""
    cached = data.get(CHANNEL_ID_KEY)
    if isinstance(cached, str) and cached:
        return cached
    items = _search(
        session,
        api_key,
        {"type": "channel", "q": CHANNEL_QUERY, "maxResults": 1},
    )
    for item in items:
        channel_id = (item.get("snippet") or {}).get("channelId") or (
            item.get("id") or {}
        ).get("channelId")
        if channel_id:
            data[CHANNEL_ID_KEY] = channel_id
            return channel_id
    return None


def search_match_videos(
    session: requests.Session,
    api_key: str,
    channel_id: str,
    match: Match,
) -> list[dict[str, Any]]:
    published_after = (
        match.utc_kickoff.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    return _search(
        session,
        api_key,
        {
            "type": "video",
            "channelId": channel_id,
            "q": f"{match.home} {match.away}",
            "order": "date",
            "publishedAfter": published_after,
            "maxResults": 5,
        },
    )


def update_highlights(
    matches: list[Match],
    data: dict[str, Any],
    session: requests.Session,
    api_key: str,
    now: Optional[datetime] = None,
) -> int:
    """FINISHED かつ未登録の試合のハイライトを探す。更新件数を返す。"""
    now = now or datetime.now(timezone.utc)
    channel_id = resolve_channel_id(session, api_key, data)
    if not channel_id:
        print("DAZN Japan channel could not be resolved; abort")
        return 0

    updated = 0
    searched = 0
    finished = [m for m in matches if m.status == "FINISHED"]
    for match in sorted(finished, key=lambda m: m.utc_kickoff):
        key = str(match.id)
        if key in data:
            continue
        if searched >= MAX_SEARCHES_PER_RUN:
            print(f"search limit ({MAX_SEARCHES_PER_RUN}) reached; stop")
            break
        searched += 1
        items = search_match_videos(session, api_key, channel_id, match)
        picked = pick_video(items, match.home, match.away)
        if picked:
            data[key] = picked
            updated += 1
            print(f"found: {match.home} vs {match.away} -> {picked['url']}")
        elif now - match.utc_kickoff > NOT_FOUND_DEADLINE:
            data[key] = {"status": "not_found"}
            updated += 1
            print(f"not found (>72h, give up): {match.home} vs {match.away}")
        else:
            print(f"not found (retry next run): {match.home} vs {match.away}")
    return updated


def main() -> None:
    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        print("YOUTUBE_API_KEY is not set; skip")
        return

    football_data_key = os.environ.get("FOOTBALL_DATA_API_KEY", "")
    if not football_data_key:
        raise SystemExit("FOOTBALL_DATA_API_KEY is required")

    matches = FootballDataProvider(football_data_key).fetch_matches(
        TOURNAMENT_START, TOURNAMENT_END
    )

    data = load_json(HIGHLIGHTS_PATH)
    before = json.dumps(data, ensure_ascii=False, sort_keys=True)
    update_highlights(matches, data, requests.Session(), api_key)
    after = json.dumps(data, ensure_ascii=False, sort_keys=True)
    if before != after:
        save_json(HIGHLIGHTS_PATH, data)
        print(f"highlights saved -> {HIGHLIGHTS_PATH}")
    else:
        print("no highlight changes")


if __name__ == "__main__":
    main()
