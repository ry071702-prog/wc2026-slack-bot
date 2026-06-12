"""手動入力の lineup JSON からフォーメーション図 PNG を描画する。

API-FOOTBALL 無料プランは 2026 の lineups にアクセス不可のため、
スタメンは data/lineups/*.json への手動入力方式 (sample.json 参照)。

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


def render_lineup(lineup: dict[str, Any], output: Path) -> Path:
    """lineup dict からフォーメーション図 PNG を生成する。"""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mplsoccer import VerticalPitch

    font = resolve_font()
    plt.rcParams["font.family"] = font

    coords = compute_coordinates(lineup["formation"])
    players = lineup["players"]

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
        pitch.annotate(
            player["name"],
            xy=(x - 4.6, y),
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
