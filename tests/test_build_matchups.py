from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pytest

from scripts import build_matchups
from src.providers.base import Match, MatchScore


def make_match(
    *,
    match_id: int = 1,
    home: str = "Netherlands",
    away: str = "Japan",
    kickoff: Optional[datetime] = None,
) -> Match:
    return Match(
        id=match_id,
        utc_kickoff=kickoff or datetime(2026, 6, 14, 20, 0, tzinfo=timezone.utc),
        home=home,
        away=away,
        stage="GROUP_STAGE",
        group="GROUP_F",
        matchday=1,
        status="TIMED",
        score=MatchScore(),
    )


# ---- flag_iso / flagcdn_url (英国構成国の変換含む) -------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Japan", "jp"),
        ("Netherlands", "nl"),
        ("England", "gb-eng"),
        ("Scotland", "gb-sct"),
        ("Wales", "gb-wls"),
        ("Ivory Coast", "ci"),
        ("South Korea", "kr"),
        ("Tunisia", "tn"),
        ("TBD", None),
        ("Atlantis", None),
    ],
)
def test_flag_iso(name: str, expected: Optional[str]) -> None:
    assert build_matchups.flag_iso(name) == expected


def test_flagcdn_url_uses_converted_iso() -> None:
    assert (
        build_matchups.flagcdn_url("England")
        == "https://flagcdn.com/w320/gb-eng.png"
    )
    assert (
        build_matchups.flagcdn_url("Japan")
        == "https://flagcdn.com/w320/jp.png"
    )
    assert build_matchups.flagcdn_url("TBD") is None


# ---- TBD スキップ / 対象選別 ---------------------------------------------


def test_is_renderable_skips_tbd() -> None:
    assert build_matchups.is_renderable("Japan", "Spain")
    assert not build_matchups.is_renderable("TBD", "Japan")
    assert not build_matchups.is_renderable("Japan", "TBD")
    assert not build_matchups.is_renderable("", "Japan")


def test_selectable_matches_skips_tbd_and_sorts() -> None:
    later = make_match(
        match_id=10,
        kickoff=datetime(2026, 6, 16, 0, 0, tzinfo=timezone.utc),
    )
    earlier = make_match(
        match_id=11,
        kickoff=datetime(2026, 6, 15, 0, 0, tzinfo=timezone.utc),
    )
    tbd = make_match(match_id=12, home="TBD", away="TBD")

    chosen = build_matchups.selectable_matches([later, earlier, tbd])

    assert [m.id for m in chosen] == [11, 10]  # kickoff 昇順、TBD 除外


def test_selectable_matches_respects_only() -> None:
    a = make_match(match_id=1)
    b = make_match(match_id=2)

    assert [m.id for m in build_matchups.selectable_matches([a, b], only=2)] == [2]


# ---- index.json -----------------------------------------------------------


def test_index_payload_is_sorted() -> None:
    assert build_matchups.index_payload([3, 1, 2]) == {"ids": [1, 2, 3]}


# ---- kickoff ラベル -------------------------------------------------------


def test_kickoff_label() -> None:
    # 6/15 05:00 JST
    assert (
        build_matchups.kickoff_label("2026-06-15T05:00:00+09:00")
        == "6/15(月) 5:00 KO"
    )


# ---- 国旗 DL / キャッシュ / フォールバック判定 ----------------------------


def _png_bytes(color: tuple[int, int, int] = (200, 30, 30)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (32, 21), color).save(buf, format="PNG")
    return buf.getvalue()


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, content: Optional[bytes], raises: bool = False) -> None:
        self.content = content
        self.raises = raises
        self.get_calls = 0

    def get(self, url: str, timeout: float = 10.0) -> FakeResponse:
        self.get_calls += 1
        if self.raises:
            raise RuntimeError("boom")
        assert self.content is not None
        return FakeResponse(self.content)


def test_download_flag_returns_image_on_success() -> None:
    session = FakeSession(_png_bytes())
    img = build_matchups.download_flag("Japan", session)
    assert img is not None
    assert img.mode == "RGBA"


