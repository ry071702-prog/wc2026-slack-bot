"""Google News RSS からW杯関連記事を取得して data/news.json に保存する。

Google News RSS はブラウザから直接 fetch できない (CORS) ため、
ビルド時 (GitHub Actions) に取得して静的JSONとして配信する。
取得に失敗した場合は既存の data/news.json をそのまま残して正常終了する
(サイトは固定ソースカードだけでも成立する設計)。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

NEWS_PATH = ROOT_DIR / "data" / "news.json"
MAX_ARTICLES_PER_FEED = 20
REQUEST_TIMEOUT = 20
USER_AGENT = "wc2026-slack-bot/1.0 (+https://github.com/ry071702-prog/wc2026-slack-bot)"

# Google News RSS 2本 (en=英語・国際寄り / ja=日本語記事中心)
FEEDS: list[dict[str, str]] = [
    {
        "lang": "en",
        "url": (
            "https://news.google.com/rss/search"
            "?q=FIFA%20World%20Cup%202026&hl=en-US&gl=US&ceid=US:en"
        ),
    },
    {
        "lang": "ja",
        "url": (
            "https://news.google.com/rss/search"
            "?q=%E3%83%AF%E3%83%BC%E3%83%AB%E3%83%89%E3%82%AB%E3%83%83"
            "%E3%83%97%202026%20%E3%82%B5%E3%83%83%E3%82%AB%E3%83%BC"
            "&hl=ja&gl=JP&ceid=JP:ja"
        ),
    },
]


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


def parse_pub_date(value: Optional[str]) -> Optional[str]:
    """RFC 822 形式の pubDate を UTC の ISO 8601 文字列にする。"""
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def strip_source_suffix(title: str, source: str) -> str:
    """Google News のタイトル末尾の「 - 媒体名」を取り除く。"""
    suffix = f" - {source}"
    if source and title.endswith(suffix):
        return title[: -len(suffix)].rstrip()
    return title


def parse_feed(xml_text: str, lang: str) -> list[dict[str, Any]]:
    """RSS XML を記事リストに変換する (新しい順・最大20件)。"""
    root = ElementTree.fromstring(xml_text)
    articles: list[dict[str, Any]] = []
    for item in root.iterfind("./channel/item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        source = (item.findtext("source") or "").strip()
        if not title or not url:
            continue
        articles.append(
            {
                "title": strip_source_suffix(title, source),
                "source": source,
                "published_at": parse_pub_date(item.findtext("pubDate")),
                "url": url,
                "lang": lang,
            }
        )
    articles.sort(key=lambda article: article["published_at"] or "", reverse=True)
    return articles[:MAX_ARTICLES_PER_FEED]


def fetch_feed(session: requests.Session, url: str) -> str:
    response = session.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.text


def update_articles(
    session: requests.Session,
    existing_articles: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """全フィードを取得する。失敗したフィードは既存記事で代替する。

    戻り値は (記事リスト, 取得に成功したフィード数)。
    """
    articles: list[dict[str, Any]] = []
    fetched = 0
    for feed in FEEDS:
        try:
            xml_text = fetch_feed(session, feed["url"])
            parsed = parse_feed(xml_text, feed["lang"])
        except Exception as error:  # noqa: BLE001 - フィード単位で握りつぶす
            print(f"feed fetch failed ({feed['lang']}): {error}")
            parsed = [
                article
                for article in existing_articles
                if article.get("lang") == feed["lang"]
            ]
        else:
            fetched += 1
            print(f"feed fetched ({feed['lang']}): {len(parsed)} articles")
        articles.extend(parsed)
    return articles, fetched


def main() -> None:
    existing = load_json(NEWS_PATH)
    existing_articles = existing.get("articles", [])
    if not isinstance(existing_articles, list):
        existing_articles = []

    articles, fetched = update_articles(requests.Session(), existing_articles)
    if fetched == 0:
        # 全滅時は既存ファイルを残して正常終了 (固定ソースカードだけで成立)
        print("no feeds fetched; keep existing news.json")
        return

    payload = {
        "generated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "articles": articles,
    }
    save_json(NEWS_PATH, payload)
    print(f"news saved: {len(articles)} articles -> {NEWS_PATH}")


if __name__ == "__main__":
    main()
