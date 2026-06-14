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
    prematch_poll: list[int]


def empty_state() -> NotificationState:
    return {
        "digest_dates": [],
        "prematch": [],
        "result": [],
        "lineup": [],
        "poll": {},
        "poll_result": [],
        "prematch_poll": [],
    }


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
        prematch_poll = raw.get("prematch_poll", [])
        if not all(
            isinstance(value, list)
            for value in (digest_dates, prematch, result, lineup, poll_result, prematch_poll)
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
            "prematch_poll": [int(value) for value in prematch_poll],
        }
