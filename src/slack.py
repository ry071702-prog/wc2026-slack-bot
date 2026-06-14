from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Optional, Protocol

import requests

from src.messages import (
    DIGEST_CONTEXT,
    VIEWING_TEXT,
    VIEWING_TEXT_JAPAN,
    date_label,
    digest_match_line,
    digest_title,
    japan_poll_result_text,
    japan_poll_text,
    prematch_text,
    result_context,
    result_text,
)
from src.providers.base import Match

Payload = dict[str, Any]

# 対戦カード画像 (build_matchups.py が GitHub Pages にデプロイする PNG) の配信元。
MATCHUP_IMAGE_BASE_URL = (
    "https://ry071702-prog.github.io/wc2026-slack-bot/data/matchups"
)


def matchup_image_block(
    match_id: Any,
    session: requests.Session,
    base_url: str = MATCHUP_IMAGE_BASE_URL,
    timeout: float = 5.0,
) -> Optional[dict[str, Any]]:
    """対戦カード画像の image ブロックを返す。

    Slack の image ブロックは image_url が到達不能 (404 等) だと
    invalid_blocks でメッセージ全体が失敗するため、HEAD で 200 を確認できた
    ときだけブロックを返す。確認失敗・ネットワーク例外時は None (画像なしで投稿)。
    """
    url = f"{base_url}/{match_id}.png"
    try:
        response = session.head(url, timeout=timeout, allow_redirects=True)
    except requests.RequestException as exc:
        print(f"matchup image HEAD failed for {match_id}: {exc}")
        return None
    if response.status_code != 200:
        print(
            f"matchup image not available for {match_id}: "
            f"HTTP {response.status_code}"
        )
        return None
    return {"type": "image", "image_url": url, "alt_text": "対戦カード"}


class SlackSender(Protocol):
    dry_run: bool

    def send(self, payload: Payload) -> bool:
        """Send or print a Slack payload."""


def build_digest_payload(
    matches: list[Match],
    day: date,
    tomorrow_matches: Optional[list[Match]] = None,
    tomorrow: Optional[date] = None,
) -> Payload:
    japan_matches = sorted(
        (match for match in matches if match.is_japan),
        key=lambda match: match.utc_kickoff,
    )
    other_matches = sorted(
        (match for match in matches if not match.is_japan),
        key=lambda match: match.utc_kickoff,
    )
    blocks: list[dict[str, Any]] = [_header(digest_title(day))]

    if japan_matches:
        blocks.append(_section("\n".join(map(digest_match_line, japan_matches))))
        blocks.append({"type": "divider"})

    if other_matches:
        blocks.append(
            _section(
                "*きょうの試合*\n"
                + "\n".join(map(digest_match_line, other_matches))
            )
        )
    elif not japan_matches:
        blocks.append(_section("本日の試合はありません。"))

    if tomorrow_matches and tomorrow:
        ordered = sorted(
            tomorrow_matches, key=lambda match: match.utc_kickoff
        )
        blocks.append({"type": "divider"})
        blocks.append(
            _section(
                f"📅 *明日（{date_label(tomorrow)}）の試合*\n"
                + "\n".join(map(digest_match_line, ordered))
            )
        )

    blocks.append(_context(DIGEST_CONTEXT))
    return {"blocks": blocks}


def build_prematch_payload(
    match: Match,
    mention_japan: bool = False,
    image_block: Optional[dict[str, Any]] = None,
) -> Payload:
    viewing = VIEWING_TEXT_JAPAN if match.is_japan else VIEWING_TEXT
    blocks: list[dict[str, Any]] = [
        _header("🔔 まもなくキックオフ"),
        _section(prematch_text(match, mention_japan)),
    ]
    if image_block:
        blocks.append(image_block)
    blocks.append(_context(viewing))
    return {"blocks": blocks}


def build_result_payload(match: Match) -> Payload:
    return {
        "blocks": [
            _header("🏁 試合終了"),
            _section(result_text(match)),
            _context(result_context(match)),
        ]
    }


def build_poll_payload(
    match: Match, image_block: Optional[dict[str, Any]] = None
) -> Payload:
    blocks: list[dict[str, Any]] = [
        _header("🗳️ 勝敗予想 受付中"),
        _section(japan_poll_text(match)),
    ]
    if image_block:
        blocks.append(image_block)
    return {"blocks": blocks}


