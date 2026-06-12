"""日本戦の公式スタメンを自動取得して投稿可能にする (notify.yml の5分毎cronに相乗り)。

2段構えの自動化:
  1. キックオフ50分前〜20分前 (取得試行窓):
     Google News RSS → 記事本文 → Gemini Flash で先発11人+フォーメーション抽出
     → data/squads.json の26人と照合して有効なら data/lineups/auto.json を書き
     "LINEUP_READY=auto" を stdout に出す (失敗は次の5分で再試行)
  2. キックオフ20分前〜5分前 (フォールバック窓):
     公式が取れていなければ auto_config.json の fallback_lineup (予想スタメン) を
     "LINEUP_READY=<name> FALLBACK=1" として出す (保険)

投稿と state 更新は workflow 側 (notify.yml) が行う。二重投稿防止は
state/notified.json の "lineup" 配列 (投稿済み match_id) で判定する。

設計上の注意:
- 毎5分実行されるため、窓外は "no window" を出して即 exit 0 (超軽量)
- ネットワーク/LLM のエラーはすべて握って exit 0 (notify 本体を壊さない)
- 氏名・背番号は squads.json 側の値を採用する (LLM出力は照合キーにのみ使う)

env: GOOGLE_API_KEY (Gemini), GEMINI_MODEL (任意, 既定 gemini-2.5-flash)
CLI: python scripts/fetch_lineup_auto.py
"""
from __future__ import annotations

import html as html_module
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import quote

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.build_news import (  # noqa: E402
    IMAGE_USER_AGENT,
    parse_feed,
    resolve_google_news_url,
)
from src.state import StateStore  # noqa: E402

JST = timezone(timedelta(hours=9))

CONFIG_PATH = ROOT_DIR / "data" / "lineups" / "auto_config.json"
SQUADS_PATH = ROOT_DIR / "data" / "squads.json"
STATE_PATH = ROOT_DIR / "state" / "notified.json"
AUTO_LINEUP_PATH = ROOT_DIR / "data" / "lineups" / "auto.json"
LINEUPS_DIR = ROOT_DIR / "data" / "lineups"

TEAM = "Japan"

# 窓の定義 (キックオフからの分数)
FETCH_WINDOW_START_MIN = 50  # ここから公式スタメンの取得を試行
FALLBACK_WINDOW_START_MIN = 20  # ここからは予想スタメンの投稿に切り替え
WINDOW_END_MIN = 5  # ここを過ぎたら何もしない (試合直前)

# 記事収集
RSS_URL_TEMPLATE = (
    "https://news.google.com/rss/search?q={query}&hl=ja&gl=JP&ceid=JP:ja"
)
MAX_ARTICLES = 5
ARTICLE_MAX_AGE_HOURS = 3
ARTICLE_TEXT_LIMIT = 5000
ARTICLE_TEXT_MIN = 200  # これ未満は本文が取れていないと見なす
REQUEST_TIMEOUT = 15

# Gemini (REST)
GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent"
)
GEMINI_DEFAULT_MODEL = "gemini-2.5-flash"
GEMINI_FALLBACK_MODEL = "gemini-2.0-flash"
GEMINI_TIMEOUT = 60

FORMATION_RE = re.compile(r"^\d(-\d){2,3}$")


# --- 窓判定 (純関数) ---


def classify_window(now: datetime, kickoff: datetime) -> Optional[str]:
    """現在時刻がどの窓にいるかを返す ("fetch" / "fallback" / None)。

    - fetch: KO-50分 <= now < KO-20分 (公式スタメンの取得試行)
    - fallback: KO-20分 <= now < KO-5分 (予想スタメンの投稿)
    """
    fetch_start = kickoff - timedelta(minutes=FETCH_WINDOW_START_MIN)
    fallback_start = kickoff - timedelta(minutes=FALLBACK_WINDOW_START_MIN)
    window_end = kickoff - timedelta(minutes=WINDOW_END_MIN)
    if fetch_start <= now < fallback_start:
        return "fetch"
    if fallback_start <= now < window_end:
        return "fallback"
    return None


