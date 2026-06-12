"""手動入力の lineup JSON からフォーメーション図 PNG を描画する。

API-FOOTBALL 無料プランは 2026 の lineups にアクセス不可のため、
スタメンは data/lineups/*.json への手動入力方式 (sample.json 参照)。

選手は data/squads.json ("team" フィールド、省略時 Japan) と背番号で照合し
(不一致時は name_ja でフォールバック)、photo URL をダウンロードして円形の
顔写真 + 緑縁 + 背番号バッジで描画する。照合/DL失敗時は従来の緑丸に戻る。

描画は mplsoccer + matplotlib (requirements-lineup.txt のみで管理。
5分毎 cron のインストールを重くしないため requirements.txt には入れない)。
そのため matplotlib / mplsoccer の import は render_lineup() 内に置き、
座標計算などの純ロジックは描画ライブラリなしでテストできるようにしている。

CLI: python scripts/render_lineup.py data/lineups/sample.json -o /tmp/lineup.png
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

# ABEMA/サイト共通テーマ
PITCH_COLOR = "#050506"
LINE_COLOR = "#2EE06A"
MARKER_COLOR = "#2EE06A"
TEXT_COLOR = "#FFFFFF"

# 顔写真の照合に使う squads.json と既定チーム
SQUADS_PATH = Path(__file__).resolve().parents[1] / "data" / "squads.json"
DEFAULT_TEAM = "Japan"

# 顔写真円の描画パラメータ
# OffsetImage の表示サイズは「画像px × zoom」が points になる (dpi に応じ拡大)。
PHOTO_DIAMETER_PT = 41.0  # 緑丸 (s=1150 ≒ 直径38pt) よりやや大きめ
PHOTO_RING_FRAC = 0.045  # 円縁 (#2EE06A) の太さ: 画像辺に対する比率 (表示2-3px相当)
PHOTO_DL_TIMEOUT = 10.0

# GK の縦位置と、フィールドプレイヤーのラインが占める縦範囲 (0=自陣ゴール, 100=敵陣ゴール)
GK_X = 7.0
LINE_X_MIN = 26.0
LINE_X_MAX = 82.0

# 日本語フォント候補 (優先順)。CI (ubuntu) は fonts-noto-cjk を apt install する前提
FONT_CANDIDATES = [
    "Noto Sans CJK JP",
    "Hiragino Sans",
    "Hiragino Kaku Gothic ProN",
    "Noto Sans JP",
]


def parse_formation(formation: str) -> list[int]:
    """"4-3-3" → [4, 3, 3] (GKを除く各ラインの人数、後ろから前)。"""
    try:
        lines = [int(part) for part in formation.split("-")]
    except ValueError as exc:
        raise ValueError(f"invalid formation: {formation!r}") from exc
    if not lines or any(count < 1 for count in lines):
        raise ValueError(f"invalid formation: {formation!r}")
    if sum(lines) != 10:
        raise ValueError(
            f"formation must total 10 outfield players: {formation!r}"
        )
    return lines


def compute_coordinates(formation: str) -> list[tuple[float, float]]:
    """formation 文字列から11人分の (x, y) を返す。

    - 座標系: x=0 自陣ゴール → x=100 敵陣ゴール、y=0 左 → y=100 右 (見た目基準)
    - 並び: GK が先頭、以降は後ろのラインから前へ、各ライン内は左→右
      (lineup JSON の players の並び順と対応させる)
    """
    lines = parse_formation(formation)
    coords: list[tuple[float, float]] = [(GK_X, 50.0)]
    if len(lines) == 1:
        xs = [(LINE_X_MIN + LINE_X_MAX) / 2]
    else:
        step = (LINE_X_MAX - LINE_X_MIN) / (len(lines) - 1)
        xs = [LINE_X_MIN + step * index for index in range(len(lines))]
    for line_x, count in zip(xs, lines):
        for position in range(count):
            y = 100.0 * (position + 1) / (count + 1)
            coords.append((line_x, y))
    return coords


def load_lineup(path: Path) -> dict[str, Any]:
    lineup = json.loads(path.read_text(encoding="utf-8"))
    players = lineup.get("players", [])
    if len(players) != 11:
        raise ValueError(f"lineup must have 11 players, got {len(players)}")
    parse_formation(lineup["formation"])  # 早期バリデーション
    return lineup


def load_squad(team: str, squads_path: Path = SQUADS_PATH) -> list[dict[str, Any]]:
    """squads.json から team のスカッドを返す。読めない/無いときは [] (落とさない)。"""
    try:
        squads = json.loads(Path(squads_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return []
    members = squads.get(team)
    return members if isinstance(members, list) else []


def squad_for_lineup(
    lineup: dict[str, Any], squads_path: Path = SQUADS_PATH
) -> list[dict[str, Any]]:
    """lineup の "team" (省略時 Japan) に対応するスカッドを返す。"""
    return load_squad(lineup.get("team", DEFAULT_TEAM), squads_path)


def resolve_photo_url(player: dict[str, Any], squad: list[dict[str, Any]]) -> str | None:
    """選手の顔写真URLを解決する。

    背番号一致を優先し、無ければ name_ja 一致でフォールバック。
    photo を持たないメンバーは照合対象外。どちらも無ければ None。
    """
    number = player.get("number")
    if number is not None:
        for member in squad:
            if member.get("number") == number and member.get("photo"):
                return member["photo"]
    name = player.get("name")
    if name:
        for member in squad:
            if member.get("name_ja") == name and member.get("photo"):
                return member["photo"]
    return None


def kickoff_label(kickoff_jst: str) -> str:
    """ISO形式の kickoff_jst を "6/15 5:00" 形式にする。"""
    dt = datetime.fromisoformat(kickoff_jst)
    return f"{dt.month}/{dt.day} {dt.hour}:{dt.minute:02d}"


def resolve_font() -> str:
    """利用可能な日本語フォント名を返す (matplotlib が必要)。"""
    from matplotlib import font_manager

    available = {font.name for font in font_manager.fontManager.ttflist}
    for name in FONT_CANDIDATES:
        if name in available:
            return name
    raise RuntimeError(
        "Japanese font not found. "
        f"Install one of: {', '.join(FONT_CANDIDATES)} "
        "(CI: sudo apt-get install -y fonts-noto-cjk)"
    )


def _fetch_photo(url: str) -> "Any":
    """photo URL をダウンロードして画像配列 (numpy) を返す (matplotlib が必要)。"""
    from io import BytesIO

    import matplotlib.pyplot as plt
    import requests

    resp = requests.get(url, timeout=PHOTO_DL_TIMEOUT)
    resp.raise_for_status()
    return plt.imread(BytesIO(resp.content), format="png")


def _circular_photo(img: "Any") -> "Any":
    """正方形クリップ + 円形アルファマスク + #2EE06A の縁を付けた RGBA を返す。

    API-Sports の写真は背景透過とは限らないため、中央正方形を
    そのまま円形に切り抜く (numpy のみで処理)。
    """
    import numpy as np
    from matplotlib.colors import to_rgb

    img = np.asarray(img)
    if img.dtype.kind in ("u", "i"):
        img = img.astype(np.float64) / 255.0
    if img.ndim == 2:  # グレースケール → RGB
        img = np.stack([img] * 3, axis=-1)

    # 中央正方形にクロップ
    h, w = img.shape[:2]
    side = min(h, w)
    top = (h - side) // 2
    left = (w - side) // 2
    img = img[top : top + side, left : left + side]

    rgba = np.ones((side, side, 4), dtype=np.float64)
    rgba[..., :3] = img[..., :3]

    # 円形マスク (縁1px分アンチエイリアス)
    center = (side - 1) / 2.0
    radius = side / 2.0
    yy, xx = np.ogrid[:side, :side]
    dist = np.sqrt((xx - center) ** 2 + (yy - center) ** 2)
    rgba[..., 3] = np.clip(radius - dist, 0.0, 1.0)

    # 縁: 外周の環状部分をテーマ色で塗る
    ring_width = max(3.0, side * PHOTO_RING_FRAC)
    ring = dist >= radius - ring_width
    rgba[ring, :3] = to_rgb(LINE_COLOR)
    return rgba


def render_lineup(lineup: dict[str, Any], output: Path) -> Path:
    """lineup dict からフォーメーション図 PNG を生成する。"""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.offsetbox import AnnotationBbox, OffsetImage
    from mplsoccer import VerticalPitch

    font = resolve_font()
    plt.rcParams["font.family"] = font

    coords = compute_coordinates(lineup["formation"])
    players = lineup["players"]
    squad = squad_for_lineup(lineup)

    pitch = VerticalPitch(
        pitch_type="opta",
        pitch_color=PITCH_COLOR,
        line_color=LINE_COLOR,
        linewidth=1.6,
    )
    # 1080x1350 px 相当 (7.2x9 inch @ dpi150)
    fig = plt.figure(figsize=(7.2, 9.0), facecolor=PITCH_COLOR)
    ax = fig.add_axes([0.03, 0.01, 0.94, 0.88])
    pitch.draw(ax=ax)

    for (x, y_left), player in zip(coords, players):
        # opta 座標は y=0 が攻撃方向に向かって左。VerticalPitch (攻撃方向=上)
        # では y が大きいほど画面左に描かれるため、画面左→右にしたい y_left を反転する
        y = 100.0 - y_left

        # 顔写真の取得 (照合失敗/DL失敗/デコード失敗は緑丸にフォールバック)
        photo = None
        photo_url = resolve_photo_url(player, squad)
        if photo_url:
            try:
                photo = _circular_photo(_fetch_photo(photo_url))
            except Exception:
                photo = None

        if photo is not None:
            # VerticalPitch の ax データ座標は (y, x) (mplsoccer が縦横を入替)
            box = OffsetImage(photo, zoom=PHOTO_DIAMETER_PT / photo.shape[0])
            artist = AnnotationBbox(
                box, (y, x), frameon=False, pad=0.0, zorder=3
            )
            ax.add_artist(artist)
            # 背番号バッジ: 写真円の右下 (画面右=y小, 画面下=x小) に小さな緑丸+白字
            badge_x, badge_y = x - 2.6, y - 3.0
            pitch.scatter(
                badge_x,
                badge_y,
                s=210,
                color=MARKER_COLOR,
                edgecolors=PITCH_COLOR,
                linewidth=0.8,
                zorder=5,
                ax=ax,
            )
            pitch.annotate(
                str(player["number"]),
                xy=(badge_x, badge_y),
                ax=ax,
                ha="center",
                va="center",
                fontsize=7.5,
                fontweight="bold",
                color=TEXT_COLOR,
                zorder=6,
            )
        else:
            # フォールバック: 従来どおり緑丸+白背番号
            pitch.scatter(
                x,
                y,
                s=1150,
                color=MARKER_COLOR,
                edgecolors=PITCH_COLOR,
                linewidth=1.2,
                zorder=3,
                ax=ax,
            )
            pitch.annotate(
                str(player["number"]),
                xy=(x, y),
                ax=ax,
                ha="center",
                va="center",
                fontsize=13,
                fontweight="bold",
                color=TEXT_COLOR,
                zorder=4,
            )
        # 選手名: 円の下 (写真円はやや大きいぶん少し下げる)
        name_offset = 5.0 if photo is not None else 4.6
        pitch.annotate(
            player["name"],
            xy=(x - name_offset, y),
            ax=ax,
            ha="center",
            va="center",
            fontsize=10.5,
            color=TEXT_COLOR,
            zorder=4,
        )

    # 🇯🇵 はフォントに依存して描画できないため画像タイトルでは省略 (Slack本文側で付与)
    title = f"{lineup['title']}｜{lineup['formation']}｜vs {lineup['opponent']}"
    subtitle = f"{kickoff_label(lineup['kickoff_jst'])} キックオフ｜{lineup['stage']}"
    fig.text(
        0.5,
        0.965,
        title,
        ha="center",
        va="center",
        fontsize=19,
        fontweight="bold",
        color=TEXT_COLOR,
    )
    fig.text(
        0.5,
        0.925,
        subtitle,
        ha="center",
        va="center",
        fontsize=12,
        color=LINE_COLOR,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150, facecolor=PITCH_COLOR)
    plt.close(fig)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="スタメン図PNGを生成する")
    parser.add_argument("lineup_json", help="lineup JSONパス (data/lineups/*.json)")
    parser.add_argument(
        "-o", "--output", default="/tmp/lineup.png", help="出力PNGパス"
    )
    args = parser.parse_args(argv)

    lineup = load_lineup(Path(args.lineup_json))
    output = render_lineup(lineup, Path(args.output))
    print(f"rendered: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
