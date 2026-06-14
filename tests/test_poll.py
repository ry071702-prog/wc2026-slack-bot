from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import pytest

from src.main import run_notify
from src.messages import (
    japan_opponent,
    japan_poll_reactions,
    japan_poll_result_text,
    japan_poll_text,
)
from src.providers.base import Match, MatchScore, Provider
from src.state import StateStore, empty_state


class StubProvider(Provider):
    def __init__(self, matches: list[Match]) -> None:
        self.matches = matches
        self.calls: list[tuple[date, date]] = []

    def fetch_matches(self, date_from: date, date_to: date) -> list[Match]:
        self.calls.append((date_from, date_to))
        return self.matches


class PollStubSlack:
    """post_message/add_reaction/get_reactions に対応した投票テスト用スタブ。"""

    def __init__(self, reactions: Optional[list[dict[str, Any]]] = None) -> None:
        self.dry_run = False
        self.posts: list[tuple[str, dict[str, Any]]] = []
        self.reactions_added: list[tuple[str, str]] = []
        self.sends: list[dict[str, Any]] = []
        self._reactions = reactions
        self._ts_counter = 0

    def post_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._ts_counter += 1
        ts = f"1700000000.{self._ts_counter:06d}"
        self.posts.append((ts, payload))
        return {"ok": True, "ts": ts, "channel": "C123"}

    def add_reaction(self, ts: str, name: str) -> bool:
        self.reactions_added.append((ts, name))
        return True

    def get_reactions(self, ts: str) -> Optional[dict[str, Any]]:
        if self._reactions is None:
            return None
        return {"ok": True, "message": {"reactions": self._reactions}}

    def send(self, payload: dict[str, Any]) -> bool:
        self.sends.append(payload)
        return True


# 6/15 05:00 JST = 6/14 20:00 UTC, home=Netherlands away=Japan
NL_JAPAN_KICKOFF = datetime(2026, 6, 14, 20, 0, tzinfo=timezone.utc)


@pytest.fixture
def nl_japan() -> Match:
    return Match(
        id=537357,
        utc_kickoff=NL_JAPAN_KICKOFF,
        home="Netherlands",
        away="Japan",
        stage="GROUP_STAGE",
        group="GROUP_F",
        matchday=1,
        status="TIMED",
        score=MatchScore(),
    )


@pytest.fixture
def japan_nl() -> Match:
    # home が日本のパターン
    return Match(
        id=99,
        utc_kickoff=NL_JAPAN_KICKOFF,
        home="Japan",
        away="Netherlands",
        stage="GROUP_STAGE",
        group="GROUP_F",
        matchday=1,
        status="TIMED",
        score=MatchScore(),
    )


def _store(tmp_path: Path) -> StateStore:
    store = StateStore(tmp_path / "notified.json")
    store.save(empty_state())
    return store


# ---- メッセージ生成 -------------------------------------------------------


def test_japan_opponent(nl_japan: Match, japan_nl: Match) -> None:
    assert japan_opponent(nl_japan) == "Netherlands"
    assert japan_opponent(japan_nl) == "Netherlands"


def test_japan_poll_text_away_japan(nl_japan: Match) -> None:
    text = japan_poll_text(nl_japan)
    assert text.startswith("🇯🇵 *オランダ vs 日本* 結果予想！⚽\n")
    assert "6/15(月) 5:00 KO ｜ グループF 第1節" in text
    assert "🇯🇵 日本が勝つ" in text
    assert "🤝 引き分け" in text
    assert "🇳🇱 オランダが勝つ" in text
    assert text.endswith("（試合後にみんなの予想結果を発表📊）")


def test_japan_poll_text_home_japan(japan_nl: Match) -> None:
    text = japan_poll_text(japan_nl)
    assert text.startswith("🇯🇵 *日本 vs オランダ* 結果予想！⚽\n")
    assert "🇳🇱 オランダが勝つ" in text


def test_japan_poll_reactions(nl_japan: Match) -> None:
    assert japan_poll_reactions(nl_japan) == ["jp", "handshake", "flag-nl"]


