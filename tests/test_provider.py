from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from src.providers.football_data import FootballDataProvider


class FakeResponse:
    status_code = 200

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeSession:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return FakeResponse(self.payload)


def load_fixture() -> dict[str, Any]:
    path = Path(__file__).parent / "fixtures" / "matches.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_provider_parses_fixture_and_converts_to_jst() -> None:
    session = FakeSession(load_fixture())
    provider = FootballDataProvider("test-key", session=session)

    matches = provider.fetch_matches(date(2026, 6, 20), date(2026, 6, 22))

    assert matches[0].kickoff_jst.isoformat() == "2026-06-21T13:00:00+09:00"
    assert matches[0].home == "Tunisia"
    assert matches[0].venue is None
    assert matches[2].score.away == 2
    assert matches[2].venue == "Estadio Azteca"
    call = session.calls[0]
    assert call["headers"] == {"X-Auth-Token": "test-key"}
    assert call["params"] == {
        "dateFrom": "2026-06-20",
        "dateTo": "2026-06-22",
    }
    assert call["timeout"] == 10.0
