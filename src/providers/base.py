from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")


@dataclass(frozen=True)
class MatchScore:
    home: Optional[int] = None
    away: Optional[int] = None
    duration: Optional[str] = None
    penalties_home: Optional[int] = None
    penalties_away: Optional[int] = None


@dataclass(frozen=True)
class Match:
    id: int
    utc_kickoff: datetime
    home: str
    away: str
    stage: str
    group: Optional[str]
    matchday: Optional[int]
    status: str
    score: MatchScore

    @property
    def kickoff_jst(self) -> datetime:
        return self.utc_kickoff.astimezone(JST)

    @property
    def is_japan(self) -> bool:
        return self.home == "Japan" or self.away == "Japan"


class Provider(ABC):
    @abstractmethod
    def fetch_matches(self, date_from: date, date_to: date) -> list[Match]:
        """Fetch matches in the inclusive date range."""
