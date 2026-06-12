from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts import build_news

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "news_rss.xml"


@pytest.fixture
def rss_xml() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


class FakeResponse:
    def __init__(self, text: str, status_ok: bool = True) -> None:
        self.text = text
        self.status_ok = status_ok

    def raise_for_status(self) -> None:
        if not self.status_ok:
            raise RuntimeError("HTTP 503")


class FakeSession:
    """URL ごとにレスポンス (または例外) を返すモックセッション。"""

    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append(url)
        response = self.responses.get(url)
        if isinstance(response, Exception):
            raise response
        if response is None:
            return FakeResponse("", status_ok=False)
        return FakeResponse(response)


def test_parse_feed_extracts_articles(rss_xml: str) -> None:
    articles = build_news.parse_feed(rss_xml, "en")

    # link 無しの item は除外され、新しい順に並ぶ
    assert [article["source"] for article in articles] == [
        "ESPN",
        "Reuters",
        "",
    ]
    assert articles[0] == {
        "title": "Japan name final 26-man squad",
        "source": "ESPN",
        "published_at": "2026-06-11T12:30:00+00:00",
        "url": "https://news.google.com/rss/articles/sample-espn",
        "lang": "en",
    }
    # pubDate の無い記事は published_at=None で末尾に落ちる
    assert articles[2]["published_at"] is None
    assert articles[2]["title"] == "Headline without date or source"


def test_parse_feed_limits_to_20_items() -> None:
    items = "".join(
        "<item>"
        f"<title>Headline {index} - Media</title>"
        f"<link>https://example.com/{index}</link>"
        f"<pubDate>Thu, 11 Jun 2026 {index:02d}:00:00 GMT</pubDate>"
        "<source url='https://example.com'>Media</source>"
        "</item>"
        for index in range(23)
    )
    xml_text = f"<rss><channel>{items}</channel></rss>"

    articles = build_news.parse_feed(xml_text, "ja")

    assert len(articles) == build_news.MAX_ARTICLES_PER_FEED
    # 新しい順 (22時 → 3時) で 20 件
    assert articles[0]["title"] == "Headline 22"
    assert articles[-1]["title"] == "Headline 3"
    assert all(article["lang"] == "ja" for article in articles)


def test_strip_source_suffix() -> None:
    assert (
        build_news.strip_source_suffix("Big news - Reuters", "Reuters")
        == "Big news"
    )
    assert (
        build_news.strip_source_suffix("Big news - Reuters", "ESPN")
        == "Big news - Reuters"
    )
    assert build_news.strip_source_suffix("Big news", "") == "Big news"


def test_parse_pub_date_handles_invalid_values() -> None:
    assert build_news.parse_pub_date(None) is None
    assert build_news.parse_pub_date("not a date") is None
    assert (
        build_news.parse_pub_date("Thu, 11 Jun 2026 12:30:00 GMT")
        == "2026-06-11T12:30:00+00:00"
    )


def test_update_articles_fetches_all_feeds(rss_xml: str) -> None:
    session = FakeSession(
        {feed["url"]: rss_xml for feed in build_news.FEEDS}
    )

    articles, fetched = build_news.update_articles(session, [])  # type: ignore[arg-type]

    assert fetched == len(build_news.FEEDS)
    assert len(session.calls) == len(build_news.FEEDS)
    langs = {article["lang"] for article in articles}
    assert langs == {"en", "ja"}


def test_update_articles_keeps_existing_on_failure(rss_xml: str) -> None:
    en_url = build_news.FEEDS[0]["url"]
    ja_url = build_news.FEEDS[1]["url"]
    session = FakeSession(
        {
            en_url: rss_xml,
            ja_url: ConnectionError("network down"),
        }
    )
    existing = [
        {"title": "古い日本語記事", "source": "旧媒体", "lang": "ja"},
        {"title": "old english article", "source": "Old", "lang": "en"},
    ]

    articles, fetched = build_news.update_articles(session, existing)  # type: ignore[arg-type]

    assert fetched == 1
    # 失敗した ja フィードは既存記事で代替し、en は新規取得分になる
    ja_articles = [a for a in articles if a["lang"] == "ja"]
    en_articles = [a for a in articles if a["lang"] == "en"]
    assert ja_articles == [existing[0]]
    assert all(a["title"] != "old english article" for a in en_articles)
    assert len(en_articles) == 3


def test_update_articles_all_failed_returns_existing(rss_xml: str) -> None:
    session = FakeSession({})  # 全URLで HTTP エラー
    existing = [{"title": "既存記事", "source": "旧媒体", "lang": "ja"}]

    articles, fetched = build_news.update_articles(session, existing)  # type: ignore[arg-type]

    assert fetched == 0
    assert articles == existing
