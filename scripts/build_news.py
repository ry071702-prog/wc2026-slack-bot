"""Google News RSS からW杯関連記事を取得して data/news.json に保存する。

Google News RSS はブラウザから直接 fetch できない (CORS) ため、
ビルド時 (GitHub Actions) に取得して静的JSONとして配信する。
取得に失敗した場合は既存の data/news.json をそのまま残して正常終了する
(サイトは固定ソースカードだけでも成立する設計)。
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
from xml.etree import ElementTree

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

NEWS_PATH = ROOT_DIR / "data" / "news.json"
MAX_ARTICLES_PER_FEED = 20
REQUEST_TIMEOUT = 20
USER_AGENT = "wc2026-slack-bot/1.0 (+https://github.com/ry071702-prog/wc2026-slack-bot)"

# og:image 取得 (ベストエフォート)。実行時間を抑えるため各フィード上位のみ。
MAX_IMAGE_FETCH_PER_FEED = 10
IMAGE_REQUEST_TIMEOUT = 8
# Google News 内部APIへの連続アクセスで 429 になるのを避ける間隔 (実地確認済み)
IMAGE_FETCH_DELAY_SECONDS = 1.5
# 記事ページは bot UA を弾くサイトがあるため、一般的なブラウザ UA を使う
IMAGE_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

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
                "image": None,
            }
        )
    articles.sort(key=lambda article: article["published_at"] or "", reverse=True)
    return articles[:MAX_ARTICLES_PER_FEED]


# <meta property="og:image" content="..."> を属性順不同で拾う (標準ライブラリのみ)
_META_TAG_RE = re.compile(r"<meta\s[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(
    r"""([a-zA-Z:-]+)\s*=\s*("([^"]*)"|'([^']*)')""",
)


def extract_og_image(html_text: str) -> Optional[str]:
    """HTML から og:image (なければ twitter:image) の URL を抽出する。"""
    og_image: Optional[str] = None
    twitter_image: Optional[str] = None
    for tag in _META_TAG_RE.findall(html_text):
        attrs: dict[str, str] = {}
        for match in _ATTR_RE.finditer(tag):
            value = match.group(3) if match.group(3) is not None else match.group(4)
            attrs[match.group(1).lower()] = value
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        content = html.unescape((attrs.get("content") or "").strip())
        if not content or not content.startswith(("http://", "https://")):
            continue
        if key == "og:image" and og_image is None:
            og_image = content
        elif key in ("twitter:image", "twitter:image:src") and twitter_image is None:
            twitter_image = content
    return og_image or twitter_image


GOOGLE_NEWS_HOST = "news.google.com"
_BATCHEXECUTE_URL = (
    "https://news.google.com/_/DotsSplashUi/data/batchexecute"
)


