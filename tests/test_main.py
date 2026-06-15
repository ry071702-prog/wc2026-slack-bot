from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import pytest

from src.main import prematch_vote_reactions, run_digest, run_notify
from src.providers.base import Match, MatchScore, Provider
from src.state import StateStore, empty_state


class StubProvider(Provider):
    def __init__(self, matches: list[Match]) -> None:
        self.matches = matches
        self.calls: list[tuple[date, date]] = []

    def fetch_matches(self, date_from: date, date_to: date) -> list[Match]:
        self.calls.append((date_from, date_to))
        return self.matches


class ReactionStubSlack:
    """Bot Token クライアントをシミュレート: post_message/add_reaction/get_reactions 対応。"""

    def __init__(self, add_reaction_succeeds: bool = True) -> None:
        self.dry_run = False
        self.posts: list[tuple[str, dict[str, Any]]] = []
        self.reactions_added: list[tuple[str, str]] = []
        self.sends: list[dict[str, Any]] = []
        self._add_reaction_succeeds = add_reaction_succeeds
        self._ts_counter = 0

    def post_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._ts_counter += 1
        ts = f"1700000000.{self._ts_counter:06d}"
        self.posts.append((ts, payload))
        return {"ok": True, "ts": ts, "channel": "C123"}

    def add_reaction(self, ts: str, name: str) -> bool:
        self.reactions_added.append((ts, name))
        return self._add_reaction_succeeds

    def get_reactions(self, ts: str) -> Optional[dict[str, Any]]:
        return {"ok": True, "message": {"reactions": []}}

    def send(self, payload: dict[str, Any]) -> bool:
        self.sends.append(payload)
        return True


class StubSlack:
    def __init__(self, succeeds: bool) -> None:
        self.succeeds = succeeds
        self.dry_run = False
        self.payloads: list[dict[str, Any]] = []

    def send(self, payload: dict[str, Any]) -> bool:
        self.payloads.append(payload)
        return self.succeeds


@pytest.mark.parametrize(
    ("succeeds", "expected_ids"),
    [(True, [1]), (False, [])],
)
def test_prematch_state_changes_only_after_successful_post(
    tmp_path: Path,
    japan_match: Match,
    succeeds: bool,
    expected_ids: list[int],
) -> None:
    store = StateStore(tmp_path / "notified.json")
    store.save(empty_state())
    provider = StubProvider([japan_match])
    slack = StubSlack(succeeds)
    now = japan_match.utc_kickoff - timedelta(minutes=10)

    run_notify(provider, slack, store, now=now)

    assert store.load()["prematch"] == expected_ids
    assert len(provider.calls) == 1


def test_results_are_limited_to_ten_per_run(
    tmp_path: Path, regular_match: Match
) -> None:
    store = StateStore(tmp_path / "notified.json")
    store.save(empty_state())
    matches = [
        replace(
            regular_match,
            id=match_id,
            utc_kickoff=regular_match.utc_kickoff
            + timedelta(minutes=match_id),
            status="FINISHED",
            score=MatchScore(home=1, away=0),
        )
        for match_id in range(1, 12)
    ]
    provider = StubProvider(matches)
    slack = StubSlack(True)

    run_notify(
        provider,
        slack,
        store,
        now=datetime(2026, 6, 21, 12, tzinfo=timezone.utc),
    )

    assert len(slack.payloads) == 10
    assert len(store.load()["result"]) == 10


def test_digest_duplicate_exits_without_api_call(
    tmp_path: Path, regular_match: Match
) -> None:
    store = StateStore(tmp_path / "notified.json")
    state = empty_state()
    state["digest_dates"].append("2026-06-21")
    store.save(state)
    provider = StubProvider([regular_match])
    slack = StubSlack(True)

    run_digest(
        provider,
        slack,
        store,
        now=datetime(2026, 6, 20, 23, tzinfo=timezone.utc),
    )

    assert provider.calls == []
    assert slack.payloads == []


# ---- prematch_vote_reactions -----------------------------------------------


def _make_match(home: str, away: str) -> Match:
    return Match(
        id=999,
        utc_kickoff=datetime(2026, 6, 21, 3, 0, tzinfo=timezone.utc),
        home=home,
        away=away,
        stage="GROUP_STAGE",
        group=None,
        matchday=1,
        status="TIMED",
        score=MatchScore(),
    )


def test_prematch_vote_reactions_japan_home() -> None:
    reactions = prematch_vote_reactions(_make_match("Japan", "Netherlands"))
    assert reactions == ["jp", "handshake", "flag-nl"]
    assert all(reactions)


def test_prematch_vote_reactions_japan_away() -> None:
    reactions = prematch_vote_reactions(_make_match("Tunisia", "Japan"))
    assert reactions == ["flag-tn", "handshake", "jp"]
    assert all(reactions)


def test_prematch_vote_reactions_non_japan() -> None:
    reactions = prematch_vote_reactions(_make_match("Spain", "Saudi Arabia"))
    assert reactions == ["flag-es", "handshake", "flag-sa"]
    assert all(reactions)


