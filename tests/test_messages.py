from __future__ import annotations

from dataclasses import replace
from datetime import date

from src.messages import prematch_text, result_text
from src.providers.base import Match, MatchScore
from src.slack import (
    build_digest_payload,
    build_prematch_payload,
    build_result_payload,
)


def test_digest_places_japan_first(
    japan_match: Match, regular_match: Match
) -> None:
    payload = build_digest_payload(
        [regular_match, japan_match], date(2026, 6, 21)
    )

    assert payload["blocks"][0]["text"]["text"] == "⚽ 今日のW杯 6/21(日)"
    assert payload["blocks"][0]["text"]["emoji"] is True
    assert payload["blocks"][1]["text"]["text"] == (
        "🇯🇵 *13:00　日本 vs 🇹🇳 チュニジア* "
        "（グループF 第2節）← *日本戦！*"
    )
    assert payload["blocks"][2] == {"type": "divider"}
    assert payload["blocks"][3]["text"]["text"] == (
        "*きょうの試合*\n"
        "`12:00`　🇪🇸 スペイン vs 🇸🇦 サウジアラビア（グループH 第2節）"
    )
    assert "時刻はJST" in payload["blocks"][4]["elements"][0]["text"]


def test_prematch_japan_with_mention(japan_match: Match) -> None:
    text = prematch_text(japan_match, mention_japan=True)

    assert text.startswith("<!here>\n")
    assert ">🇯🇵 *日本*  vs  🇹🇳 チュニジア" in text
    assert ">🕔 `13:00` KO ｜ グループF 第2節" in text

    payload = build_prematch_payload(japan_match, mention_japan=True)
    assert payload["blocks"][0]["text"]["text"] == "🔔 まもなくキックオフ"
    assert payload["blocks"][0]["type"] == "header"
    assert payload["blocks"][2]["elements"][0]["text"] == (
        "📺 ABEMA de DAZN / DAZN ／ 地上波（NHK・日テレ）"
    )


def test_prematch_regular_match_has_no_mention(
    regular_match: Match,
) -> None:
    text = prematch_text(regular_match, mention_japan=True)

    assert not text.startswith("<!here>")
    assert "🇯🇵" not in text
    assert ">🇪🇸 スペイン  vs  🇸🇦 サウジアラビア" in text

    payload = build_prematch_payload(regular_match, mention_japan=True)
    assert payload["blocks"][2]["elements"][0]["text"] == (
        "📺 ABEMA de DAZN / DAZN"
    )


def test_result_japan_win(japan_match: Match) -> None:
    finished = replace(
        japan_match,
        status="FINISHED",
        score=MatchScore(home=1, away=2, duration="REGULAR"),
    )

    text = result_text(finished)

    # 日本を先頭に固定し、スコアも日本側を先に並べる (away=日本=2, home=チュニジア=1)
    assert text == (
        ">🇯🇵 *日本*  `2 - 1`  🇹🇳 チュニジア\n"
        ">🎉 *日本、勝利！*  ｜  グループF"
    )

    payload = build_result_payload(finished)
    assert payload["blocks"][0]["text"]["text"] == "🏁 試合終了"
    context = payload["blocks"][2]["elements"][0]["text"]
    assert (
        "▶️ <https://ry071702-prog.github.io/wc2026-slack-bot/"
        f"match.html?id={finished.id}|ハイライト・試合詳細>"
    ) in context
    assert (
        "📊 <https://ry071702-prog.github.io/wc2026-slack-bot/"
        "standings.html|順位表>"
    ) in context


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

    assert "🇪🇸 *スペイン*  `2 - 1`  🇸🇦 サウジアラビア (延長)" in text
    assert "🏆 *スペインの勝利*  ｜  準々決勝" in text


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
    assert "🏆 *スペインの勝利*  ｜  ラウンド16" in text


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


def test_digest_line_shows_score_for_finished(regular_match: Match) -> None:
    from src.slack import build_digest_payload
    from datetime import date

    finished = replace(
        regular_match,
        status="FINISHED",
        score=MatchScore(home=0, away=1),
    )

    from src.messages import digest_match_line

    assert digest_match_line(finished) == (
        "`12:00`　🇪🇸 スペイン 0 - 1 🇸🇦 サウジアラビア（グループH 第2節）　🏁終了"
    )


def test_digest_line_shows_live(regular_match: Match) -> None:
    from src.messages import digest_match_line

    live = replace(
        regular_match,
        status="IN_PLAY",
        score=MatchScore(home=2, away=0),
    )

    assert "🇪🇸 スペイン 2 - 0 🇸🇦 サウジアラビア" in digest_match_line(live)
    assert "🔴LIVE" in digest_match_line(live)


def test_digest_includes_tomorrow_section(
    japan_match: Match, regular_match: Match
) -> None:
    from datetime import date, timedelta

    tomorrow_match = replace(
        regular_match,
        id=777,
        utc_kickoff=regular_match.utc_kickoff + timedelta(days=1),
    )

    payload = build_digest_payload(
        [japan_match],
        date(2026, 6, 21),
        tomorrow_matches=[tomorrow_match],
        tomorrow=date(2026, 6, 22),
    )

    texts = [
        b.get("text", {}).get("text", "")
        for b in payload["blocks"]
        if b["type"] == "section"
    ]
    tomorrow_text = [t for t in texts if "明日" in t]
    assert tomorrow_text, "明日セクションが無い"
    assert "📅 *明日（6/22(月)）の試合*" in tomorrow_text[0]
    assert "🇪🇸 スペイン vs 🇸🇦 サウジアラビア" in tomorrow_text[0]
