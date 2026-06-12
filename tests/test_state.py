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
    state["lineup"].append(30)

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


def test_empty_state_has_lineup_key() -> None:
    assert empty_state()["lineup"] == []


def test_legacy_state_without_lineup_is_normalized(tmp_path: Path) -> None:
    # 既存の notified.json (lineup 追加前) を読んでも lineup: [] が補われる
    path = tmp_path / "notified.json"
    path.write_text(
        json.dumps(
            {"digest_dates": ["2026-06-12"], "prematch": [1], "result": [2]}
        ),
        encoding="utf-8",
    )
    state = StateStore(path).load()

    assert state["lineup"] == []
    assert state["prematch"] == [1]


def test_broken_json_falls_back_to_empty_state(tmp_path: Path) -> None:
    path = tmp_path / "notified.json"
    path.write_text("{broken", encoding="utf-8")
    store = StateStore(path)

    state = store.load()

    assert state == empty_state()
    assert json.loads(path.read_text(encoding="utf-8")) == empty_state()