def test_prematch_vote_reactions_unknown_team() -> None:
    # 未知チームは soccer フォールバック (空文字にならない)
    reactions = prematch_vote_reactions(_make_match("Atlantis", "Utopia"))
    assert reactions == ["soccer", "handshake", "soccer"]
    assert all(reactions)


# ---- prematch リアクション種付け (run_notify) ---------------------------------


def test_run_notify_prematch_seeds_reactions_non_japan(
    tmp_path: Path, regular_match: Match
) -> None:
    """非日本試合の prematch にリアクション3つが種付けされ state に記録される。"""
    store = StateStore(tmp_path / "notified.json")
    store.save(empty_state())
    slack = ReactionStubSlack()
    now = regular_match.utc_kickoff - timedelta(minutes=10)

    run_notify(StubProvider([regular_match]), slack, store, now=now)

    assert len(slack.posts) == 1
    ts = slack.posts[0][0]
    assert [name for _, name in slack.reactions_added] == ["flag-es", "handshake", "flag-sa"]
    loaded = store.load()
    assert loaded["prematch"] == [regular_match.id]
    # prematch_poll は {match_id文字列: prematch ts} で記録される
    assert loaded["prematch_poll"] == {str(regular_match.id): ts}


def test_run_notify_prematch_seeds_reactions_japan_match(
    tmp_path: Path, japan_match: Match
) -> None:
    """日本試合の prematch にもリアクションが種付けされる。"""
    store = StateStore(tmp_path / "notified.json")
    store.save(empty_state())
    slack = ReactionStubSlack()
    now = japan_match.utc_kickoff - timedelta(minutes=10)

    run_notify(StubProvider([japan_match]), slack, store, now=now)

    # prematch のリアクション (Tunisia away=Japan)
    ts = slack.posts[0][0]
    reaction_names = [name for _, name in slack.reactions_added]
    assert "flag-tn" in reaction_names
    assert "handshake" in reaction_names
    assert "jp" in reaction_names
    assert store.load()["prematch_poll"] == {str(japan_match.id): ts}


def test_run_notify_prematch_reactions_dedup(
    tmp_path: Path, regular_match: Match
) -> None:
    """prematch_poll に記録済みの match にはリアクションを再シードしない。"""
    store = StateStore(tmp_path / "notified.json")
    state = empty_state()
    # prematch_poll には既に登録済み、prematch には未登録 (prematch は再送される経路)
    state["prematch_poll"][str(regular_match.id)] = "existing.ts"
    store.save(state)
    slack = ReactionStubSlack()
    now = regular_match.utc_kickoff - timedelta(minutes=10)

    run_notify(StubProvider([regular_match]), slack, store, now=now)

    # prematch は送られる
    assert len(slack.posts) == 1
    # リアクションは種付けされない (dedup)
    assert slack.reactions_added == []
    # 既存の ts は上書きされない
    assert store.load()["prematch_poll"] == {str(regular_match.id): "existing.ts"}


def test_run_notify_prematch_webhook_no_reactions(
    tmp_path: Path, regular_match: Match
) -> None:
    """Webhook クライアントは send() を使い、リアクション種付けをスキップする。"""
    store = StateStore(tmp_path / "notified.json")
    store.save(empty_state())
    slack = StubSlack(True)  # send() のみ; _supports_reactions = False
    now = regular_match.utc_kickoff - timedelta(minutes=10)

    run_notify(StubProvider([regular_match]), slack, store, now=now)

    assert len(slack.payloads) == 1  # send() が呼ばれた
    loaded = store.load()
    assert loaded["prematch"] == [regular_match.id]
    assert loaded["prematch_poll"] == {}


def test_run_notify_prematch_dry_run_no_reactions(
    tmp_path: Path, regular_match: Match
) -> None:
    """dry_run=True のときはリアクション種付けも state 記録もしない。"""
    store = StateStore(tmp_path / "notified.json")
    store.save(empty_state())
    slack = ReactionStubSlack()
    slack.dry_run = True
    now = regular_match.utc_kickoff - timedelta(minutes=10)

    run_notify(StubProvider([regular_match]), slack, store, now=now)

    loaded = store.load()
    assert loaded["prematch"] == []
    assert loaded["prematch_poll"] == {}
    assert slack.reactions_added == []


def test_run_notify_prematch_add_reaction_failure_prematch_still_delivered(
    tmp_path: Path, regular_match: Match
) -> None:
    """add_reaction が失敗しても prematch は配信され state['prematch'] が記録される。"""
    store = StateStore(tmp_path / "notified.json")
    store.save(empty_state())
    slack = ReactionStubSlack(add_reaction_succeeds=False)
    now = regular_match.utc_kickoff - timedelta(minutes=10)

    run_notify(StubProvider([regular_match]), slack, store, now=now)

    # prematch は post_message で配信済み
    assert len(slack.posts) == 1
    # state['prematch'] は記録される
    assert store.load()["prematch"] == [regular_match.id]
    # add_reaction は呼ばれた (ベストエフォート)
    assert len(slack.reactions_added) == 3