def test_download_flag_returns_none_on_failure() -> None:
    # ネットワーク例外 → None フォールバック
    assert build_matchups.download_flag("Japan", FakeSession(None, raises=True)) is None


def test_download_flag_returns_none_for_unknown_team() -> None:
    session = FakeSession(_png_bytes())
    assert build_matchups.download_flag("Atlantis", session) is None
    assert session.get_calls == 0  # URL 不明なら DL しない


def test_flag_loader_caches_per_iso() -> None:
    session = FakeSession(_png_bytes())
    loader = build_matchups.FlagLoader(session=session)

    first = loader.load("Japan")
    second = loader.load("Japan")

    assert first is second
    assert session.get_calls == 1  # 同じ ISO は 1 回だけ DL


def test_flag_loader_returns_none_on_failure_is_cached() -> None:
    session = FakeSession(None, raises=True)
    loader = build_matchups.FlagLoader(session=session)

    assert loader.load("Japan") is None
    assert loader.load("Japan") is None
    assert session.get_calls == 1  # 失敗も 1 回キャッシュ


# ---- 描画スモーク (日本語フォントが無い環境ではスキップ) -------------------


def _fonts_or_skip() -> "build_matchups.Fonts":
    try:
        return build_matchups.Fonts.resolve()
    except RuntimeError:
        pytest.skip("Japanese font not available in this environment")


class StubFlagLoader:
    """常に同じ振る舞いを返す描画テスト用ローダ。"""

    def __init__(self, image=None) -> None:
        self._image = image

    def load(self, name: str):
        return self._image


def _entry(**overrides) -> dict:
    base = {
        "id": 537357,
        "home": "Netherlands",
        "away": "Japan",
        "home_ja": "オランダ",
        "away_ja": "日本",
        "kickoff_jst": "2026-06-15T05:00:00+09:00",
        "stage_ja": "グループF 第1節",
        "is_japan": True,
    }
    base.update(overrides)
    return base


def test_render_matchup_card_writes_png(tmp_path: Path) -> None:
    from PIL import Image

    fonts = _fonts_or_skip()
    out = tmp_path / "537357.png"

    build_matchups.render_matchup_card(
        _entry(), out, StubFlagLoader(), fonts
    )

    assert out.exists()
    with Image.open(out) as img:
        assert img.size == (build_matchups.CARD_W, build_matchups.CARD_H)


def test_build_matchups_writes_index(tmp_path: Path) -> None:
    fonts = _fonts_or_skip()
    matches = [
        make_match(match_id=1),
        make_match(match_id=2, home="Spain", away="Tunisia"),
        make_match(match_id=3, home="TBD", away="TBD"),
    ]

    ids = build_matchups.build_matchups(
        matches,
        output_dir=tmp_path,
        flag_loader=StubFlagLoader(),  # 国旗 None → プレースホルダー (DL なし)
        fonts=fonts,
    )

    assert sorted(ids) == [1, 2]  # TBD 除外
    assert (tmp_path / "1.png").exists()
    assert (tmp_path / "2.png").exists()
    assert not (tmp_path / "3.png").exists()
    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert index == {"ids": [1, 2]}


def test_matchup_left_right_puts_japan_left():
    from scripts.build_matchups import matchup_left_right

    # 日本がアウェイ (オランダ vs 日本) → 日本を左に
    e = {"home": "Netherlands", "home_ja": "オランダ", "away": "Japan",
         "away_ja": "日本", "is_japan": True}
    left, right = matchup_left_right(e)
    assert left[0] == "Japan" and right[0] == "Netherlands"
    assert left[2] is True

    # 日本がホーム → そのまま左
    e2 = {"home": "Japan", "home_ja": "日本", "away": "Sweden",
          "away_ja": "スウェーデン", "is_japan": True}
    left2, right2 = matchup_left_right(e2)
    assert left2[0] == "Japan" and right2[0] == "Sweden"

    # 非日本戦 → home が左
    e3 = {"home": "Spain", "home_ja": "スペイン", "away": "Paraguay",
          "away_ja": "パラグアイ", "is_japan": False}
    left3, right3 = matchup_left_right(e3)
    assert left3[0] == "Spain" and right3[0] == "Paraguay"
