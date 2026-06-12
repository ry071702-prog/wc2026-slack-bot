from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.main import (
    should_send_prematch,
    should_send_result,
    utc_query_dates_for_jst_day,
)
from src.providers.base import Match, MatchScore
from src.state import empty_state


def test_prematch_exactly_15_minutes_before_is_sent(
    japan_match: Match,
) -> None:
    now = japan_match.utc_kickoff - timedelta(minutes=15)

    assert should_send_prematch(japan_match, now, 15, empty_state())


def test_prematch_16_minutes_before_is_not_sent(
    japan_match: Match,
) -> None:
    now = japan_match.utc_kickoff - timedelta(minutes=16)

    assert not should_send_prematch(japan_match, now, 15, empty_state())


def test_prematch_after_kickoff_is_not_sent(japan_match: Match) -> None:
    now = japan_match.utc_kickoff + timedelta(seconds=1)

    assert not should_send_prematch(japan_match, now, 15, empty_state())


def test_prematch_duplicate_is_not_sent(japan_match: Match) -> None:
    state = empty_state()
    state["prematch"].append(japan_match.id)
    now = japan_match.utc_kickoff - timedelta(minutes=10)

    assert not should_send_prematch(japan_match, now, 15, state)


def test_result_duplicate_is_not_sent(japan_match: Match) -> None:
    finished = Match(
        **{
            **japan_match.__dict__,
            "status": "FINISHED",
            "score": MatchScore(home=1, away=2),
        }
    )
    state = empty_state()
    assert should_send_result(finished, state)

    state["result"].append(finished.id)
    assert not should_send_result(finished, state)


def test_prematch_handles_non_utc_aware_now(japan_match: Match) -> None:
    now_jst = datetime(2026, 6, 21, 12, 50, tzinfo=timezone(timedelta(hours=9)))

    assert should_send_prematch(japan_match, now_jst, 15, empty_state())


def test_digest_query_dates_cover_full_jst_day() -> None:
    date_from, date_to = utc_query_dates_for_jst_day(
        datetime(2026, 6, 21, tzinfo=timezone.utc).date()
    )

    assert date_from.isoformat() == "2026-06-20"
    assert date_to.isoformat() == "2026-06-21"
