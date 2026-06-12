from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Any

from scripts import build_highlights
from src.providers.base import Match


def make_uploads(*titles: str, published_at: str = "2026-06-21T08:00:00Z"):
    return [
        {
            "videoId": f"video{index}",
            "title": title,
            "publishedAt": published_at,
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
    """channels / playlistItems に応じて固定レスポンスを返すモック。"""

    def __init__(
        self,
        uploads: list[dict[str, str]],
        channel_id: str = "UC-dazn",
    ) -> None:
        self.uploads = uploads
        self.channel_id = channel_id
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        if url == build_highlights.CHANNELS_URL:
            return FakeResponse({"items": [{"id": self.channel_id}]})
        items = [
            {
                "snippet": {
                    "title": upload["title"],
                    "publishedAt": upload["publishedAt"],
                    "resourceId": {"videoId": upload["videoId"]},
                }
            }
            for upload in self.uploads
        ]
        return FakeResponse({"items": items})


def finished(match: Match) -> Match:
    return replace(match, status="FINISHED")


def test_title_matches_english_names() -> None:
    assert build_highlights.title_matches(
        "【ハイライト】Mexico vs South Africa｜FIFA ワールドカップ26",
        "Mexico",
        "South Africa",
    )


def test_title_matches_japanese_names() -> None:
    assert build_highlights.title_matches(
        "【メキシコ×南アフリカ｜ハイライト｜開催国メキシコが白星発進】グループA第1節",
        "Mexico",
        "South Africa",
    )


def test_title_matches_requires_both_teams() -> None:
    assert not build_highlights.title_matches(
        "【ハイライト】メキシコ×カナダ", "Mexico", "South Africa"
    )


def test_pick_video_requires_highlight_and_kickoff(japan_match: Match) -> None:
    match = finished(japan_match)  # KO 2026-06-21T04:00:00Z
    uploads = (
        make_uploads("チュニジア×日本 試合前プレビュー")
        + make_uploads(
            "【チュニジア×日本｜ハイライト】グループF第2節",
            published_at="2026-06-21T07:00:00Z",
        )
        + make_uploads(
            # KO前に公開された動画はハイライトではない
            "【チュニジア×日本｜ハイライト風の予想】",
            published_at="2026-06-20T00:00:00Z",
        )
    )

    picked = build_highlights.pick_video(uploads, match)

    assert picked is not None
    assert picked["title"] == "【チュニジア×日本｜ハイライト】グループF第2節"


def test_pick_video_returns_none_when_no_match(japan_match: Match) -> None:
    uploads = make_uploads("今日のW杯まとめ", "メキシコ×カナダ ハイライト")

    assert build_highlights.pick_video(uploads, finished(japan_match)) is None


def test_update_highlights_registers_found_video(japan_match: Match) -> None:
    session = FakeSession(
        make_uploads("【チュニジア×日本｜ハイライト】グループF第2節")
    )
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
    # 2回目は登録済みなのでAPIを叩かない
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
    session = FakeSession(make_uploads("関係ない動画"))
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
    session = FakeSession(make_uploads("関係ない動画"))
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
    session = FakeSession(
        make_uploads("【チュニジア×日本｜ハイライト】")
    )
    data: dict[str, Any] = {"channel_id": "UC-dazn"}

    updated = build_highlights.update_highlights(
        [japan_match],  # status=TIMED
        data,
        session,  # type: ignore[arg-type]
        "yt-key",
    )

    assert updated == 0
    assert session.calls == []


def test_uploads_playlist_id_is_derived_from_channel(
    japan_match: Match,
) -> None:
    session = FakeSession(make_uploads("関係ない動画"))

    build_highlights.fetch_recent_uploads(
        session,  # type: ignore[arg-type]
        "yt-key",
        "UC-dazn",
    )

    params = session.calls[0]["params"]
    assert params["playlistId"] == "UU-dazn"
    assert params["maxResults"] == 50
