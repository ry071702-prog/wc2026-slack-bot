"""予想データの保存先。

GH_TOKEN があれば GitHub リポジトリの data/predictions.json (Contents API) に永続化する
(HF Spaces はファイルシステムが揮発性のため)。無ければローカルファイル (Mac での開発用)。
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import requests

LOCAL_PATH = Path(__file__).resolve().parent.parent / "data" / "predictions.json"
REPO = os.environ.get("PREDICTIONS_REPO", "ry071702-prog/wc2026-slack-bot")
FILE_PATH = "data/predictions.json"
API_URL = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"


class GitHubStore:
    def __init__(self, token: str) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            }
        )

    def _fetch(self) -> tuple[dict, str | None]:
        response = self.session.get(API_URL, params={"ref": "main"}, timeout=10)
        if response.status_code == 404:
            return {}, None
        response.raise_for_status()
        payload = response.json()
        content = base64.b64decode(payload["content"]).decode("utf-8")
        return json.loads(content), payload["sha"]

    def load(self) -> dict:
        return self._fetch()[0]

    def save(self, predictions: dict) -> None:
        body = {
            "message": "chore: update predictions [skip ci]",
            "content": base64.b64encode(
                (
                    json.dumps(predictions, ensure_ascii=False, indent=2) + "\n"
                ).encode("utf-8")
            ).decode("ascii"),
            "branch": "main",
        }
        for attempt in range(2):
            _, sha = self._fetch()
            if sha:
                body["sha"] = sha
            response = self.session.put(API_URL, json=body, timeout=10)
            if response.status_code == 409 and attempt == 0:
                continue  # sha が古い (競合) → 取り直して1回だけリトライ
            response.raise_for_status()
            return


class LocalStore:
    def load(self) -> dict:
        try:
            return json.loads(LOCAL_PATH.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save(self, predictions: dict) -> None:
        LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOCAL_PATH.write_text(
            json.dumps(predictions, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def create_store():
    token = os.environ.get("GH_TOKEN", "").strip()
    if token:
        print(f"predictions store: GitHub ({REPO}/{FILE_PATH})")
        return GitHubStore(token)
    print(f"predictions store: local ({LOCAL_PATH})")
    return LocalStore()
