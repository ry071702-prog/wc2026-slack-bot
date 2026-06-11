from __future__ import annotations

from scripts.build_site_data import build_predictions_summary


def test_empty_predictions() -> None:
    assert build_predictions_summary({}) == {"total": 0, "distribution": {}}


def test_counts_champions_sorted_desc() -> None:
    raw = {
        "U1": {"nickname": "a", "champion": "日本"},
        "U2": {"nickname": "b", "champion": "ブラジル"},
        "U3": {"nickname": "c", "champion": "日本"},
        "U4": {"nickname": "d", "champion": ""},
    }

    summary = build_predictions_summary(raw)

    assert summary["total"] == 4
    assert list(summary["distribution"].items()) == [("日本", 2), ("ブラジル", 1)]
