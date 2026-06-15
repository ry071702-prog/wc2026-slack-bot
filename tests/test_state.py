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


def test_empty_state_has_prematch_poll_key() -> None:
    assert empty_state()["prematch_poll"] == {}


def test_legacy_state_without_prematch_poll_is_normalized(tmp_path: Path) -> None:
    # prematch_poll 追加前の旧 JSON を読んでも prematch_poll: {} が補われる
    path = tmp_path / "notified.json"
    path.write_text(
        json.dumps(
            {
                "digest_dates": ["2026-06-12"],
                "prematch": [1],
                "result": [2],
                "lineup": [3],
                "poll": {},
                "poll_result": [],
            }
        ),
        encoding="utf-8",
    )
    state = StateStore(path).load()

    assert state["prematch_poll"] == {}
    assert state["prematch"] == [1]


def test_legacy_prematch_poll_list_is_converted_to_dict(tmp_path: Path) -> None:
    # 旧形式 (list[int]) の prematch_poll は {id文字列: ""} に変換される
    # (ts 不明=空文字、過去シード分は集計不可だが dedup は維持)
    path = tmp_path / "notified.json"
    path.write_text(
        json.dumps(
            {
                "digest_dates": [],
                "prematch": [],
                "result": [],
                "lineup": [],
                "poll": {},
                "poll_result": [],
                "prematch_poll": [537351, 537357],
            }
        ),
        encoding="utf-8",
    )
    state = StateStore(path).load()

    assert state["prematch_poll"] == {"537351": "", "537357": ""}


def test_prematch_poll_dict_is_preserved(tmp_path: Path) -> None:
    # 新形式 (dict) はキー/値を str 化してそのまま保持する
    path = tmp_path / "notified.json"
    path.write_text(
        json.dumps(
            {
                "digest_dates": [],
                "prematch": [],
                "result": [],
                "lineup": [],
                "poll": {},
                "poll_result": [],
                "prematch_poll": {"537357": "1700000000.000123", 537358: "1700000001.000456"},
            }
        ),
        encoding="utf-8",
    )
    state = StateStore(path).load()

    assert state["prematch_poll"] == {
        "537357": "1700000000.000123",
        "537358": "1700000001.000456",
    }


def test_prematch_poll_dict_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "notified.json"
    store = StateStore(path)
    state = empty_state()
    state["prematch_poll"]["537357"] = "1700000000.000123"

    store.save(state)

    assert store.load()["prematch_poll"] == {"537357": "1700000000.000123"}
