from __future__ import annotations

import time
from datetime import date, datetime, timezone
from typing import Any, Optional

import requests

from src.providers.base import Match, MatchScore, Provider


class FootballDataProvider(Provider):
    BASE_URL = "https://api.football-data.org/v4/competitions/WC/matches"

    def __init__(
        self,
        api_key: str,
        session: Optional[requests.Session] = None,
        timeout: float = 10.0,
    ) -> None:
        if not api_key:
            raise ValueError("FOOTBALL_DATA_API_KEY is required")
        self.api_key = api_key
        self.session = session or requests.Session()
        self.timeout = timeout

    def fetch_matches(self, date_from: date, date_to: date) -> list[Match]:
        params = {
            "dateFrom": date_from.isoformat(),
            "dateTo": date_to.isoformat(),
        }
        headers = {"X-Auth-Token": self.api_key}

        for attempt in range(2):
            try:
                response = self.session.get(
                    self.BASE_URL,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                payload = response.json()
                matches = payload.get("matches", [])
                print(
                    "football-data.org: "
                    f"{date_from}..{date_to}, {len(matches)} matches"
                )
                return [self._parse_match(item) for item in matches]
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                if attempt == 1:
                    raise RuntimeError(
                        "football-data.org request failed after retry"
                    ) from exc
                delay_seconds = 2**attempt
                print(
                    "football-data.org request failed; "
                    f"retrying in {delay_seconds}s: {exc}"
                )
                time.sleep(delay_seconds)

        raise AssertionError("unreachable")

    @staticmethod
    def _parse_match(item: dict[str, Any]) -> Match:
        score_data = item.get("score") or {}
        full_time = score_data.get("fullTime") or {}
        penalties = score_data.get("penalties") or {}
        utc_kickoff = datetime.fromisoformat(
            item["utcDate"].replace("Z", "+00:00")
        )
        if utc_kickoff.tzinfo is None:
            utc_kickoff = utc_kickoff.replace(tzinfo=timezone.utc)

        return Match(
            id=int(item["id"]),
            utc_kickoff=utc_kickoff.astimezone(timezone.utc),
            home=FootballDataProvider._team_name(item.get("homeTeam")),
            away=FootballDataProvider._team_name(item.get("awayTeam")),
            stage=str(item.get("stage") or ""),
            group=item.get("group"),
            matchday=FootballDataProvider._optional_int(item.get("matchday")),
            status=str(item.get("status") or ""),
            score=MatchScore(
                home=FootballDataProvider._optional_int(full_time.get("home")),
                away=FootballDataProvider._optional_int(full_time.get("away")),
                duration=score_data.get("duration"),
                penalties_home=FootballDataProvider._optional_int(
                    penalties.get("home")
                ),
                penalties_away=FootballDataProvider._optional_int(
                    penalties.get("away")
                ),
            ),
        )

    @staticmethod
    def _team_name(team: Any) -> str:
        if not isinstance(team, dict):
            return "TBD"
        return str(team.get("name") or "TBD")

    @staticmethod
    def _optional_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        return int(value)
