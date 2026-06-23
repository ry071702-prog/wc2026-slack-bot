from __future__ import annotations

from datetime import datetime, timezone

from src.providers.base import Match, MatchScore
from src.standings import compute_group_positions


def _gm(home: str, away: str, hg: int, ag: int) -> Match:
    return Match(
        id=abs(hash((home, away))) % 100000,
        utc_kickoff=datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc),
        home=home,
        away=away,
        stage="GROUP_STAGE",
        group="GROUP_A",
        matchday=1,
        status="FINISHED",
        score=MatchScore(home=hg, away=ag, duration="REGULAR"),
    )


def test_compute_group_positions_orders_by_points_then_gd() -> None:
    matches = [
        _gm("Alpha", "Delta", 3, 0),
        _gm("Bravo", "Charlie", 1, 0),
        _gm("Alpha", "Bravo", 1, 0),
        _gm("Charlie", "Delta", 2, 0),
    ]
    # Alpha 6pts, Charlie/Bravo 3pts (Charlie gd+1 > Bravo gd0), Delta 0
    positions = compute_group_positions(matches)

    assert positions["Alpha"] == ("A", 1)
    assert positions["Charlie"] == ("A", 2)
    assert positions["Bravo"] == ("A", 3)
    assert positions["Delta"] == ("A", 4)


def test_compute_group_positions_ignores_unplayed_and_non_group() -> None:
    knockout = Match(
        id=999,
        utc_kickoff=datetime(2026, 6, 29, 12, 0, tzinfo=timezone.utc),
        home="Alpha",
        away="Bravo",
        stage="LAST_32",
        group=None,
        matchday=None,
        status="TIMED",
        score=MatchScore(),
    )
    unplayed = Match(
        id=1000,
        utc_kickoff=datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc),
        home="Alpha",
        away="Bravo",
        stage="GROUP_STAGE",
        group="GROUP_A",
        matchday=3,
        status="TIMED",
        score=MatchScore(),
    )
    # Alpha が Bravo に 2-0。未消化(TIMED)とノックアウトは集計対象外。
    positions = compute_group_positions([_gm("Alpha", "Bravo", 2, 0), unplayed, knockout])

    assert positions["Alpha"] == ("A", 1)
    assert positions["Bravo"] == ("A", 2)
    # ノックアウトのみに出るチームは順位表に現れない
    assert set(positions) == {"Alpha", "Bravo"}
