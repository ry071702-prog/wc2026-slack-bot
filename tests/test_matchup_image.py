from __future__ import annotations

from unittest.mock import MagicMock

import requests

from src.slack import (
    MATCHUP_IMAGE_BASE_URL,
    build_poll_payload,
    build_prematch_payload,
    matchup_image_block,
)


def _head(status: int) -> MagicMock:
    response = MagicMock()
    response.status_code = status
    return response


def test_matchup_image_block_returns_block_on_200() -> None:
    session = MagicMock()
    session.head.return_value = _head(200)

    block = matchup_image_block(537357, session)

    assert block == {
        "type": "image",
        "image_url": f"{MATCHUP_IMAGE_BASE_URL}/537357.png",
        "alt_text": "対戦カード",
    }
    _, kwargs = session.head.call_args
    assert kwargs["allow_redirects"] is True


def test_matchup_image_block_returns_none_on_404() -> None:
    session = MagicMock()
    session.head.return_value = _head(404)

    assert matchup_image_block(537357, session) is None


def test_matchup_image_block_returns_none_on_exception() -> None:
    session = MagicMock()
    session.head.side_effect = requests.RequestException("network down")

    assert matchup_image_block(537357, session) is None


def test_matchup_image_block_custom_base_url() -> None:
    session = MagicMock()
    session.head.return_value = _head(200)

    block = matchup_image_block(99, session, base_url="https://x.test/m")

    assert block["image_url"] == "https://x.test/m/99.png"


# ---- payload への image ブロック挿入 -------------------------------------

IMAGE_BLOCK = {
    "type": "image",
    "image_url": "https://example.test/1.png",
    "alt_text": "対戦カード",
}


def test_prematch_payload_inserts_image(japan_match) -> None:
    payload = build_prematch_payload(
        japan_match, mention_japan=False, image_block=IMAGE_BLOCK
    )
    types = [block["type"] for block in payload["blocks"]]
    assert types == ["header", "section", "image", "context"]
    assert payload["blocks"][2] == IMAGE_BLOCK


def test_prematch_payload_without_image_is_unchanged(japan_match) -> None:
    payload = build_prematch_payload(japan_match, mention_japan=False)
    types = [block["type"] for block in payload["blocks"]]
    assert types == ["header", "section", "context"]
    # 既存の context (視聴情報) の位置は据え置き
    assert payload["blocks"][2]["type"] == "context"


def test_poll_payload_inserts_image(japan_match) -> None:
    payload = build_poll_payload(japan_match, image_block=IMAGE_BLOCK)
    types = [block["type"] for block in payload["blocks"]]
    assert types == ["header", "section", "image"]
    assert payload["blocks"][2] == IMAGE_BLOCK


def test_poll_payload_without_image_is_unchanged(japan_match) -> None:
    payload = build_poll_payload(japan_match)
    types = [block["type"] for block in payload["blocks"]]
    assert types == ["header", "section"]


# ---- main._matchup_image_block の安全ゲート -------------------------------


def test_main_image_block_only_for_bot_client(japan_match) -> None:
    from src.main import _matchup_image_block
    from src.slack import SlackBotClient

    # Bot Token クライアント (非 dry_run) は HEAD200 で画像を添付する
    session = MagicMock()
    session.head.return_value = _head(200)
    bot = SlackBotClient(
        token="xoxb-test", channel="C123", session=session
    )
    block = _matchup_image_block(bot, japan_match)
    assert block is not None and block["type"] == "image"


def test_main_image_block_skipped_for_dry_run(japan_match) -> None:
    from src.main import _matchup_image_block
    from src.slack import SlackBotClient

    session = MagicMock()
    bot = SlackBotClient(token=None, channel=None, dry_run=True, session=session)
    assert _matchup_image_block(bot, japan_match) is None
    session.head.assert_not_called()  # dry_run では HEAD しない


def test_main_image_block_skipped_for_webhook(japan_match) -> None:
    from src.main import _matchup_image_block
    from src.slack import SlackWebhookClient

    webhook = SlackWebhookClient(
        webhook_url="https://hooks.slack.com/x", session=MagicMock()
    )
    assert _matchup_image_block(webhook, japan_match) is None
