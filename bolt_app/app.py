"""W杯2026 予想Bot (Socket Mode)。

/yosou  : 優勝予想の入力・上書き (モーダル)
/ranking: 優勝予想 生存者ランキングの表示

必要な環境変数:
  SLACK_BOT_TOKEN  (xoxb-) chat:write / commands 承認済みであること
  SLACK_APP_TOKEN  (xapp-) connections:write
"""
from __future__ import annotations

import os
import sys
import threading
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bolt_app.storage import create_store  # noqa: E402
from src.messages import TEAM_NAMES  # noqa: E402
JAPAN_RESULTS = [
    "GL敗退",
    "ラウンド32",
    "ラウンド16",
    "ベスト8",
    "ベスト4",
    "準優勝",
    "優勝",
]

app = App(token=os.environ["SLACK_BOT_TOKEN"])
store = create_store()


def load_predictions() -> dict:
    return store.load()


def save_predictions(predictions: dict) -> None:
    store.save(predictions)


class HealthHandler(BaseHTTPRequestHandler):
    """HF Spaces のスリープ防止用 (cron-job.org が定期ping)。"""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"wc2026 bolt: ok")

    def log_message(self, *args):
        pass


def start_health_server() -> None:
    port = int(os.environ.get("PORT", "7860"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"health server: 0.0.0.0:{port}")


def team_options() -> list[dict]:
    # TODO(P1): teams.json (出場48カ国の確定リスト) に差し替える
    names = sorted(set(TEAM_NAMES.values()))
    return [
        {
            "text": {"type": "plain_text", "text": name},
            "value": name,
        }
        for name in names[:100]
    ]


@app.command("/yosou")
def open_yosou_modal(ack, body, client):
    ack()
    existing = load_predictions().get(body["user_id"], {})
    client.views_open(
        trigger_id=body["trigger_id"],
        view={
            "type": "modal",
            "callback_id": "yosou_submit",
            "private_metadata": body.get("channel_id", ""),
            "title": {"type": "plain_text", "text": "W杯 優勝予想"},
            "submit": {"type": "plain_text", "text": "送信 (上書きOK)"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "nickname",
                    "label": {
                        "type": "plain_text",
                        "text": "ニックネーム（ランキングで公開されます）",
                    },
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "v",
                        "initial_value": existing.get("nickname", ""),
                        "max_length": 20,
                    },
                },
                {
                    "type": "input",
                    "block_id": "champion",
                    "label": {"type": "plain_text", "text": "優勝国"},
                    "element": {
                        "type": "static_select",
                        "action_id": "v",
                        "options": team_options(),
                    },
                },
                {
                    "type": "input",
                    "block_id": "japan_result",
                    "label": {"type": "plain_text", "text": "日本の最終成績"},
                    "element": {
                        "type": "static_select",
                        "action_id": "v",
                        "options": [
                            {
                                "text": {"type": "plain_text", "text": r},
                                "value": r,
                            }
                            for r in JAPAN_RESULTS
                        ],
                    },
                },
                {
                    "type": "input",
                    "block_id": "top_scorer",
                    "optional": True,
                    "label": {"type": "plain_text", "text": "得点王（任意）"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "v",
                        "initial_value": existing.get("top_scorer", ""),
                    },
                },
                {
                    "type": "input",
                    "block_id": "comment",
                    "optional": True,
                    "label": {"type": "plain_text", "text": "ひとこと（任意）"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "v",
                        "initial_value": existing.get("comment", ""),
                    },
                },
            ],
        },
    )


@app.view("yosou_submit")
def handle_yosou_submit(ack, body, view, client):
    ack()
    values = view["state"]["values"]

    def value_of(block_id: str) -> str:
        data = values[block_id]["v"]
        if data["type"] == "static_select":
            selected = data.get("selected_option")
            return selected["value"] if selected else ""
        return data.get("value") or ""

    user_id = body["user"]["id"]
    predictions = load_predictions()
    predictions[user_id] = {
        "nickname": value_of("nickname"),
        "champion": value_of("champion"),
        "japan_result": value_of("japan_result"),
        "top_scorer": value_of("top_scorer"),
        "comment": value_of("comment"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    save_predictions(predictions)
    entry = predictions[user_id]
    client.chat_postEphemeral(
        channel=view.get("private_metadata") or user_id,
        user=user_id,
        text=(
            f"✅ 予想を受け付けました！ "
            f"優勝: *{entry['champion']}* / 日本: *{entry['japan_result']}*"
            "（/yosou でいつでも変更できます）"
        ),
    )


@app.command("/ranking")
def show_ranking(ack, respond):
    ack()
    predictions = load_predictions()
    if not predictions:
        respond("まだ予想がありません。`/yosou` で最初の予想者になろう！")
        return

    # TODO(P2): results.json と突合した「生存者ランキング」「得点ランキング」に差し替える
    champions = Counter(p["champion"] for p in predictions.values())
    lines = [
        f"{i}. *{team}* — {count}人"
        for i, (team, count) in enumerate(champions.most_common(10), start=1)
    ]
    respond(
        f"🏆 *優勝予想の分布* （回答 {len(predictions)}人）\n" + "\n".join(lines)
    )


if __name__ == "__main__":
    start_health_server()
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
