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
    assert kwargs["json"]["text"] == "🏁 試合終了"


def test_bot_client_returns_false_on_slack_error() -> None:
    session = MagicMock()
    session.post.return_value = _response(ok=False, error="not_in_channel")
    client = SlackBotClient(token="xoxb-test", channel="C123", session=session)

    assert client.send(PAYLOAD) is False


def test_post_message_returns_response_with_ts() -> None:
    session = MagicMock()
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"ok": True, "channel": "C123", "ts": "111.222"}
    session.post.return_value = response
    client = SlackBotClient(token="xoxb-test", channel="C123", session=session)

    data = client.post_message(PAYLOAD)

    assert data is not None
    assert data["ts"] == "111.222"


def test_post_message_returns_none_on_error() -> None:
    session = MagicMock()
    session.post.return_value = _response(ok=False, error="channel_not_found")
    client = SlackBotClient(token="xoxb-test", channel="C123", session=session)

    assert client.post_message(PAYLOAD) is None


def test_add_reaction_succeeds() -> None:
    session = MagicMock()
    session.post.return_value = _response(ok=True)
    client = SlackBotClient(token="xoxb-test", channel="C123", session=session)

    assert client.add_reaction("111.222", "jp") is True
    _, kwargs = session.post.call_args
    assert kwargs["json"] == {
        "channel": "C123",
        "timestamp": "111.222",
        "name": "jp",
    }


def test_add_reaction_already_reacted_is_success() -> None:
    session = MagicMock()
    session.post.return_value = _response(ok=False, error="already_reacted")
    client = SlackBotClient(token="xoxb-test", channel="C123", session=session)

    assert client.add_reaction("111.222", "jp") is True


def test_add_reaction_returns_false_on_other_error() -> None:
    session = MagicMock()
    session.post.return_value = _response(ok=False, error="invalid_name")
    client = SlackBotClient(token="xoxb-test", channel="C123", session=session)

    assert client.add_reaction("111.222", "nope") is False


def test_get_reactions_returns_data() -> None:
    session = MagicMock()
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "ok": True,
        "message": {"reactions": [{"name": "jp", "count": 3}]},
    }
    session.get.return_value = response
    client = SlackBotClient(token="xoxb-test", channel="C123", session=session)

    data = client.get_reactions("111.222")

    assert data is not None
    assert data["message"]["reactions"][0]["count"] == 3


def test_get_reactions_returns_none_on_error() -> None:
    session = MagicMock()
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"ok": False, "error": "message_not_found"}
    session.get.return_value = response
    client = SlackBotClient(token="xoxb-test", channel="C123", session=session)

    assert client.get_reactions("111.222") is None


def test_bot_client_requires_token_and_channel() -> None:
    with pytest.raises(ValueError):
        SlackBotClient(token="xoxb-test", channel=None)


def test_fallback_text_uses_first_block_first_line() -> None:
    # header が無い場合は最初の mrkdwn セクション先頭行を記号除去して使う
    assert fallback_text(PAYLOAD) == "🏁 試合終了"
    assert fallback_text({"blocks": []}) == "W杯通知"


def test_fallback_text_prefers_header_plain_text() -> None:
    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🔔 まもなくキックオフ",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ">🇯🇵 *日本*  vs  🇳🇱 オランダ\n>🕔 `5:00` KO",
                },
            },
        ]
    }
    assert fallback_text(payload) == "🔔 まもなくキックオフ"


def test_fallback_text_strips_quote_bold_code_and_links() -> None:
    # header が無いとき: 引用記号(>)・太字(*)・コード(`)・リンクを除去する
    payload = {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ">🇯🇵 *日本*  `2 - 1`  オランダ\n>🎉 *日本、勝利！*",
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "▶️ <https://example.com|ハイライト>",
                    }
                ],
            },
        ]
    }
    assert fallback_text(payload) == "🇯🇵 日本  2 - 1  オランダ"


def test_fallback_text_keeps_link_display_name() -> None:
    payload = {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "<https://example.com/x|順位表> を見てね",
                },
            }
        ]
    }
    assert fallback_text(payload) == "順位表 を見てね"


def test_create_slack_client_prefers_bot_token(monkeypatch) -> None:
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_CHANNEL_ID", "C123")
    assert isinstance(create_slack_client(dry_run=False), SlackBotClient)

    monkeypatch.delenv("SLACK_BOT_TOKEN")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/x")
    assert isinstance(create_slack_client(dry_run=False), SlackWebhookClient)
