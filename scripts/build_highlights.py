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
PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
CHANNEL_HANDLE = "DAZNJapan"
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
    uploads: list[dict[str, str]], match: Match
) -> Optional[dict[str, str]]:
    """アップロード一覧から、KO以降公開かつ両チーム名+「ハイライト」を含む動画を選ぶ。"""
    kickoff_iso = (
        match.utc_kickoff.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    for upload in uploads:
        title = upload.get("title", "")
        if (
            upload.get("publishedAt", "") >= kickoff_iso
            and "ハイライト" in title
            and title_matches(title, match.home, match.away)
        ):
            return {
                "url": f"https://www.youtube.com/watch?v={upload['videoId']}",
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
    # ハンドル指定 (1unit) で確実に @DAZNJapan を引く
    response = session.get(
        CHANNELS_URL,
        params={"part": "id", "forHandle": CHANNEL_HANDLE, "key": api_key},
        timeout=15,
    )
    response.raise_for_status()
    items = response.json().get("items", [])
    for item in items:
        channel_id = item.get("id")
        if channel_id:
            data[CHANNEL_ID_KEY] = channel_id
            return channel_id
    return None


def fetch_recent_uploads(
    session: requests.Session,
    api_key: str,
    channel_id: str,
    pages: int = 2,
) -> list[dict[str, str]]:
    """チャンネルのアップロード一覧 (最新最大100件)。

    search.list は新着のインデックス反映が数時間遅れるため使わない。
    playlistItems はほぼリアルタイム + 1unit/コール。
    """
    playlist_id = (
        "UU" + channel_id[2:] if channel_id.startswith("UC") else channel_id
    )
    uploads: list[dict[str, str]] = []
    page_token = None
    for _ in range(pages):
        params: dict[str, Any] = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": 50,
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token
        response = session.get(
            PLAYLIST_ITEMS_URL, params=params, timeout=15
        )
        response.raise_for_status()
        payload = response.json()
        for item in payload.get("items", []):
            snippet = item.get("snippet") or {}
            video_id = (snippet.get("resourceId") or {}).get("videoId")
            if video_id:
                uploads.append(
                    {
                        "videoId": video_id,
                        "title": snippet.get("title", ""),
                        "publishedAt": snippet.get("publishedAt", ""),
                    }
                )
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
    return uploads


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

    finished = [m for m in matches if m.status == "FINISHED"]
    pending = [m for m in finished if str(m.id) not in data]
    if not pending:
        print("no pending matches")
        return 0

    uploads = fetch_recent_uploads(session, api_key, channel_id)
    print(f"recent uploads: {len(uploads)} (pending matches: {len(pending)})")

    updated = 0
    for match in sorted(pending, key=lambda m: m.utc_kickoff):
        key = str(match.id)
        picked = pick_video(uploads, match)
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
