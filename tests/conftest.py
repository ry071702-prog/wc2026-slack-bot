from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.providers.base import Match, MatchScore


@pytest.fixture
def japan_match() -> Match:
    return Match(
        id=1,
        utc_kickoff=datetime(2026, 6, 21, 4, 0, tzinfo=timezone.utc),
        home="Tunisia",
        away="Japan",
        stage="GROUP_STAGE",
        group="GROUP_F",
        matchday=2,
        status="TIMED",
        score=MatchScore(),
    )


@pytest.fixture
def regular_match() -> Match:
    return Match(
        id=2,
        utc_kickoff=datetime(2026, 6, 21, 3, 0, tzinfo=timezone.utc),
        home="Spain",
        away="Saudi Arabia",
        stage="GROUP_STAGE",
        group="GROUP_H",
        matchday=2,
        status="TIMED",
        score=MatchScore(),
    )
