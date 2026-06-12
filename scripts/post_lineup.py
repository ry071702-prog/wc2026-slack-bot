"""スタメン図PNGを生成して Slack に投稿する (files_upload_v2 相当)。

Bot Token (xoxb, files:write) で以下の3ステップを requests で行う
(slack_sdk は追加しない):
  1. files.getUploadURLExternal でアップロードURLを取得
  2. アップロードURLに PNG bytes を POST
  3. files.completeUploadExternal でチャンネル投稿 (initial_comment 付き)

env: SLACK_BOT_TOKEN, SLACK_CHANNEL_ID, (任意) LINEUP_PREFIX (例 "[テスト] ")
CLI: python scripts/post_lineup.py data/lineups/sample.json
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.render_lineup import load_lineup, render_lineup

SLACK_API = "https://slack.com/api"

# position 表記 → 表示グループ
POSITION_GROUPS = {
    "GK": "GK",
    "RB": "DF",
    "CB": "DF",
    "LB": "DF",
    "RWB": "DF",
    "LWB": "DF",
    "DF": "DF",
    "DM": "MF",
    "CM": "MF",
    "AM": "MF",
    "MF": "MF",
    "RW": "FW",
    "LW": "FW",
    "CF": "FW",
    "ST": "FW",
    "SS": "FW",
    "FW": "FW",
}
GROUP_ORDER = ("GK", "DF", "MF", "FW")


def classify_position(position: str) -> str:
    """RB/CB/LB→DF, DM/CM/AM→MF, RW/LW/CF/ST→FW などに分類する。"""
    group = POSITION_GROUPS.get(position.upper())
    if group is None:
        raise ValueError(f"unknown position: {position!r}")
    return group


def build_initial_comment(lineup: dict[str, Any], prefix: str = "") -> str:
    groups: dict[str, list[str]] = {group: [] for group in GROUP_ORDER}
    for player in lineup["players"]:
        groups[classify_position(player["position"])].append(
            f"{player['number']} {player['name']}"
        )

    lines = [
        f"{prefix}🇯🇵 *日本代表スタメン発表！*"
        f"｜{lineup['formation']}"
        f"｜vs {lineup['opponent']}（{lineup['stage']}）"
    ]
    for group in GROUP_ORDER:
        if groups[group]:
            lines.append(f"{group}: " + " / ".join(groups[group]))
    bench_note = lineup.get("bench_note")
    if bench_note:
        lines.append(bench_note)
    return "\n".join(lines)


def _check_api(response: requests.Response, api: str) -> dict[str, Any]:
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"{api} failed: {data.get('error')}")
    return data


def upload_png_to_slack(
    token: str,
    channel_id: str,
    png_path: Path,
    initial_comment: str,
    title: str = "日本 スタメン",
    session: Optional[requests.Session] = None,
    timeout: float = 30.0,
) -> None:
    session = session or requests.Session()
    headers = {"Authorization": f"Bearer {token}"}
    png_bytes = png_path.read_bytes()

    # 1. アップロードURL取得
    data = _check_api(
        session.post(
            f"{SLACK_API}/files.getUploadURLExternal",
            headers=headers,
            data={"filename": png_path.name, "length": len(png_bytes)},
            timeout=timeout,
        ),
        "files.getUploadURLExternal",
    )

    # 2. PNG bytes をアップロード
    upload_response = session.post(
        data["upload_url"], data=png_bytes, timeout=timeout
    )
    upload_response.raise_for_status()

    # 3. アップロード完了 + チャンネル投稿
    _check_api(
        session.post(
            f"{SLACK_API}/files.completeUploadExternal",
            headers=headers,
            json={
                "files": [{"id": data["file_id"], "title": title}],
                "channel_id": channel_id,
                "initial_comment": initial_comment,
            },
            timeout=timeout,
        ),
        "files.completeUploadExternal",
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="スタメン図をSlackに投稿する")
    parser.add_argument("lineup_json", help="lineup JSONパス (data/lineups/*.json)")
    args = parser.parse_args(argv)

    token = os.environ.get("SLACK_BOT_TOKEN")
    channel_id = os.environ.get("SLACK_CHANNEL_ID")
    prefix = os.environ.get("LINEUP_PREFIX", "")
    if not (token and channel_id):
        print("error: SLACK_BOT_TOKEN and SLACK_CHANNEL_ID are required")
        return 1

    try:
        lineup = load_lineup(Path(args.lineup_json))
        comment = build_initial_comment(lineup, prefix=prefix)
        with tempfile.TemporaryDirectory() as tmp_dir:
            png_path = render_lineup(lineup, Path(tmp_dir) / "lineup.png")
            upload_png_to_slack(
                token,
                channel_id,
                png_path,
                initial_comment=comment,
                title=lineup.get("title", "日本 スタメン"),
            )
    except Exception as exc:  # noqa: BLE001 — CLIなので本文を出して非0終了
        print(f"error: {exc}")
        return 1

    print(f"Slack files upload succeeded: channel={channel_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
