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
    def __init__(self, text: str, status_ok: bool = True, url: str = "") -> None:
        self.text = text
        self.status_ok = status_ok
        self.url = url

    def raise_for_status(self) -> None:
        if not self.status_ok:
            raise RuntimeError("HTTP 503")


class FakeSession:
    """URL ごとにレスポンス (または例外) を返すモックセッション。"""

    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[str] = []
        self.post_calls: list[str] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append(url)
        response = self.responses.get(url)
        if isinstance(response, Exception):
            raise response
        if response is None:
            return FakeResponse("", status_ok=False, url=url)
        return FakeResponse(response, url=url)

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.post_calls.append(url)
        response = self.responses.get(("POST", url))
        if isinstance(response, Exception):
            raise response
        if response is None:
            return FakeResponse("", status_ok=False, url=url)
        return FakeResponse(response, url=url)


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
        "image": None,
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


# --- og:image (サムネイル) ---------------------------------------------------


def test_extract_og_image_property_first() -> None:
    html_text = (
        "<html><head>"
        '<meta property="og:image" content="https://example.com/og.jpg">'
        "</head></html>"
    )
    assert build_news.extract_og_image(html_text) == "https://example.com/og.jpg"


def test_extract_og_image_attribute_order_and_quotes() -> None:
    # content が先・シングルクォート・name 属性でも拾える
    html_text = (
        "<meta content='https://example.com/rev.png' property='og:image' />"
    )
    assert build_news.extract_og_image(html_text) == "https://example.com/rev.png"

    html_text = '<meta name="og:image" content="https://example.com/n.png">'
    assert build_news.extract_og_image(html_text) == "https://example.com/n.png"


def test_extract_og_image_falls_back_to_twitter_image() -> None:
    html_text = (
        '<meta name="twitter:image" content="https://example.com/tw.jpg">'
        '<meta property="og:title" content="title">'
    )
    assert build_news.extract_og_image(html_text) == "https://example.com/tw.jpg"


def test_extract_og_image_prefers_og_over_twitter() -> None:
    html_text = (
        '<meta name="twitter:image" content="https://example.com/tw.jpg">'
        '<meta property="og:image" content="https://example.com/og.jpg">'
    )
    assert build_news.extract_og_image(html_text) == "https://example.com/og.jpg"


def test_extract_og_image_rejects_missing_or_relative() -> None:
    assert build_news.extract_og_image("<html><body>no meta</body></html>") is None
    assert (
        build_news.extract_og_image(
            '<meta property="og:image" content="/relative/path.jpg">'
        )
        is None
    )


def test_extract_og_image_unescapes_html_entities() -> None:
    html_text = (
        '<meta property="og:image" '
        'content="https://example.com/a.jpg?w=1200&amp;h=630">'
    )
    assert (
        build_news.extract_og_image(html_text)
        == "https://example.com/a.jpg?w=1200&h=630"
    )


def test_resolve_google_news_url_passes_through_other_hosts() -> None:
    session = FakeSession({})

    resolved = build_news.resolve_google_news_url(
        session,  # type: ignore[arg-type]
        "https://example.com/article",
    )

    assert resolved == "https://example.com/article"
    assert session.calls == []  # ネットワークアクセスなし


def test_resolve_google_news_url_decodes_via_batchexecute() -> None:
    gn_url = "https://news.google.com/rss/articles/CBMiSample?oc=5"
    article_page = (
        '<c-wiz data-n-a-id="x" data-n-a-sg="SIG123" data-n-a-ts="99">'
    )
    batch_response = (
        ")]}'\n\n"
        '[["wrb.fr","Fbv4je","[\\"garturlres\\",\\"https://example.com/real-article\\"]",null,null,null,"generic"]]'
    )
    session = FakeSession(
        {
            "https://news.google.com/articles/CBMiSample": article_page,
            ("POST", build_news._BATCHEXECUTE_URL): batch_response,
        }
    )

    resolved = build_news.resolve_google_news_url(session, gn_url)  # type: ignore[arg-type]

    assert resolved == "https://example.com/real-article"
    assert session.post_calls == [build_news._BATCHEXECUTE_URL]


def test_resolve_google_news_url_returns_none_without_signature() -> None:
    gn_url = "https://news.google.com/rss/articles/CBMiSample?oc=5"
    session = FakeSession(
        {"https://news.google.com/articles/CBMiSample": "<html>consent page</html>"}
    )

    assert (
        build_news.resolve_google_news_url(session, gn_url)  # type: ignore[arg-type]
        is None
    )
    assert session.post_calls == []


