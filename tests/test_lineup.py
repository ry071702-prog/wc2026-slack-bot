from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.post_lineup import build_initial_comment, classify_position
from scripts.render_lineup import (
    GK_X,
    LINE_X_MAX,
    LINE_X_MIN,
    compute_coordinates,
    kickoff_label,
    load_lineup,
    parse_formation,
)

SAMPLE_PATH = Path(__file__).resolve().parents[1] / "data" / "lineups" / "sample.json"


@pytest.fixture
def sample_lineup() -> dict:
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


# --- formation 解析 ---


def test_parse_formation_433() -> None:
    assert parse_formation("4-3-3") == [4, 3, 3]


def test_parse_formation_3421() -> None:
    assert parse_formation("3-4-2-1") == [3, 4, 2, 1]


@pytest.mark.parametrize("formation", ["4-3-4", "4-3", "abc", "", "4--3-3"])
def test_parse_formation_invalid(formation: str) -> None:
    with pytest.raises(ValueError):
        parse_formation(formation)


# --- 座標計算 ---


def test_compute_coordinates_433_has_11_players() -> None:
    coords = compute_coordinates("4-3-3")
    assert len(coords) == 11


def test_compute_coordinates_gk_first_and_centered() -> None:
    coords = compute_coordinates("4-3-3")
    assert coords[0] == (GK_X, 50.0)


def test_compute_coordinates_line_sizes() -> None:
    coords = compute_coordinates("4-3-3")
    df, mf, fw = coords[1:5], coords[5:8], coords[8:11]
    # 各ラインは同じ x (縦位置) を共有する
    assert len({x for x, _ in df}) == 1
    assert len({x for x, _ in mf}) == 1
    assert len({x for x, _ in fw}) == 1
    # ラインは後ろ→前の順に並ぶ
    assert df[0][0] == LINE_X_MIN
    assert df[0][0] < mf[0][0] < fw[0][0] == LINE_X_MAX


def test_compute_coordinates_within_pitch() -> None:
    for formation in ("4-3-3", "4-2-3-1", "3-4-2-1", "5-4-1"):
        for x, y in compute_coordinates(formation):
            assert 0 < x < 100
            assert 0 < y < 100


def test_compute_coordinates_line_is_left_to_right_and_even() -> None:
    coords = compute_coordinates("4-3-3")
    df_y = [y for _, y in coords[1:5]]
    assert df_y == [20.0, 40.0, 60.0, 80.0]  # 左→右に均等
    fw_y = [y for _, y in coords[8:11]]
    assert fw_y == [25.0, 50.0, 75.0]


# --- position 分類 ---


@pytest.mark.parametrize(
    ("position", "group"),
    [
        ("GK", "GK"),
        ("RB", "DF"),
        ("CB", "DF"),
        ("LB", "DF"),
        ("DM", "MF"),
        ("CM", "MF"),
        ("AM", "MF"),
        ("RW", "FW"),
        ("LW", "FW"),
        ("CF", "FW"),
        ("ST", "FW"),
    ],
)
def test_classify_position(position: str, group: str) -> None:
    assert classify_position(position) == group


def test_classify_position_unknown_raises() -> None:
    with pytest.raises(ValueError):
        classify_position("LIBERO")


# --- initial_comment 生成 ---


def test_build_initial_comment(sample_lineup: dict) -> None:
    comment = build_initial_comment(sample_lineup)
    lines = comment.split("\n")
    assert lines[0] == (
        "🇯🇵 *日本代表スタメン発表！*｜4-3-3｜vs オランダ（グループF 第1節）"
    )
    assert lines[1] == "GK: 1 鈴木彩艶"
    assert lines[2] == "DF: 2 菅原由勢 / 4 板倉滉 / 22 冨安健洋 / 21 伊藤洋輝"
    assert lines[3] == "MF: 6 遠藤航 / 7 田中碧 / 15 鎌田大地"
    assert lines[4] == "FW: 14 伊東純也 / 18 上田綺世 / 8 久保建英"
    assert lines[5] == "控えGK: 大迫敬介 / 早川友基"


def test_build_initial_comment_with_prefix(sample_lineup: dict) -> None:
    comment = build_initial_comment(sample_lineup, prefix="[テスト] ")
    assert comment.startswith("[テスト] 🇯🇵 *日本代表スタメン発表！*")


def test_build_initial_comment_without_bench_note(sample_lineup: dict) -> None:
    del sample_lineup["bench_note"]
    comment = build_initial_comment(sample_lineup)
    assert "控えGK" not in comment
    assert len(comment.split("\n")) == 5


# --- lineup JSON 読み込み ---


def test_load_lineup_sample() -> None:
    lineup = load_lineup(SAMPLE_PATH)
    assert lineup["formation"] == "4-3-3"
    assert len(lineup["players"]) == 11


def test_load_lineup_rejects_wrong_player_count(
    tmp_path: Path, sample_lineup: dict
) -> None:
    sample_lineup["players"] = sample_lineup["players"][:10]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(sample_lineup, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError):
        load_lineup(path)


# --- その他 ---


def test_kickoff_label(sample_lineup: dict) -> None:
    assert kickoff_label(sample_lineup["kickoff_jst"]) == "6/15 5:00"