def find_active_match(
    config: dict[str, Any], now: datetime
) -> Optional[tuple[dict[str, Any], str]]:
    """auto_config の matches から「いま窓内」の試合と窓種別を返す。"""
    for match in config.get("matches", []):
        try:
            kickoff = datetime.fromisoformat(match["kickoff_jst"])
        except (KeyError, TypeError, ValueError):
            continue
        window = classify_window(now, kickoff)
        if window:
            return match, window
    return None


# --- 照合 (純関数) ---


def normalize_name(name: str) -> str:
    """照合用に空白 (全角含む) を除去する。"""
    return re.sub(r"[\s　]+", "", name)


def match_player(
    name: str, squad: list[dict[str, Any]]
) -> Optional[dict[str, Any]]:
    """抽出された選手名を squad (26人) の1人に照合する。

    name_ja の完全一致を優先し、無ければ部分一致 (姓のみ等のゆらぎ)。
    部分一致は「26人中で一意に決まる場合のみ」許容し、曖昧なら None。
    """
    target = normalize_name(name)
    if not target:
        return None
    exact = [
        member
        for member in squad
        if normalize_name(str(member.get("name_ja", ""))) == target
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None
    partial = [
        member
        for member in squad
        if target in normalize_name(str(member.get("name_ja", "")))
        or normalize_name(str(member.get("name_ja", ""))) in target
    ]
    if len(partial) == 1:
        return partial[0]
    return None


def match_players(
    names: list[str], squad: list[dict[str, Any]]
) -> Optional[list[dict[str, Any]]]:
    """先発11人を照合する。11人全員が一意に照合でき重複が無い場合のみ有効。"""
    if len(names) != 11:
        return None
    members: list[dict[str, Any]] = []
    for name in names:
        member = match_player(str(name), squad)
        if member is None:
            return None
        members.append(member)
    numbers = [member.get("number") for member in members]
    if len(set(numbers)) != 11:
        return None  # 同一選手への重複照合
    return members


def order_players(
    members: list[dict[str, Any]]
) -> Optional[list[dict[str, Any]]]:
    """GK がちょうど1人いることを検証し、GK を先頭に並べ替える。

    GK 以外は元の順序 (LLM が出した「後ろのラインから前へ」) を保つ。
    """
    goalkeepers = [m for m in members if m.get("position") == "GK"]
    if len(goalkeepers) != 1:
        return None
    keeper = goalkeepers[0]
    return [keeper] + [m for m in members if m is not keeper]


def validate_formation(formation: Any) -> bool:
    """"4-3-3" 形式 (3〜4ライン) かつフィールドプレイヤー合計10人なら True。"""
    if not isinstance(formation, str) or not FORMATION_RE.match(formation):
        return False
    return sum(int(part) for part in formation.split("-")) == 10


def build_lineup(
    match_config: dict[str, Any],
    formation: str,
    members: list[dict[str, Any]],
) -> dict[str, Any]:
    """照合済みメンバーから post_lineup.py 互換の lineup dict を作る。

    氏名・背番号・ポジションはすべて squads.json 側の値を採用する。
    """
    return {
        "title": "日本 スタメン",
        "team": TEAM,
        "opponent": match_config["opponent"],
        "kickoff_jst": match_config["kickoff_jst"],
        "stage": match_config["stage"],
        "formation": formation,
        "players": [
            {
                "number": member["number"],
                "name": member["name_ja"],
                "position": member["position"],
            }
            for member in members
        ],
    }


# --- Gemini 抽出 ---


def build_extraction_prompt(opponent: str, article_text: str) -> str:
    return (
        "以下のニュース記事から、サッカー日本代表の"
        f"{opponent}戦の「公式発表された先発11人 (スタメン)」と"
        "フォーメーションを抽出してください。\n"
        "ルール:\n"
        "- 公式発表済みのスタメンが明記されている場合のみ "
        '{"found": true, "formation": "4-3-3", '
        '"players": ["選手名", ...]} の形式で返す (players は11人)\n'
        "- players は GK を先頭に、最終ライン (DF) から前線 (FW) へ、"
        "各ライン内は左から右の順に並べる\n"
        "- 選手名は記事に書かれた日本語表記をそのまま使う\n"
        "- 予想スタメン・予想布陣しか書かれていない記事や、"
        "先発11人が揃って書かれていない記事の場合は "
        '{"found": false} を返す\n'
        "- JSON のみを出力する\n"
        f"\n記事:\n{article_text}"
    )


def build_gemini_request(
    model: str, prompt: str
) -> tuple[str, dict[str, Any]]:
    """Gemini generateContent の (URL, JSONペイロード) を作る (キーは含めない)。"""
    url = GEMINI_ENDPOINT.format(model=model)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0,
        },
    }
    return url, payload