def resolve_google_news_url(
    session: requests.Session, url: str
) -> Optional[str]:
    """Google News のリダイレクトURLを実記事URLに解決する。

    news.google.com の記事ページは HTTP リダイレクトではなく JS リダイレクト
    (実地確認済み: requests では interstitial に留まり、Google の汎用ロゴが
    og:image として返る)。そのため記事ページの署名 (data-n-a-sg / ts) を使い
    内部 API (batchexecute) で実URLを引く。失敗したら None。
    Google News 以外のURLはそのまま返す。
    """
    parsed = urlparse(url)
    if parsed.netloc != GOOGLE_NEWS_HOST:
        return url
    article_id = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    if not article_id:
        return None

    headers = {
        "User-Agent": IMAGE_USER_AGENT,
        "Accept-Language": "ja,en;q=0.8",
    }
    page = session.get(
        f"https://news.google.com/articles/{article_id}",
        headers=headers,
        timeout=IMAGE_REQUEST_TIMEOUT,
        allow_redirects=True,
    )
    page.raise_for_status()
    signature = re.search(r'data-n-a-sg="([^"]+)"', page.text)
    timestamp = re.search(r'data-n-a-ts="([^"]+)"', page.text)
    if not signature or not timestamp:
        return None

    payload = (
        '[[["Fbv4je","[\\"garturlreq\\",[[\\"X\\",\\"X\\",[\\"X\\",\\"X\\"],'
        "null,null,1,1,\\\"US:en\\\",null,1,null,null,null,null,null,0,1],"
        '\\"X\\",\\"X\\",1,[1,1,1],1,1,null,0,0,null,0],'
        f'\\"{article_id}\\",{timestamp.group(1)},\\"{signature.group(1)}\\"]"'
        ',null,"generic"]]]'
    )
    response = session.post(
        _BATCHEXECUTE_URL,
        headers={
            **headers,
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        },
        data={"f.req": payload},
        timeout=IMAGE_REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    for line in response.text.splitlines():
        if "garturlres" not in line:
            continue
        envelope = json.loads(line)
        inner = json.loads(envelope[0][2])
        target = inner[1] if len(inner) > 1 else None
        if isinstance(target, str) and target.startswith(("http://", "https://")):
            return target
    return None


class RateLimitedError(Exception):
    """Google から 429 を受けた (以降の画像取得を打ち切る)。"""


def fetch_article_image(session: requests.Session, url: str) -> Optional[str]:
    """記事URL (Google News リダイレクト) を辿って og:image を取る。失敗は None。"""
    try:
        resolved = resolve_google_news_url(session, url)
        if not resolved:
            return None
        response = session.get(
            resolved,
            headers={"User-Agent": IMAGE_USER_AGENT, "Accept-Language": "ja,en;q=0.8"},
            timeout=IMAGE_REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        response.raise_for_status()
        # 解決後も Google 内に留まる場合は汎用ロゴしか取れないので捨てる
        if urlparse(str(response.url)).netloc == GOOGLE_NEWS_HOST:
            return None
        return extract_og_image(response.text)
    except Exception as error:  # noqa: BLE001 - 画像はベストエフォート
        status = getattr(getattr(error, "response", None), "status_code", None)
        if status == 429:
            raise RateLimitedError(str(error)) from error
        print(f"image fetch failed: {url[:80]}...: {error}")
        return None


def merge_existing_images(
    articles: list[dict[str, Any]],
    existing_articles: list[dict[str, Any]],
) -> None:
    """前回取得済みの image を URL 一致でマージする (再取得を避ける)。"""
    image_by_url = {
        article.get("url"): article.get("image")
        for article in existing_articles
        if article.get("url") and article.get("image")
    }
    for article in articles:
        if not article.get("image"):
            article["image"] = image_by_url.get(article["url"])


def enrich_images(
    session: requests.Session,
    articles: list[dict[str, Any]],
    limit_per_feed: int = MAX_IMAGE_FETCH_PER_FEED,
    delay_seconds: float = 0.0,
) -> int:
    """各フィード (lang) の上位 limit 件だけ og:image を取得する。

    既に image があるもの (前回マージ分) はスキップ。
    戻り値は新規取得に成功した件数。
    """
    fetched = 0
    seen_by_lang: dict[str, int] = {}
    for article in articles:
        lang = str(article.get("lang") or "")
        position = seen_by_lang.get(lang, 0)
        seen_by_lang[lang] = position + 1
        if position >= limit_per_feed:
            continue
        if article.get("image"):
            continue
        if delay_seconds > 0:
            time.sleep(delay_seconds)
        try:
            image = fetch_article_image(session, article["url"])
        except RateLimitedError as error:
            # 429 が出たら以降は全て弾かれるため打ち切る (画像はベストエフォート)
            print(f"rate limited; stop image fetch: {error}")
            break
        if image:
            article["image"] = image
            fetched += 1
    return fetched


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

    session = requests.Session()
    articles, fetched = update_articles(session, existing_articles)
    if fetched == 0:
        # 全滅時は既存ファイルを残して正常終了 (固定ソースカードだけで成立)
        print("no feeds fetched; keep existing news.json")
        return

    # サムネ: 前回分をマージしてから、各フィード上位だけ新規取得する
    merge_existing_images(articles, existing_articles)
    new_images = enrich_images(
        session, articles, delay_seconds=IMAGE_FETCH_DELAY_SECONDS
    )
    total_images = sum(1 for article in articles if article.get("image"))
    print(f"images: {new_images} newly fetched, {total_images} total with image")

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
