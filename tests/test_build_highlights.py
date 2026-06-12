from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

from scripts import build_highlights
from src.providers.base import Match


def make_items(*titles: str) -> list[dict[str, Any]]:
    return [
        {
            "id": {"videoId": f"video{index}"},
            "snippet": {"title": title},
        }
        for index, title in enumerate(titles)
    ]


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeSession:
    """search.list の type に応じて固定レスポンスを返すモック。"""

    def __init__(
        self,
        video_items: list[dict[str, Any]],
        channel_id: str = "UC-dazn",
    ) -> None:
        self.video_items = video_items
        self.channel_id = channel_id
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        params = kwargs.get("params", {})
        self.calls.append({"url": url, **kwargs})
        if url == build_highlights.CHANNELS_URL:
            return FakeResponse({"items": [{"id": self.channel_id}]})
        return FakeResponse({"items": self.video_items})


def test_title_matches_english_names() -> None:
    assert build_highlights.title_matches(
        "【ハイライト】Mexico vs South Africa｜FIFA ワールドカップ26",
        "Mexico",
        "South Africa",
    )


def test_title_matches_japanese_names() -> None:
    assert build_highlights.title_matches(
        "【ハイライト】メキシコ×南アフリカ｜FIFA ワールドカップ26 グループA",
        "Mexico",
        "South Africa",
    )


def test_title_matches_requires_both_teams() -> None:
    assert not build_highlights.title_matches(
        "【ハイライト】メキシコ×カナダ", "Mexico", "South Africa"
    )


def test_pick_video_returns_first_matching(japan_match: Match) -> None:
    items = make_items(
        "今日のW杯まとめ",
        "【ハイライト】チュニジア×日本｜FIFA ワールドカップ26",
        "【ハイライト】Tunisia vs Japan (2本目)",
    )

    picked = build_highlights.pick_video(items, "Tunisia", "Japan")

    assert picked == {
        "url": "https://www.youtube.com/watch?v=video1",
        "title": "【ハイライト】チュニジア×日本｜FIFA ワールドカップ26",
    }


def test_pick_video_returns_none_when_no_match() -> None:
    items = make_items("今日のW杯まとめ", "メキシコ×カナダ ハイライト")

    assert build_highlights.pick_video(items, "Tunisia", "Japan") is None


def finished(match: Match) -> Match:
    return replace(match, status="FINISHED")


def test_update_highlights_registers_found_video(
    japan_match: Match,
) -> None:
    session = FakeSession(make_items("【ハイライト】チュニジア×日本"))
    data: dict[str, Any] = {}

    updated = build_highlights.update_highlights(
        [finished(japan_match)],
        data,
        session,  # type: ignore[arg-type]
        "yt-key",
        now=japan_match.utc_kickoff + timedelta(hours=6),
    )

    assert updated == 1
    assert data["1"]["url"] == "https://www.youtube.com/watch?v=video0"
    assert data["channel_id"] == "UC-dazn"
    # 2回目はチャンネル解決をキャッシュから読む & 登録済みなので検索しない
    calls_before = len(session.calls)
    build_highlights.update_highlights(
        [finished(japan_match)],
        data,
        session,  # type: ignore[arg-type]
        "yt-key",
    )
    assert len(session.calls) == calls_before


def test_update_highlights_marks_not_found_after_72h(
    japan_match: Match,
) -> None:
    session = FakeSession(make_items("関係ない動画"))
    data: dict[str, Any] = {"channel_id": "UC-dazn"}

    build_highlights.update_highlights(
        [finished(japan_match)],
        data,
        session,  # type: ignore[arg-type]
        "yt-key",
        now=japan_match.utc_kickoff + timedelta(hours=73),
    )

    assert data["1"] == {"status": "not_found"}


def test_update_highlights_retries_within_72h(japan_match: Match) -> None:
    session = FakeSession(make_items("関係ない動画"))
    data: dict[str, Any] = {"channel_id": "UC-dazn"}

    build_highlights.update_highlights(
        [finished(japan_match)],
        data,
        session,  # type: ignore[arg-type]
        "yt-key",
        now=japan_match.utc_kickoff + timedelta(hours=6),
    )

    assert "1" not in data


def test_update_highlights_skips_non_finished(japan_match: Match) -> None:
    session = FakeSession(make_items("【ハイライト】チュニジア×日本"))
    data: dict[str, Any] = {"channel_id": "UC-dazn"}

    updated = build_highlights.update_highlights(
        [japan_match],  # status=TIMED
        data,
        session,  # type: ignore[arg-type]
        "yt-key",
    )

    assert updated == 0
    assert session.calls == []


def test_update_highlights_limits_searches(japan_match: Match) -> None:
    session = FakeSession([])
    data: dict[str, Any] = {"channel_id": "UC-dazn"}
    matches = [
        replace(
            finished(japan_match),
            id=100 + offset,
            utc_kickoff=japan_match.utc_kickoff + timedelta(hours=offset),
        )
        for offset in range(25)
    ]

    build_highlights.update_highlights(
        matches,
        data,
        session,  # type: ignore[arg-type]
        "yt-key",
        now=datetime(2026, 7, 30, tzinfo=timezone.utc),
    )

    assert len(session.calls) == build_highlights.MAX_SEARCHES_PER_RUN


def test_search_params_use_channel_and_published_after(
    japan_match: Match,
) -> None:
    session = FakeSession([])
    build_highlights.search_match_videos(
        session,  # type: ignore[arg-type]
        "yt-key",
        "UC-dazn",
        finished(japan_match),
    )

    params = session.calls[0]["params"]
    assert params["type"] == "video"
    assert params["channelId"] == "UC-dazn"
    assert params["q"] == "チュニジア 日本 ハイライト"
    assert params["order"] == "date"
    assert params["publishedAfter"] == "2026-06-21T04:00:00Z"
    assert params["maxResults"] == 5
