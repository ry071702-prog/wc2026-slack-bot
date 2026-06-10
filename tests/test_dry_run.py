from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from src.main import parse_bool, run_notify
from src.providers.base import Match, Provider
from src.providers.football_data import FootballDataProvider
from src.slack import SlackWebhookClient
from src.state import StateStore, empty_state


class FixtureProvider(Provider):
    def __init__(self, matches: list[Match]) -> None:
        self.matches = matches
        self.calls: list[tuple[date, date]] = []

    def fetch_matches(self, date_from: date, date_to: date) -> list[Match]:
        self.calls.append((date_from, date_to))
        return self.matches


def load_matches() -> list[Match]:
    fixture_path = Path(__file__).parent / "fixtures" / "matches.json"
    payload: dict[str, Any] = json.loads(
        fixture_path.read_text(encoding="utf-8")
    )
    return [
        FootballDataProvider._parse_match(item) for item in payload["matches"]
    ]


def test_dry_run_prints_fixture_payload_without_changing_state(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "notified.json"
    store = StateStore(state_path)
    store.save(empty_state())
    provider = FixtureProvider(load_matches())
    dry_run = parse_bool(os.getenv("DRY_RUN"), default=True)
    assert dry_run
    slack = SlackWebhookClient(webhook_url=None, dry_run=dry_run)
    now = datetime(2026, 6, 21, 3, 50, tzinfo=timezone.utc)

    run_notify(
        provider=provider,
        slack=slack,
        state_store=store,
        now=now,
        notify_minutes_before=15,
        mention_japan=True,
    )

    assert store.load() == empty_state()
    assert len(provider.calls) == 1