def parse_gemini_response(data: dict[str, Any]) -> Optional[dict[str, Any]]:
    """generateContent のレスポンスから JSON テキストを取り出して parse する。"""
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def call_gemini(
    session: requests.Session,
    api_key: str,
    prompt: str,
    model: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Gemini を呼んで抽出JSONを返す。既定モデルが404なら旧モデルで再試行。"""
    models = [model or os.environ.get("GEMINI_MODEL", GEMINI_DEFAULT_MODEL)]
    if GEMINI_FALLBACK_MODEL not in models:
        models.append(GEMINI_FALLBACK_MODEL)
    for candidate_model in models:
        url, payload = build_gemini_request(candidate_model, prompt)
        response = session.post(
            url,
            params={"key": api_key},
            json=payload,
            timeout=GEMINI_TIMEOUT,
        )
        if response.status_code == 404:
            print(f"gemini model not found: {candidate_model}; trying fallback")
            continue
        response.raise_for_status()
        return parse_gemini_response(response.json())
    return None


# --- 記事収集 ---

_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style|noscript)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(html_text: str) -> str:
    """HTML からタグを除去してプレーンテキストにする。"""
    text = _SCRIPT_STYLE_RE.sub(" ", html_text)
    text = _TAG_RE.sub(" ", text)
    text = html_module.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def rss_url(opponent: str) -> str:
    query = quote(f"日本代表 スタメン {opponent}")
    return RSS_URL_TEMPLATE.format(query=query)


def fetch_candidate_articles(
    session: requests.Session, opponent: str, now: datetime
) -> list[dict[str, Any]]:
    """Google News RSS から直近3時間以内の記事を新しい順に最大5件返す。"""
    response = session.get(
        rss_url(opponent),
        headers={"User-Agent": IMAGE_USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    articles = parse_feed(response.text, "ja")  # 新しい順にソート済み
    cutoff = now.astimezone(timezone.utc) - timedelta(
        hours=ARTICLE_MAX_AGE_HOURS
    )
    recent = [
        article
        for article in articles
        if article.get("published_at")
        and datetime.fromisoformat(article["published_at"]) >= cutoff
    ]
    return recent[:MAX_ARTICLES]


def fetch_article_text(
    session: requests.Session, url: str
) -> Optional[str]:
    """記事URL (Google News リダイレクト) を解決して本文テキストを返す。"""
    resolved = resolve_google_news_url(session, url)
    if not resolved:
        return None
    response = session.get(
        resolved,
        headers={
            "User-Agent": IMAGE_USER_AGENT,
            "Accept-Language": "ja,en;q=0.8",
        },
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    )
    response.raise_for_status()
    text = strip_html(response.text)
    if len(text) < ARTICLE_TEXT_MIN:
        return None
    return text[:ARTICLE_TEXT_LIMIT]


# --- 抽出 → 照合 (LLM呼び出しは注入可能にしてテスト可能に) ---


def extract_lineup_from_text(
    article_text: str,
    match_config: dict[str, Any],
    squad: list[dict[str, Any]],
    call_llm: Callable[[str], Optional[dict[str, Any]]],
) -> Optional[dict[str, Any]]:
    """記事テキスト1本から有効な lineup dict を作る。無効なら None。"""
    extracted = call_llm(
        build_extraction_prompt(match_config["opponent"], article_text)
    )
    if not extracted or not extracted.get("found"):
        return None
    formation = extracted.get("formation")
    if not validate_formation(formation):
        print(f"invalid formation from LLM: {formation!r}")
        return None
    players = extracted.get("players")
    if not isinstance(players, list):
        return None
    members = match_players([str(name) for name in players], squad)
    if members is None:
        print("players did not uniquely match the 26-man squad")
        return None
    ordered = order_players(members)
    if ordered is None:
        print("lineup must contain exactly one GK")
        return None
    return build_lineup(match_config, str(formation), ordered)


def attempt_auto_fetch(
    session: requests.Session,
    api_key: str,
    match_config: dict[str, Any],
    squad: list[dict[str, Any]],
    now: datetime,
) -> Optional[dict[str, Any]]:
    """ニュース記事から公式スタメンの抽出を試みる。成功時は lineup dict。"""
    articles = fetch_candidate_articles(session, match_config["opponent"], now)
    if not articles:
        print("no recent articles found")
        return None
    print(f"{len(articles)} candidate articles")
    for article in articles:
        title = str(article.get("title", ""))[:60]
        try:
            text = fetch_article_text(session, article["url"])
        except Exception as exc:  # noqa: BLE001 - 記事単位で握る
            print(f"article fetch failed: {title}: {exc}")
            continue
        if not text:
            print(f"article text unavailable: {title}")
            continue
        try:
            lineup = extract_lineup_from_text(
                text,
                match_config,
                squad,
                lambda prompt: call_gemini(session, api_key, prompt),
            )
        except Exception as exc:  # noqa: BLE001 - LLM呼び出しも記事単位で握る
            print(f"extraction failed: {title}: {exc}")
            continue
        if lineup:
            print(f"official lineup extracted from: {title}")
            return lineup
    return None


# --- エントリポイント ---


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def main(now: Optional[datetime] = None) -> int:
    now = now or datetime.now(JST)

    try:
        config = load_json(CONFIG_PATH)
    except (OSError, ValueError) as exc:
        print(f"auto_config unreadable: {exc}")
        return 0

    active = find_active_match(config, now)
    if not active:
        print("no window")
        return 0
    match_config, window = active
    match_id = int(match_config["match_id"])
    print(
        f"window={window} match_id={match_id} "
        f"opponent={match_config.get('opponent')}"
    )

    state = StateStore(STATE_PATH).load()
    if match_id in state["lineup"]:
        print("lineup already posted for this match")
        return 0

    if window == "fallback":
        name = str(match_config.get("fallback_lineup") or "sample")
        if not (LINEUPS_DIR / f"{name}.json").exists():
            print(f"fallback lineup missing: {name}.json")
            return 0
        print(f"LINEUP_MATCH_ID={match_id}")
        print(f"LINEUP_READY={name} FALLBACK=1")
        return 0

    # fetch 窓: 公式スタメンの取得試行
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("GOOGLE_API_KEY is not set; skip auto fetch")
        return 0
    try:
        squad = load_json(SQUADS_PATH).get(TEAM)
    except (OSError, ValueError) as exc:
        print(f"squads unreadable: {exc}")
        return 0
    if not isinstance(squad, list) or len(squad) != 26:
        print("Japan squad (26 players) unavailable; skip auto fetch")
        return 0

    try:
        lineup = attempt_auto_fetch(
            requests.Session(), api_key, match_config, squad, now
        )
    except Exception as exc:  # noqa: BLE001 - notify 本体を壊さない
        print(f"auto fetch failed: {exc}")
        return 0
    if not lineup:
        print("official lineup not confirmed yet; retry on next run")
        return 0

    AUTO_LINEUP_PATH.write_text(
        json.dumps(lineup, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"auto lineup saved: {AUTO_LINEUP_PATH}")
    print(f"LINEUP_MATCH_ID={match_id}")
    print("LINEUP_READY=auto")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