def test_japan_poll_result_japan_win(nl_japan: Match) -> None:
    # 日本 2-1 勝ち → home(オランダ)=1, away(日本)=2
    finished = replace(
        nl_japan,
        status="FINISHED",
        score=MatchScore(home=1, away=2, duration="REGULAR"),
    )
    text = japan_poll_result_text(finished, 12, 3, 5)
    assert "📊 *みんなの予想結果*（オランダ 1 - 2 日本）" in text
    assert "🇯🇵 日本勝利: 12票 ← 🎯的中！" in text
    assert "🤝 引き分け: 3票\n" in text
    assert "🇳🇱 オランダ勝利: 5票\n" in text
    assert "オランダ勝利: 5票 ← 🎯的中！" not in text
    assert "的中した12人、おみごと！🎉" in text


def test_japan_poll_result_draw(nl_japan: Match) -> None:
    finished = replace(
        nl_japan,
        status="FINISHED",
        score=MatchScore(home=1, away=1, duration="REGULAR"),
    )
    text = japan_poll_result_text(finished, 12, 7, 5)
    assert "🤝 引き分け: 7票 ← 🎯的中！" in text
    assert "日本勝利: 12票 ← 🎯的中！" not in text
    assert "オランダ勝利: 5票 ← 🎯的中！" not in text
    assert "的中した7人、おみごと！🎉" in text


def test_japan_poll_result_opponent_win(nl_japan: Match) -> None:
    # オランダ勝ち → home(オランダ)=2, away(日本)=0
    finished = replace(
        nl_japan,
        status="FINISHED",
        score=MatchScore(home=2, away=0, duration="REGULAR"),
    )
    text = japan_poll_result_text(finished, 12, 3, 5)
    assert "🇳🇱 オランダ勝利: 5票 ← 🎯的中！" in text
    assert "日本勝利: 12票 ← 🎯的中！" not in text
    assert "（オランダ 2 - 0 日本）" in text
    assert "的中した5人、おみごと！🎉" in text


# ---- run_notify でのポール投稿 -------------------------------------------


def test_run_notify_posts_poll_and_seeds_reactions(
    tmp_path: Path, nl_japan: Match
) -> None:
    store = _store(tmp_path)
    provider = StubProvider([nl_japan])
    slack = PollStubSlack()
    now = nl_japan.utc_kickoff - timedelta(hours=10)

    run_notify(provider, slack, store, now=now)

    assert len(slack.posts) == 1
    ts = slack.posts[0][0]
    assert [name for _, name in slack.reactions_added] == [
        "jp",
        "handshake",
        "flag-nl",
    ]
    assert store.load()["poll"] == {"537357": ts}


def test_run_notify_does_not_repost_existing_poll(
    tmp_path: Path, nl_japan: Match
) -> None:
    store = StateStore(tmp_path / "notified.json")
    state = empty_state()
    state["poll"]["537357"] = "existing.ts"
    store.save(state)
    slack = PollStubSlack()
    now = nl_japan.utc_kickoff - timedelta(hours=10)

    run_notify(StubProvider([nl_japan]), slack, store, now=now)

    assert slack.posts == []
    assert slack.reactions_added == []


@pytest.mark.parametrize(
    ("lead_hours", "expected_posts"),
    [(14.0, 1), (14.5, 0), (1.0, 1), (-0.1, 0)],
)
def test_run_notify_poll_window_boundaries(
    tmp_path: Path,
    nl_japan: Match,
    lead_hours: float,
    expected_posts: int,
) -> None:
    store = _store(tmp_path)
    slack = PollStubSlack()
    now = nl_japan.utc_kickoff - timedelta(hours=lead_hours)

    run_notify(StubProvider([nl_japan]), slack, store, now=now)

    assert len(slack.posts) == expected_posts


# ---- run_notify での集計発表 ---------------------------------------------


def _finished_japan_win(nl_japan: Match) -> Match:
    return replace(
        nl_japan,
        status="FINISHED",
        score=MatchScore(home=1, away=2, duration="REGULAR"),
    )


