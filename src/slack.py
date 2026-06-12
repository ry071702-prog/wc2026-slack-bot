from __future__ import annotations

import json
from datetime import date
from typing import Any, Optional, Protocol

import requests

from src.messages import (
    DIGEST_CONTEXT,
    date_label,
    digest_match_line,
    digest_title,
    prematch_text,
    result_text,
)
from src.providers.base import Match

Payload = dict[str, Any]


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
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": digest_title(day)},
        }
    ]

    if japan_matches:
        blocks.append(_section("\n".join(map(digest_match_line, japan_matches))))
        blocks.append({"type": "divider"})

    if other_matches:
        blocks.append(_section("\n".join(map(digest_match_line, other_matches))))
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

    blocks.append(
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": DIGEST_CONTEXT}],
        }
    )
    return {"blocks": blocks}


def build_prematch_payload(
    match: Match, mention_japan: bool = False
) -> Payload:
    return {"blocks": [_section(prematch_text(match, mention_japan))]}


def build_result_payload(match: Match) -> Payload:
    return {"blocks": [_section(result_text(match))]}


class SlackBotClient:
    """Bot Token (xoxb-) で chat.postMessage する送信クライアント。"""

    API_URL = "https://slack.com/api/chat.postMessage"

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

    def send(self, payload: Payload) -> bool:
        if self.dry_run:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            print("Slack POST skipped: DRY_RUN=true")
            return True

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
            return False

        if not data.get("ok"):
            print(f"Slack chat.postMessage failed: {data.get('error')}")
            return False

        print(f"Slack chat.postMessage succeeded: channel={data.get('channel')}")
        return True


def fallback_text(payload: Payload) -> str:
    """通知プレビュー用のテキスト (blocks非対応クライアント向け) を先頭ブロックから作る。"""
    for block in payload.get("blocks", []):
        text = block.get("text", {}).get("text")
        if text:
            return text.split("\n", 1)[0]
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


def _section(text: str) -> dict[str, Any]:
    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": text},
    }
