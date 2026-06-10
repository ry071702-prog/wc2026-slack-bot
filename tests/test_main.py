from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from src.main import run_digest, run_notify
from src.providers.base import Match, Provider
from src.state import StateStore, empty_state


class StubProvider(Provider):
    def __init__(self, matches: list[Match]) -> None:
        self.matches = matches
        self.calls: list[tuple[date, date]] = []

    def fetch_matches(self, date_from: date, date_to: date) -> list[Match]:
        self.calls.append((date_from, date_to))
        return self.matches


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
