from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.main import create_slack_client
from src.slack import SlackBotClient, SlackWebhookClient, fallback_text

PAYLOAD = {
    "blocks": [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "🏁 *試合終了*\n詳細行"},
        }
    ]
}


def _response(ok: bool, error: str | None = None, channel: str = "C123"):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = (
        {"ok": True, "channel": channel} if ok else {"ok": False, "error": error}
    )
    return response


def test_bot_client_posts_to_chat_post_message() -> None:
    session = MagicMock()
    session.post.return_value = _response(ok=True)
    client = SlackBotClient(token="xoxb-test", channel="C123", session=session)

    assert client.send(PAYLOAD) is True

    args, kwargs = session.post.call_args
    assert args[0] == "https://slack.com/api/chat.postMessage"
    assert kwargs["headers"]["Authorization"] == "Bearer xoxb-test"
    assert kwargs["json"]["channel"] == "C123"
    assert kwargs["json"]["blocks"] == PAYLOAD["blocks"]
    assert kwargs["json"]["text"] == "🏁 *試合終了*"


def test_bot_client_returns_false_on_slack_error() -> None:
    session = MagicMock()
    session.post.return_value = _response(ok=False, error="not_in_channel")
    client = SlackBotClient(token="xoxb-test", channel="C123", session=session)

    assert client.send(PAYLOAD) is False


def test_bot_client_requires_token_and_channel() -> None:
    with pytest.raises(ValueError):
        SlackBotClient(token="xoxb-test", channel=None)


def test_fallback_text_uses_first_block_first_line() -> None:
    assert fallback_text(PAYLOAD) == "🏁 *試合終了*"
    assert fallback_text({"blocks": []}) == "W杯通知"


def test_create_slack_client_prefers_bot_token(monkeypatch) -> None:
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_CHANNEL_ID", "C123")
    assert isinstance(create_slack_client(dry_run=False), SlackBotClient)

    monkeypatch.delenv("SLACK_BOT_TOKEN")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/x")
    assert isinstance(create_slack_client(dry_run=False), SlackWebhookClient)
