from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.main import is_quiet_time, parse_quiet_hours, run_notify
from src.providers.base import Match, MatchScore
from src.state import StateStore, empty_state
from tests.test_main import StubProvider, StubSlack

JST = ZoneInfo("Asia/Tokyo")
QUIET = (time(1, 0), time(6, 30))


def jst(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 6, 15, hour, minute, tzinfo=JST)


def test_parse_default_and_disable() -> None:
    assert parse_quiet_hours(None) == (time(1, 0), time(6, 30))
    assert parse_quiet_hours("23:00-06:00") == (time(23, 0), time(6, 0))
    assert parse_quiet_hours("") is None
    with pytest.raises(ValueError):
        parse_quiet_hours("ふつうの文字列")


def test_quiet_window_boundaries() -> None:
    assert not is_quiet_time(jst(0, 59), QUIET)
    assert is_quiet_time(jst(1, 0), QUIET)
    assert is_quiet_time(jst(6, 29), QUIET)
    assert not is_quiet_time(jst(6, 30), QUIET)
    assert not is_quiet_time(jst(13, 0), QUIET)
    assert not is_quiet_time(jst(3, 0), None)


def test_quiet_window_crossing_midnight() -> None:
    overnight = (time(23, 0), time(6, 0))
    assert is_quiet_time(jst(23, 30), overnight)
    assert is_quiet_time(jst(2, 0), overnight)
    assert not is_quiet_time(jst(12, 0), overnight)


def test_quiet_hours_suppress_non_japan_but_allow_japan(
    tmp_path, japan_match: Match, regular_match: Match
) -> None:
    quiet_now = jst(4, 0)  # 静音時間帯内
    japan = replace(japan_match, utc_kickoff=quiet_now + timedelta(minutes=10))
    regular = replace(
        regular_match,
        id=999,
        utc_kickoff=quiet_now + timedelta(minutes=10),
        status="TIMED",
    )
    finished_regular = replace(
        regular_match,
        id=998,
        status="FINISHED",
        score=MatchScore(home=2, away=1),
    )
    store = StateStore(tmp_path / "notified.json")
    store.save(empty_state())
    slack = StubSlack(True)

    run_notify(
        StubProvider([japan, regular, finished_regular]),
        slack,
        store,
        now=quiet_now,
        quiet_hours=QUIET,
    )

    state = store.load()
    assert state["prematch"] == [japan.id]  # 日本戦のみ通知
    assert state["result"] == []  # 通常試合の結果は静音明けまで保留


def test_after_quiet_hours_pending_results_are_sent(
    tmp_path, regular_match: Match
) -> None:
    finished = replace(
        regular_match, status="FINISHED", score=MatchScore(home=2, away=1)
    )
    store = StateStore(tmp_path / "notified.json")
    store.save(empty_state())
    slack = StubSlack(True)

    run_notify(
        StubProvider([finished]),
        slack,
        store,
        now=jst(6, 30),  # 静音明け最初の実行
        quiet_hours=QUIET,
    )

    assert store.load()["result"] == [finished.id]


def test_result_waits_until_score_is_available(
    tmp_path, regular_match: Match
) -> None:
    from src.providers.base import MatchScore

    scoreless = replace(
        regular_match, status="FINISHED", score=MatchScore()
    )
    store = StateStore(tmp_path / "notified.json")
    store.save(empty_state())
    slack = StubSlack(True)

    run_notify(StubProvider([scoreless]), slack, store, now=jst(12, 0))

    assert store.load()["result"] == []  # スコア未反映 → 持ち越し
    assert slack.payloads == []