def build_poll_result_payload(
    match: Match,
    votes_jp: int,
    votes_draw: int,
    votes_opp: int,
    winner_names: Optional[list[str]] = None,
    winner_extra: int = 0,
) -> Payload:
    return {
        "blocks": [
            _header("📊 予想結果発表"),
            _section(
                japan_poll_result_text(
                    match,
                    votes_jp,
                    votes_draw,
                    votes_opp,
                    winner_names=winner_names,
                    winner_extra=winner_extra,
                )
            ),
        ]
    }


class SlackBotClient:
    """Bot Token (xoxb-) で chat.postMessage する送信クライアント。"""

    API_URL = "https://slack.com/api/chat.postMessage"
    REACTIONS_ADD_URL = "https://slack.com/api/reactions.add"
    REACTIONS_GET_URL = "https://slack.com/api/reactions.get"
    AUTH_TEST_URL = "https://slack.com/api/auth.test"
    USERS_INFO_URL = "https://slack.com/api/users.info"

    def __init__(
        self,
        token: Optional[str],
        channel: Optional[str],
        dry_run: bool = False,
        session: Optional[requests.Session] = None,
        timeout: float = 10.0,
    ) -> None:
        if not dry_run and not (token and channel):
            raise ValueError(
                "SLACK_BOT_TOKEN and SLACK_CHANNEL_ID are required unless DRY_RUN=true"
            )
        self.token = token or ""
        self.channel = channel or ""
        self.dry_run = dry_run
        self.session = session or requests.Session()
        self.timeout = timeout

    def post_message(self, payload: Payload) -> Optional[dict[str, Any]]:
        """chat.postMessage を叩き、成功時はレスポンス JSON 全体 (ts 含む) を返す。失敗時 None。"""
        if self.dry_run:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            print("Slack POST skipped: DRY_RUN=true")
            return {"ok": True, "ts": "DRYRUN", "channel": self.channel}

        try:
            response = self.session.post(
                self.API_URL,
                headers={"Authorization": f"Bearer {self.token}"},
                json={
                    "channel": self.channel,
                    "blocks": payload["blocks"],
                    "text": fallback_text(payload),
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"Slack chat.postMessage failed: {exc}")
            return None

        if not data.get("ok"):
            error = data.get("error")
            blocks = payload.get("blocks", [])
            # HEAD200でもSlackが画像を拒否する場合(サイズ/content-type/TOCTOU)に備え、
            # invalid_blocks のときは画像ブロックを外して必ずテキストを届ける。
            if error == "invalid_blocks" and any(
                b.get("type") == "image" for b in blocks
            ):
                print(
                    "Slack rejected message with image (invalid_blocks); "
                    "retrying without the matchup image"
                )
                return self.post_message(
                    {"blocks": [b for b in blocks if b.get("type") != "image"]}
                )
            print(f"Slack chat.postMessage failed: {error}")
            return None

        print(f"Slack chat.postMessage succeeded: channel={data.get('channel')}")
        return data

    def send(self, payload: Payload) -> bool:
        return self.post_message(payload) is not None

    def add_reaction(self, ts: str, name: str) -> bool:
        """reactions.add。already_reacted は成功扱い (True)。"""
        if self.dry_run:
            print(f"Slack reactions.add skipped: DRY_RUN=true (name={name} ts={ts})")
            return True

        try:
            response = self.session.post(
                self.REACTIONS_ADD_URL,
                headers={"Authorization": f"Bearer {self.token}"},
                json={"channel": self.channel, "timestamp": ts, "name": name},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"Slack reactions.add failed: {exc}")
            return False

        if not data.get("ok"):
            error = data.get("error")
            if error == "already_reacted":
                return True
            print(f"Slack reactions.add failed: {error}")
            return False
        return True

    def get_reactions(self, ts: str) -> Optional[dict[str, Any]]:
        """reactions.get (full=true)。成功時はレスポンス JSON 全体を返す。失敗/未取得時 None。"""
        if self.dry_run:
            # 空のリアクション集合を返し、集計発表メッセージを dry_run でも
            # プレビューできるようにする (None だと集計パスがスキップされる)。
            print(f"Slack reactions.get stubbed: DRY_RUN=true (ts={ts})")
            return {"ok": True, "message": {"reactions": []}}

        try:
            response = self.session.get(
                self.REACTIONS_GET_URL,
                headers={"Authorization": f"Bearer {self.token}"},
                params={
                    "channel": self.channel,
                    "timestamp": ts,
                    "full": "true",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"Slack reactions.get failed: {exc}")
            return None

        if not data.get("ok"):
            print(f"Slack reactions.get failed: {data.get('error')}")
            return None
        return data

    def bot_user_id(self) -> Optional[str]:
        """auth.test で自分 (Bot) の user_id を取得 (1回だけ叩いてキャッシュ)。"""
        if self.dry_run:
            return None
        if getattr(self, "_bot_user_id", None) is not None:
            return self._bot_user_id
        try:
            response = self.session.post(
                self.AUTH_TEST_URL,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"Slack auth.test failed: {exc}")
            return None
        self._bot_user_id = data.get("user_id") if data.get("ok") else None
        return self._bot_user_id

    def user_display_name(self, user_id: str) -> Optional[str]:
        """users.info で表示名 (display_name → real_name → name) を解決する。"""
        if self.dry_run:
            return user_id
        try:
            response = self.session.get(
                self.USERS_INFO_URL,
                headers={"Authorization": f"Bearer {self.token}"},
                params={"user": user_id},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"Slack users.info failed: {exc}")
            return None
        if not data.get("ok"):
            return None
        user = data.get("user") or {}
        profile = user.get("profile") or {}
        return (
            profile.get("display_name")
            or profile.get("real_name")
            or user.get("real_name")
            or user.get("name")
        )


_LINK_RE = re.compile(r"<([^|>]*)\|([^>]*)>")


def _strip_mrkdwn(line: str) -> str:
    """mrkdwn 記号を除去してプッシュ通知向けのクリーンな1行にする。
    行頭の引用記号(>)・リンク(<URL|表示>→表示名)・太字/斜体/コード記号を落とす。"""
    line = line.lstrip(">").strip()
    line = _LINK_RE.sub(r"\2", line)
    for symbol in ("*", "_", "`"):
        line = line.replace(symbol, "")
    return line.strip()


def fallback_text(payload: Payload) -> str:
    """通知プレビュー用のテキスト (blocks非対応クライアント向け)。
    header があればその plain_text を、無ければ最初の mrkdwn セクション先頭行を
    記号除去して採用する。"""
    blocks = payload.get("blocks", [])
    for block in blocks:
        if block.get("type") == "header":
            text = block.get("text", {}).get("text")
            if text:
                return _strip_mrkdwn(text)
    for block in blocks:
        text_obj = block.get("text", {})
        if text_obj.get("type") == "mrkdwn":
            cleaned = _strip_mrkdwn(text_obj.get("text", "").split("\n", 1)[0])
            if cleaned:
                return cleaned
    return "W杯通知"


class SlackWebhookClient:
    def __init__(
        self,
        webhook_url: Optional[str],
        dry_run: bool = False,
        session: Optional[requests.Session] = None,
        timeout: float = 10.0,
    ) -> None:
        if not dry_run and not webhook_url:
            raise ValueError("SLACK_WEBHOOK_URL is required unless DRY_RUN=true")
        self.webhook_url = webhook_url or ""
        self.dry_run = dry_run
        self.session = session or requests.Session()
        self.timeout = timeout

    def send(self, payload: Payload) -> bool:
        if self.dry_run:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            print("Slack POST skipped: DRY_RUN=true")
            return True

        try:
            response = self.session.post(
                self.webhook_url,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"Slack POST failed: {exc}")
            return False

        print(f"Slack POST succeeded: status={response.status_code}")
        return True


def _header(text: str) -> dict[str, Any]:
    return {
        "type": "header",
        "text": {"type": "plain_text", "text": text, "emoji": True},
    }


def _section(text: str) -> dict[str, Any]:
    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": text},
    }


def _context(text: str) -> dict[str, Any]:
    return {
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": text}],
    }
