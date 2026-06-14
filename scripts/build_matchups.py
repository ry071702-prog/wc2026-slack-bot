"""対戦カード (VSカード) PNG を全試合ぶん生成する。

home/away が確定した (TBD でない) 試合ごとに 1200x630 の OGP 風横長カードを
Pillow で描画し site/data/matchups/{id}.png に保存する。生成済み ID 一覧は
site/data/matchups/index.json に {"ids": [...]} で書き出し、notify 側が存在確認に
使えるようにする。

国旗は flagcdn (パブリックドメイン・キー不要) から requests で DL し Pillow で
リサイズして VS の両脇に角丸+枠付きで配置する。同じ ISO は 1 回だけ DL して
キャッシュする。DL 失敗時はその国だけソリッドカラー+国名のプレースホルダーに
フォールバックし、カード生成自体は継続する。

描画は Pillow のみ (matplotlib 不使用・軽量)。日本語フォントは Hiragino (mac) /
Noto CJK (CI: fonts-noto-cjk) を解決する。

CLI:
  FOOTBALL_DATA_API_KEY=... python scripts/build_matchups.py
  FOOTBALL_DATA_API_KEY=... python scripts/build_matchups.py --only 537357 -o /tmp/card.png
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import build_site_data
from src.flags import TEAM_ISO
from src.messages import WEEKDAYS_JA, team_name
from src.providers.base import Match
from src.providers.football_data import FootballDataProvider

# ---- 配色・サイズ (サイト/ABEMA 共通テーマ) ------------------------------
CARD_W = 1200
CARD_H = 630
BG = (5, 5, 6, 255)          # #050506
NEON = (46, 224, 106, 255)   # #2EE06A
WHITE = (245, 246, 248, 255)
MUTED = (154, 160, 166, 255)  # #9AA0A6
FLAG_BORDER = (120, 124, 130, 255)
FLAG_BORDER_JP = NEON

FLAG_BOX = (300, 200)
FLAG_RADIUS = 18
LEFT_FLAG_CX = 250
RIGHT_FLAG_CX = 950
FLAG_CY = 270
NAME_Y = 420

# flagcdn は英国構成国を gb-eng / gb-sct / gb-wls で配信する。
FLAGCDN_SUBDIVISION = {
    "england": "gb-eng",
    "scotland": "gb-sct",
    "wales": "gb-wls",
}

# 日本語フォント候補 (優先順・フルパス)。CI(ubuntu) は fonts-noto-cjk を入れる前提。
FONT_CANDIDATES_BOLD = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Bold.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
]
FONT_CANDIDATES_REGULAR = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]

OUTPUT_DIR = ROOT_DIR / "site" / "data" / "matchups"
TOURNAMENT_START = build_site_data.TOURNAMENT_START
TOURNAMENT_END = build_site_data.TOURNAMENT_END


# ---- 純ロジック (Pillow/requests 非依存・単体テスト対象) ------------------


def flag_iso(name: str) -> Optional[str]:
    """英語名 → flagcdn 用 ISO コード。England→gb-eng / Scotland→gb-sct /
    Wales→gb-wls、Japan→jp、それ以外は TEAM_ISO の値そのまま。未知名は None。"""
    iso = TEAM_ISO.get(name)
    if not iso:
        return None
    return FLAGCDN_SUBDIVISION.get(iso, iso)


def flagcdn_url(name: str, width: int = 320) -> Optional[str]:
    """英語名 → flagcdn の PNG URL。未知名は None。"""
    iso = flag_iso(name)
    if not iso:
        return None
    return f"https://flagcdn.com/w{width}/{iso}.png"


def is_renderable(home: str, away: str) -> bool:
    """home/away がともに確定 (TBD/空でない) ならカード生成対象。"""
    return bool(home) and bool(away) and home != "TBD" and away != "TBD"


def selectable_matches(
    matches: list[Match], only: Optional[int] = None
) -> list[Match]:
    """カード生成対象の試合を kickoff 順で返す (TBD は除外、only 指定時は1件)。"""
    chosen = [
        match
        for match in matches
        if is_renderable(match.home, match.away)
        and (only is None or match.id == only)
    ]
    return sorted(chosen, key=lambda match: match.utc_kickoff)


def index_payload(ids: list[int]) -> dict[str, list[int]]:
    """index.json のペイロード ({"ids": ソート済み})。"""
    return {"ids": sorted(ids)}


def kickoff_label(kickoff_jst_iso: str) -> str:
    """ISO 形式の kickoff_jst を "M/D(曜) H:MM KO" にする (時は0埋めしない)。"""
    dt = datetime.fromisoformat(kickoff_jst_iso)
    weekday = WEEKDAYS_JA[dt.weekday()]
    return f"{dt.month}/{dt.day}({weekday}) {dt.hour}:{dt.minute:02d} KO"


def _placeholder_color(name: str) -> tuple[int, int, int, int]:
    """国名から決まる落ち着いた暗色 (国旗 DL 失敗時のプレースホルダー地色)。"""
    digest = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16)
    r = 38 + (digest & 0x3F)
    g = 40 + ((digest >> 6) & 0x3F)
    b = 46 + ((digest >> 12) & 0x3F)
    return (r, g, b, 255)


# ---- 国旗ローダ (キャッシュ付き) -----------------------------------------


def download_flag(name: str, session: requests.Session, timeout: float = 10.0):
    """flagcdn から国旗を DL して RGBA の PIL.Image を返す。失敗時は None。"""
    from PIL import Image

    url = flagcdn_url(name)
    if not url:
        return None
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert("RGBA")
    except Exception as exc:  # noqa: BLE001 (DL/デコード失敗は握りつぶしフォールバック)
        print(f"flag download failed for {name} ({url}): {exc}")
        return None


class FlagLoader:
    """同じ ISO は 1 回だけ DL するキャッシュ付き国旗ローダ。"""

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        timeout: float = 10.0,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout
        self._cache: dict[str, Any] = {}

    def load(self, name: str):
        """国旗の PIL.Image を返す (キャッシュ)。未知名/失敗時は None。"""
        iso = flag_iso(name)
        if not iso:
            return None
        if iso not in self._cache:
            self._cache[iso] = download_flag(name, self.session, self.timeout)
        return self._cache[iso]


# ---- フォント解決 ---------------------------------------------------------


def resolve_font_path(bold: bool) -> str:
    """利用可能な日本語フォントのフルパスを返す。無ければ RuntimeError。"""
    candidates = FONT_CANDIDATES_BOLD if bold else FONT_CANDIDATES_REGULAR
    for path in candidates:
        if os.path.exists(path):
            return path
    raise RuntimeError(
        "Japanese font not found. Install Hiragino (mac) or fonts-noto-cjk "
        "(CI: sudo apt-get install -y fonts-noto-cjk). "
        f"Tried: {', '.join(candidates)}"
    )


@dataclass
class Fonts:
    bold_path: str
    regular_path: str

    @classmethod
    def resolve(cls) -> "Fonts":
        return cls(resolve_font_path(True), resolve_font_path(False))

    def bold(self, size: int):
        from PIL import ImageFont

        return ImageFont.truetype(self.bold_path, size)

    def regular(self, size: int):
        from PIL import ImageFont

        return ImageFont.truetype(self.regular_path, size)

    def fit_bold(
        self, text: str, max_width: int, max_size: int, min_size: int = 22
    ):
        """max_width に収まる最大の bold フォントを返す。"""
        size = max_size
        while size > min_size:
            font = self.bold(size)
            if font.getlength(text) <= max_width:
                return font
            size -= 2
        return self.bold(min_size)


# ---- カード描画 -----------------------------------------------------------


def _flag_tile(
    flag_img,
    name_ja: str,
    fonts: "Fonts",
    border_color: tuple[int, int, int, int],
    border_width: int,
):
    """角丸+枠付きの国旗タイル (RGBA, FLAG_BOX サイズ) を返す。
    flag_img が None のときはソリッドカラー+国名のプレースホルダー。"""
    from PIL import Image, ImageDraw, ImageOps

    box_w, box_h = FLAG_BOX
    if flag_img is not None:
        filled = ImageOps.fit(flag_img, (box_w, box_h), method=Image.LANCZOS)
        filled = filled.convert("RGBA")
    else:
        filled = Image.new("RGBA", (box_w, box_h), _placeholder_color(name_ja))
        place_draw = ImageDraw.Draw(filled)
        font = fonts.fit_bold(name_ja, box_w - 32, 40, min_size=20)
        place_draw.text(
            (box_w // 2, box_h // 2),
            name_ja,
            font=font,
            fill=WHITE,
            anchor="mm",
        )

    mask = Image.new("L", (box_w, box_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, box_w - 1, box_h - 1], radius=FLAG_RADIUS, fill=255
    )

    tile = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    tile.paste(filled, (0, 0), mask)
    inset = border_width / 2
    ImageDraw.Draw(tile).rounded_rectangle(
        [inset, inset, box_w - 1 - inset, box_h - 1 - inset],
        radius=FLAG_RADIUS,
        outline=border_color,
        width=border_width,
    )
    return tile


def _paste_glow(card, box, radius, color, blur=22) -> None:
    """指定矩形のまわりにぼかしたグロー (ネオン強調) を合成する。"""
    from PIL import Image, ImageDraw, ImageFilter

    glow = Image.new("RGBA", card.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle(box, radius=radius, fill=color)
    glow = glow.filter(ImageFilter.GaussianBlur(blur))
    card.alpha_composite(glow)


def render_matchup_card(
    entry: dict[str, Any],
    output: Path,
    flag_loader: "FlagLoader",
    fonts: "Fonts",
) -> Path:
    """schedule エントリ風 dict から VSカード PNG を生成する。

    必要キー: home, away, home_ja, away_ja, kickoff_jst, stage_ja, is_japan
    """
    from PIL import Image, ImageDraw

    card = Image.new("RGBA", (CARD_W, CARD_H), BG)
    draw = ImageDraw.Draw(card)

    # 外周のネオン枠
    draw.rounded_rectangle(
        [14, 14, CARD_W - 15, CARD_H - 15],
        radius=30,
        outline=NEON,
        width=4,
    )
    # 上下の細いネオンの装飾ライン
    draw.line([(60, 120), (CARD_W - 60, 120)], fill=(46, 224, 106, 90), width=2)

    # ステージ (上部中央)
    stage = str(entry.get("stage_ja") or "")
    if stage:
        stage_font = fonts.fit_bold(stage, CARD_W - 160, 40, min_size=24)
        draw.text((CARD_W // 2, 74), stage, font=stage_font, fill=NEON, anchor="mm")

    is_japan = bool(entry.get("is_japan"))
    home_jp = entry.get("home") == "Japan"
    away_jp = entry.get("away") == "Japan"

    sides = (
        (entry.get("home"), str(entry.get("home_ja") or ""), LEFT_FLAG_CX, home_jp),
        (entry.get("away"), str(entry.get("away_ja") or ""), RIGHT_FLAG_CX, away_jp),
    )

    box_w, box_h = FLAG_BOX
    for name_en, name_ja, center_x, is_jp_side in sides:
        flag_img = flag_loader.load(str(name_en)) if name_en else None
        left = center_x - box_w // 2
        top = FLAG_CY - box_h // 2

        if is_japan and is_jp_side:
            # 日本側はネオングローと太枠で強調
            _paste_glow(
                card,
                [left - 12, top - 12, left + box_w + 12, top + box_h + 12],
                radius=FLAG_RADIUS + 12,
                color=(46, 224, 106, 130),
            )
            tile = _flag_tile(flag_img, name_ja, fonts, FLAG_BORDER_JP, 7)
            name_color = NEON
            name_text = f"★ {name_ja} ★"
        else:
            tile = _flag_tile(flag_img, name_ja, fonts, FLAG_BORDER, 3)
            name_color = WHITE
            name_text = name_ja

        card.alpha_composite(tile, (left, top))

        name_font = fonts.fit_bold(name_text, box_w + 80, 48, min_size=22)
        draw.text(
            (center_x, NAME_Y), name_text, font=name_font, fill=name_color, anchor="mm"
        )

    # 中央の "VS" (ネオン+影)
    vs_font = fonts.bold(128)
    draw.text((CARD_W // 2 + 3, FLAG_CY + 4), "VS", font=vs_font, fill=(0, 0, 0, 180), anchor="mm")
    draw.text((CARD_W // 2, FLAG_CY), "VS", font=vs_font, fill=NEON, anchor="mm")

    # キックオフ (下部中央)
    ko = kickoff_label(str(entry["kickoff_jst"]))
    ko_font = fonts.bold(42)
    draw.text((CARD_W // 2, 552), ko, font=ko_font, fill=WHITE, anchor="mm")

    output.parent.mkdir(parents=True, exist_ok=True)
    card.convert("RGB").save(output, format="PNG")
    return output


# ---- ビルド本体 -----------------------------------------------------------


def build_matchups(
    matches: list[Match],
    output_dir: Path = OUTPUT_DIR,
    flag_loader: Optional["FlagLoader"] = None,
    fonts: Optional["Fonts"] = None,
    only: Optional[int] = None,
    write_index: bool = True,
    output_override: Optional[Path] = None,
) -> list[int]:
    """対象試合ぶんのカードを生成し、生成 ID のリストを返す。"""
    flag_loader = flag_loader or FlagLoader()
    fonts = fonts or Fonts.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    chosen = selectable_matches(matches, only)
    ids: list[int] = []
    for match in chosen:
        entry = build_site_data.match_to_schedule_entry(match)
        out = output_override if output_override else output_dir / f"{match.id}.png"
        # 1枚の描画失敗が全体を止めないよう個別に握る (index.jsonには成功分のみ載せる)
        try:
            render_matchup_card(entry, out, flag_loader, fonts)
        except Exception as exc:  # noqa: BLE001
            print(f"matchup card FAILED for {match.home} vs {match.away}: {exc}")
            continue
        ids.append(match.id)
        print(f"matchup card: {match.home} vs {match.away} -> {out}")

    if write_index:
        build_site_data.write_json(
            output_dir / "index.json", index_payload(ids)
        )
    return ids


def fetch_matches(api_key: str) -> list[Match]:
    provider = FootballDataProvider(api_key)
    return provider.fetch_matches(TOURNAMENT_START, TOURNAMENT_END)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="対戦カード (VSカード) PNG を生成する")
    parser.add_argument(
        "--only", type=int, default=None, help="この match id だけ描く (サンプル確認用)"
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="--only 指定時の出力先 PNG パス (既定は site/data/matchups/{id}.png)",
    )
    args = parser.parse_args(argv)

    api_key = os.environ.get("FOOTBALL_DATA_API_KEY", "")
    if not api_key:
        raise SystemExit("FOOTBALL_DATA_API_KEY is required")

    matches = fetch_matches(api_key)
    ids = build_matchups(
        matches,
        only=args.only,
        # --only はサンプル確認用途なので index.json は更新しない
        write_index=args.only is None,
        output_override=Path(args.output) if (args.only and args.output) else None,
    )
    print(f"matchup cards generated: {len(ids)} -> {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