def test_fetch_article_image_rejects_google_interstitial() -> None:
    # 解決後も news.google.com に留まる場合は汎用ロゴしか取れないため None
    gn_url = "https://news.google.com/rss/articles/CBMiSample?oc=5"
    article_page = '<c-wiz data-n-a-sg="SIG123" data-n-a-ts="99">'
    batch_response = (
        '[["wrb.fr","Fbv4je","[\\"garturlres\\",'
        '\\"https://news.google.com/articles/Other\\"]",null,null,null,"generic"]]'
    )
    generic_logo_html = (
        '<meta property="og:image" '
        'content="https://lh3.googleusercontent.com/generic-logo">'
    )
    session = FakeSession(
        {
            "https://news.google.com/articles/CBMiSample": article_page,
            ("POST", build_news._BATCHEXECUTE_URL): batch_response,
            "https://news.google.com/articles/Other": generic_logo_html,
        }
    )

    image = build_news.fetch_article_image(session, gn_url)  # type: ignore[arg-type]

    assert image is None


def test_merge_existing_images_keeps_previous_image() -> None:
    articles = [
        {"url": "https://example.com/a", "image": None},
        {"url": "https://example.com/b", "image": None},
        {"url": "https://example.com/c", "image": "https://img.example.com/new.jpg"},
    ]
    existing = [
        {"url": "https://example.com/a", "image": "https://img.example.com/a.jpg"},
        {"url": "https://example.com/b", "image": None},  # 前回も無し
        {"url": "https://example.com/c", "image": "https://img.example.com/old.jpg"},
    ]

    build_news.merge_existing_images(articles, existing)

    assert articles[0]["image"] == "https://img.example.com/a.jpg"
    assert articles[1]["image"] is None
    # 既に image を持つ記事は上書きしない
    assert articles[2]["image"] == "https://img.example.com/new.jpg"


def test_enrich_images_limits_per_feed_and_skips_existing() -> None:
    og_html = '<meta property="og:image" content="https://img.example.com/x.jpg">'
    articles = [
        {"url": f"https://example.com/en/{index}", "lang": "en", "image": None}
        for index in range(15)
    ] + [
        {"url": f"https://example.com/ja/{index}", "lang": "ja", "image": None}
        for index in range(5)
    ]
    # en の先頭2件は前回取得済み → 再取得しない
    articles[0]["image"] = "https://img.example.com/cached0.jpg"
    articles[1]["image"] = "https://img.example.com/cached1.jpg"
    session = FakeSession(
        {article["url"]: og_html for article in articles}
    )

    fetched = build_news.enrich_images(session, articles, limit_per_feed=10)  # type: ignore[arg-type]

    # en: 上位10件のうち未取得の8件 + ja: 5件 = 13リクエスト
    assert len(session.calls) == 13
    assert fetched == 13
    assert articles[0]["image"] == "https://img.example.com/cached0.jpg"
    assert articles[9]["image"] == "https://img.example.com/x.jpg"
    # 上位10件を超えた en 記事は取得対象外
    assert articles[10]["image"] is None
    assert all(a["image"] for a in articles if a["lang"] == "ja")


def test_enrich_images_stops_on_rate_limit() -> None:
    class FakeHTTPError(Exception):
        def __init__(self) -> None:
            super().__init__("429 Too Many Requests")
            self.response = type("R", (), {"status_code": 429})()

    articles = [
        {"url": f"https://example.com/{index}", "lang": "en", "image": None}
        for index in range(3)
    ]
    session = FakeSession({"https://example.com/0": FakeHTTPError()})

    fetched = build_news.enrich_images(session, articles)  # type: ignore[arg-type]

    # 1件目で 429 → 残りの記事は取得を試みない
    assert fetched == 0
    assert session.calls == ["https://example.com/0"]
    assert all(article["image"] is None for article in articles)


def test_enrich_images_failure_leaves_image_null() -> None:
    articles = [
        {"url": "https://example.com/fail", "lang": "en", "image": None},
        {"url": "https://example.com/error", "lang": "en", "image": None},
    ]
    session = FakeSession(
        {"https://example.com/error": ConnectionError("boom")}
        # /fail は未登録 → HTTP エラー扱い
    )

    fetched = build_news.enrich_images(session, articles)  # type: ignore[arg-type]

    assert fetched == 0
    assert articles[0]["image"] is None
    assert articles[1]["image"] is None
