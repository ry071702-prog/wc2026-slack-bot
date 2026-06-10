from __future__ import annotations

from dataclasses import replace
from datetime import date

from src.messages import prematch_text, result_text
from src.providers.base import Match, MatchScore
from src.slack import build_digest_payload


def test_digest_places_japan_first(
    japan_match: Match, regular_match: Match
) -> None:
    payload = build_digest_payload(
        [regular_match, japan_match], date(2026, 6, 21)
    )

    assert payload["blocks"][0]["text"]["text"] == "⚽ 今日のW杯（6/21 日）"
    assert payload["blocks"][1]["text"]["text"] == (
        "🇯🇵 *13:00　チュニジア vs 日本*"
        "（グループF 第2節）← *日本戦！*"
    )
    assert payload["blocks"][2] == {"type": "divider"}
    assert payload["blocks"][3]["text"]["text"] == (
        "12:00　スペイン vs サウジアラビア（グループH 第2節）"
    )
    assert "時刻はJST" in payload["blocks"][4]["elements"][0]["text"]


def test_prematch_japan_with_mention(japan_match: Match) -> None:
    text = prematch_text(japan_match, mention_japan=True)

    assert text.startswith("<!here> 🔔 *まもなくキックオフ！（13:00〜）*")
    assert "🇯🇵 *チュニジア vs 日本*｜グループF 第2節" in text
    assert "📺 ABEMA de DAZN / DAZN ／ 地上波（NHK・日テレ）" in text


def test_prematch_regular_match_has_no_mention(
    regular_match: Match,
) -> None:
    text = prematch_text(regular_match, mention_japan=True)

    assert not text.startswith("<!here>")
    assert "🇯🇵" not in text
    assert "地上波" not in text


def test_result_japan_win(japan_match: Match) -> None:
    finished = replace(
        japan_match,
        status="FINISHED",
        score=MatchScore(home=1, away=2, duration="REGULAR"),
    )

    text = result_text(finished)

    assert text.startswith(
        "🏁 *試合終了*\n"
        "🇯🇵 チュニジア *1 - 2* 日本\n"
        "🎉 *日本、勝利！* グループF"
    )
    assert (
        "▶️ <https://www.youtube.com/results?search_query="
        in text
    )
    assert "|ハイライトを探す (YouTube)>" in text


def test_result_extra_time(regular_match: Match) -> None:
    finished = replace(
        regular_match,
        status="FINISHED",
        stage="QUARTER_FINALS",
        group=None,
        matchday=None,
        score=MatchScore(home=2, away=1, duration="EXTRA_TIME"),
    )

    text = result_text(finished)

    assert "スペイン *2 - 1* サウジアラビア (延長)" in text
    assert "🏆 *スペインの勝利* 準々決勝" in text


def test_result_penalties_use_shootout_winner(regular_match: Match) -> None:
    finished = replace(
        regular_match,
        status="FINISHED",
        stage="LAST_16",
        group=None,
        matchday=None,
        score=MatchScore(
            home=1,
            away=1,
            duration="PENALTY_SHOOTOUT",
            penalties_home=4,
            penalties_away=2,
        ),
    )

    text = result_text(finished)

    assert "(PK 4-2)" in text
    assert "🏆 *スペインの勝利* ラウンド16" in text


def test_result_japan_draw_and_loss(japan_match: Match) -> None:
    draw = replace(
        japan_match,
        score=MatchScore(home=1, away=1, duration="REGULAR"),
    )
    loss = replace(
        japan_match,
        score=MatchScore(home=2, away=1, duration="REGULAR"),
    )

    assert "🤝 *ドロー*" in result_text(draw)
    assert "😢 *惜敗…次戦に期待！*" in result_text(loss)
