from __future__ import annotations

import json
from pathlib import Path

from src.state import StateStore, empty_state


def test_state_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "state" / "notified.json"
    store = StateStore(path)
    state = empty_state()
    state["digest_dates"].append("2026-06-15")
    state["prematch"].append(10)
    state["result"].append(20)

    store.save(state)

    assert store.load() == state


def test_state_append_and_save(tmp_path: Path) -> None:
    path = tmp_path / "notified.json"
    store = StateStore(path)
    state = empty_state()
    state["prematch"].append(123)

    store.save(state)
    raw = json.loads(path.read_text(encoding="utf-8"))

    assert raw["prematch"] == [123]


def test_broken_json_falls_back_to_empty_state(tmp_path: Path) -> None:
    path = tmp_path / "notified.json"
    path.write_text("{broken", encoding="utf-8")
    store = StateStore(path)

    state = store.load()

    assert state == empty_state()
    assert json.loads(path.read_text(encoding="utf-8")) == empty_state()
