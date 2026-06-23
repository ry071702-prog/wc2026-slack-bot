"""グループステージの順位計算 (site/assets/standings.js の Python 版)。

決勝トーナメントの通知で「どの組を何位で通過したか」を出すために、
グループ戦の結果から各チームの (組, 順位) を求める。
順位タイブレークは standings.js と同じ: 勝ち点 → 得失点差 → 総得点 → チーム名。
"""
from __future__ import annotations

from dataclasses import dataclass

from src.providers.base import Match

# 集計対象: 確定 + 進行中 (順位表と同じ基準)
COUNTABLE_STATUSES = {"FINISHED", "IN_PLAY", "PAUSED"}


@dataclass
class _Row:
    team: str
    points: int = 0
    gd: int = 0
    gf: int = 0
    played: int = 0

    def apply(self, goals_for: int, goals_against: int) -> None:
        self.played += 1
        self.gf += goals_for
        self.gd += goals_for - goals_against
        if goals_for > goals_against:
            self.points += 3
        elif goals_for == goals_against:
            self.points += 1


def _group_letter(group_id: str) -> str:
    return group_id.split("_")[1] if "_" in group_id else group_id


def compute_group_positions(matches: list[Match]) -> dict[str, tuple[str, int]]:
    """チーム名 -> (組レター, 順位 1始まり) を返す。グループ戦のみ対象。"""
    groups: dict[str, dict[str, _Row]] = {}

    for match in matches:
        if match.stage != "GROUP_STAGE" or not match.group:
            continue
        teams = groups.setdefault(match.group, {})
        for name in (match.home, match.away):
            if name and name not in teams:
                teams[name] = _Row(team=name)

        score = match.score
        if (
            match.status not in COUNTABLE_STATUSES
            or score.home is None
            or score.away is None
            or not match.home
            or not match.away
        ):
            continue
        teams[match.home].apply(score.home, score.away)
        teams[match.away].apply(score.away, score.home)

    positions: dict[str, tuple[str, int]] = {}
    for group_id, teams in groups.items():
        letter = _group_letter(group_id)
        rows = sorted(
            teams.values(),
            key=lambda row: (-row.points, -row.gd, -row.gf, row.team),
        )
        for index, row in enumerate(rows):
            positions[row.team] = (letter, index + 1)
    return positions
