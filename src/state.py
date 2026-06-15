from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict


class NotificationState(TypedDict):
    digest_dates: list[str]
    prematch: list[int]
    result: list[int]
    lineup: list[int]
    poll: dict[str, str]
    poll_result: list[int]
    prematch_poll: dict[str, str]


def empty_state() -> NotificationState:
    return {
        "digest_dates": [],
        "prematch": [],
        "result": [],
        "lineup": [],
        "poll": {},
        "poll_result": [],
        "prematch_poll": {},
    }


def _normalize_prematch_poll(raw: Any) -> dict[str, str]:
    """prematch_poll を {match_id文字列: prematch ts} に正規化する。

    後方互換: 旧形式は list[int] (match_id のみ・ts 未記録) だったため、
    list の場合は {str(id): ""} に変換する (ts 不明=空文字、過去シード分は
    集計不可だが dedup は維持される)。dict の場合はキー/値を str に揃える。
    """
    if isinstance(raw, list):
        return {str(value): "" for value in raw}
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items()}
    raise TypeError("prematch_poll must be an array or object")


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> NotificationState:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return self._normalize(raw)
        except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
            print(f"State is missing or invalid; using empty state: {self.path}")
            state = empty_state()
            self.save(state)
            return state

    def save(self, state: NotificationState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(self.path)
        print(f"State saved: {self.path}")

    @staticmethod
    def _normalize(raw: Any) -> NotificationState:
        if not isinstance(raw, dict):
            raise TypeError("state must be an object")
        digest_dates = raw.get("digest_dates", [])
        prematch = raw.get("prematch", [])
        result = raw.get("result", [])
        lineup = raw.get("lineup", [])
        poll = raw.get("poll", {})
        poll_result = raw.get("poll_result", [])
        prematch_poll = raw.get("prematch_poll", {})
        if not all(
            isinstance(value, list)
            for value in (digest_dates, prematch, result, lineup, poll_result)
        ):
            raise TypeError("state values must be arrays")
        if not isinstance(poll, dict):
            raise TypeError("poll must be an object")
        return {
            "digest_dates": [str(value) for value in digest_dates],
            "prematch": [int(value) for value in prematch],
            "result": [int(value) for value in result],
            "lineup": [int(value) for value in lineup],
            "poll": {str(key): str(value) for key, value in poll.items()},
            "poll_result": [int(value) for value in poll_result],
            "prematch_poll": _normalize_prematch_poll(prematch_poll),
        }