def test_run_notify_posts_poll_result(tmp_path: Path, nl_japan: Match) -> None:
    store = StateStore(tmp_path / "notified.json")
    state = empty_state()
    state["poll"]["537357"] = "1700000000.000001"
    state["result"].append(537357)  # 結果通知は対象外にして集計のみ検証
    store.save(state)
    finished = _finished_japan_win(nl_japan)
    reactions = [
        {"name": "jp", "count": 13},
        {"name": "handshake", "count": 4},
        {"name": "flag-nl", "count": 6},
    ]
    slack = PollStubSlack(reactions=reactions)
    now = finished.utc_kickoff + timedelta(hours=2)

    run_notify(StubProvider([finished]), slack, store, now=now)

    assert len(slack.sends) == 1
    assert slack.sends[0]["blocks"][0]["text"]["text"] == "📊 予想結果発表"
    text = slack.sends[0]["blocks"][1]["text"]["text"]
    assert "🇯🇵 日本勝利: 12票 ← 🎯的中！" in text  # 13 - 1
    assert "🤝 引き分け: 3票" in text  # 4 - 1
    assert "🇳🇱 オランダ勝利: 5票" in text  # 6 - 1
    assert store.load()["poll_result"] == [537357]


def test_run_notify_poll_result_only_once(
    tmp_path: Path, nl_japan: Match
) -> None:
    store = StateStore(tmp_path / "notified.json")
    state = empty_state()
    state["poll"]["537357"] = "1700000000.000001"
    state["poll_result"].append(537357)
    state["result"].append(537357)
    store.save(state)
    slack = PollStubSlack(reactions=[{"name": "jp", "count": 13}])
    now = nl_japan.utc_kickoff + timedelta(hours=2)

    run_notify(StubProvider([_finished_japan_win(nl_japan)]), slack, store, now=now)

    assert slack.sends == []


def test_run_notify_poll_result_skipped_when_reactions_unavailable(
    tmp_path: Path, nl_japan: Match
) -> None:
    store = StateStore(tmp_path / "notified.json")
    state = empty_state()
    state["poll"]["537357"] = "1700000000.000001"
    state["result"].append(537357)
    store.save(state)
    slack = PollStubSlack(reactions=None)  # get_reactions -> None
    now = nl_japan.utc_kickoff + timedelta(hours=2)

    run_notify(StubProvider([_finished_japan_win(nl_japan)]), slack, store, now=now)

    assert slack.sends == []
    assert store.load()["poll_result"] == []


# ---- state 後方互換 -------------------------------------------------------


def test_legacy_state_without_poll_keys(tmp_path: Path) -> None:
    path = tmp_path / "notified.json"
    path.write_text(
        json.dumps(
            {
                "digest_dates": ["2026-06-12"],
                "prematch": [1],
                "result": [2],
                "lineup": [3],
            }
        ),
        encoding="utf-8",
    )

    state = StateStore(path).load()

    assert state["poll"] == {}
    assert state["poll_result"] == []
    assert state["prematch"] == [1]


def test_result_text_lists_winner_names(japan_match):
    from dataclasses import replace
    from src.messages import japan_poll_result_text
    from src.providers.base import MatchScore

    # japan_match: home=Tunisia away=Japan。日本勝ち (チュニジア1-2日本)
    m = replace(japan_match, status="FINISHED", score=MatchScore(home=1, away=2))
    text = japan_poll_result_text(m, 3, 1, 2, winner_names=["山田", "鈴木"], winner_extra=1)
    assert "🎯 *的中者*（3人）: 山田・鈴木 ほか1人" in text
    # 名前なし(従来)も維持
    text2 = japan_poll_result_text(m, 3, 1, 2)
    assert "的中した3人、おみごと！🎉" in text2


def test_resolve_winner_names_excludes_bot_and_caps():
    from src.main import _resolve_winner_names, POLL_MAX_WINNER_NAMES

    class FakeClient:
        dry_run = False
        def bot_user_id(self):
            return "BOT"
        def user_display_name(self, uid):
            return f"name-{uid}"

    users = ["BOT"] + [f"U{i}" for i in range(POLL_MAX_WINNER_NAMES + 5)]
    reaction = {"name": "jp", "count": len(users), "users": users}
    # 実投票数 = count - 1 (bot除外)
    names, extra = _resolve_winner_names(FakeClient(), reaction, len(users) - 1)
    assert len(names) == POLL_MAX_WINNER_NAMES
    assert "name-BOT" not in names
    assert extra == 5  # 35人中30人表示・残り5人


def test_resolve_winner_names_without_capable_client():
    from src.main import _resolve_winner_names

    class PlainClient:
        dry_run = False

    names, extra = _resolve_winner_names(PlainClient(), {"users": ["U1"]}, 1)
    assert names is None and extra == 0
