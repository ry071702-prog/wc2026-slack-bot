from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import pytest

from scripts.fetch_lineup_auto import (
    JST,
    build_extraction_prompt,
    build_gemini_request,
    build_lineup,
    classify_window,
    extract_lineup_from_text,
    find_active_match,
    main,
    match_player,
    match_players,
    normalize_name,
    order_players,
    parse_gemini_response,
    rss_url,
    strip_html,
    validate_formation,
)
import scripts.fetch_lineup_auto as fetch_lineup_auto

ROOT = Path(__file__).resolve().parents[1]
SQUAD: list[dict[str, Any]] = json.loads(
    (ROOT / "data" / "squads.json").read_text(encoding="utf-8")
)["Japan"]

KICKOFF = datetime(2026, 6, 15, 5, 0, tzinfo=JST)

MATCH_CONFIG = {
    "match_id": 537357,
    "kickoff_jst": "2026-06-15T05:00:00+09:00",
    "opponent": "オランダ",
    "stage": "グループF 第1節",
    "fallback_lineup": "sample",
}

STARTERS = [
    "鈴木彩艶",
    "菅原由勢",
    "板倉滉",
    "冨安健洋",
    "伊藤洋輝",
    "遠藤航",
    "田中碧",
    "鎌田大地",
    "伊東純也",
    "上田綺世",
    "久保建英",
]


# --- 窓判定 ---


@pytest.mark.parametrize(
    ("minutes_before_kickoff", "expected"),
    [
        (51, None),  # 窓の前
        (50, "fetch"),  # 取得試行窓の開始 (境界は含む)
        (35, "fetch"),
        (21, "fetch"),
        (20, "fallback"),  # フォールバック窓の開始 (境界は含む)
        (10, "fallback"),
        (6, "fallback"),
        (5, None),  # KO-5分で窓終了 (境界は含まない)
        (0, None),  # キックオフ
        (-30, None),  # 試合中
    ],
)
def test_classify_window(minutes_before_kickoff: int, expected: Optional[str]) -> None:
    now = KICKOFF - timedelta(minutes=minutes_before_kickoff)
    assert classify_window(now, KICKOFF) == expected


def test_classify_window_handles_timezone_conversion() -> None:
    # UTC で渡しても JST のキックオフと正しく比較できる
    now_utc = (KICKOFF - timedelta(minutes=30)).astimezone(timezone.utc)
    assert classify_window(now_utc, KICKOFF) == "fetch"


def test_find_active_match_picks_match_in_window() -> None:
    config = {
        "matches": [
            MATCH_CONFIG,
            {
                "match_id": 537360,
                "kickoff_jst": "2026-06-21T13:00:00+09:00",
                "opponent": "チュニジア",
                "stage": "グループF 第2節",
                "fallback_lineup": "sample",
            },
        ]
    }
    now = datetime(2026, 6, 21, 12, 30, tzinfo=JST)  # チュニジア戦 KO-30分
    active = find_active_match(config, now)
    assert active is not None
    match, window = active
    assert match["match_id"] == 537360
    assert window == "fetch"


def test_find_active_match_returns_none_outside_windows() -> None:
    now = datetime(2026, 6, 18, 12, 0, tzinfo=JST)
    assert find_active_match({"matches": [MATCH_CONFIG]}, now) is None


def test_find_active_match_skips_broken_entries() -> None:
    config = {"matches": [{"match_id": 1, "kickoff_jst": "not-a-date"}]}
    assert find_active_match(config, KICKOFF) is None


# --- 照合 ---


def test_normalize_name_strips_spaces() -> None:
    assert normalize_name("鈴木 彩艶") == "鈴木彩艶"
    assert normalize_name("鈴木　彩艶") == "鈴木彩艶"


def test_match_player_exact() -> None:
    member = match_player("遠藤航", SQUAD)
    assert member is not None
    assert member["number"] == 6


def test_match_player_surname_only_when_unique() -> None:
    # 「遠藤」は26人中1人なので姓のみでも一意に決まる
    member = match_player("遠藤", SQUAD)
    assert member is not None
    assert member["name_ja"] == "遠藤航"


def test_match_player_ambiguous_surname_returns_none() -> None:
    # 「鈴木」は鈴木彩艶/鈴木淳之介/鈴木唯人の3人いるため曖昧 → 無効
    assert match_player("鈴木", SQUAD) is None


def test_match_player_unknown_returns_none() -> None:
    assert match_player("本田圭佑", SQUAD) is None


def test_match_players_full_eleven() -> None:
    members = match_players(STARTERS, SQUAD)
    assert members is not None
    assert len(members) == 11
    # 氏名・背番号は squads.json 側の値
    assert members[0]["name_ja"] == "鈴木彩艶"
    assert members[0]["number"] == 1


def test_match_players_rejects_ten_matched() -> None:
    names = STARTERS[:10] + ["存在しない選手"]
    assert match_players(names, SQUAD) is None


def test_match_players_rejects_duplicates() -> None:
    names = STARTERS[:10] + ["遠藤航"]  # 遠藤航が2回 (照合先が重複)
    assert match_players(names, SQUAD) is None


def test_match_players_rejects_wrong_count() -> None:
    assert match_players(STARTERS[:10], SQUAD) is None
    assert match_players(STARTERS + ["前田大然"], SQUAD) is None


def test_order_players_puts_gk_first() -> None:
    members = match_players(STARTERS, SQUAD)
    assert members is not None
    shuffled = members[1:] + [members[0]]  # GKを末尾に
    ordered = order_players(shuffled)
    assert ordered is not None
    assert ordered[0]["name_ja"] == "鈴木彩艶"
    # GK以外の相対順序は保たれる
    assert [m["name_ja"] for m in ordered[1:]] == [
        m["name_ja"] for m in shuffled if m["name_ja"] != "鈴木彩艶"
    ]


def test_order_players_rejects_no_gk() -> None:
    members = match_players(STARTERS, SQUAD)
    assert members is not None
    outfield_only = members[1:] + [match_player("前田大然", SQUAD)]
    assert order_players(outfield_only) is None


def test_order_players_rejects_two_gk() -> None:
    members = match_players(STARTERS, SQUAD)
    assert members is not None
    two_keepers = [match_player("大迫敬介", SQUAD)] + members[:10]
    assert order_players(two_keepers) is None


# --- フォーメーション検証 ---


@pytest.mark.parametrize("formation", ["4-3-3", "4-2-3-1", "3-4-2-1", "5-4-1"])
def test_validate_formation_valid(formation: str) -> None:
    assert validate_formation(formation)


@pytest.mark.parametrize(
    "formation",
    [
        "4-3-4",  # 合計11
        "4-4",  # ライン数不足
        "4-3-2-1-1",  # ライン数過多 (regexで弾く)
        "433",
        "4-3-x",
        "",
        None,
        433,
    ],
)
def test_validate_formation_invalid(formation: Any) -> None:
    assert not validate_formation(formation)


# --- lineup 生成 ---


def test_build_lineup_uses_squad_values() -> None:
    members = order_players(match_players(STARTERS, SQUAD) or [])
    assert members is not None
    lineup = build_lineup(MATCH_CONFIG, "4-3-3", members)
    assert lineup["team"] == "Japan"
    assert lineup["opponent"] == "オランダ"
    assert lineup["kickoff_jst"] == "2026-06-15T05:00:00+09:00"
    assert lineup["stage"] == "グループF 第1節"
    assert lineup["formation"] == "4-3-3"
    assert len(lineup["players"]) == 11
    assert lineup["players"][0] == {
        "number": 1,
        "name": "鈴木彩艶",
        "position": "GK",
    }


# --- Gemini リクエスト構築/レスポンス解析 ---


def test_build_gemini_request_url_and_payload() -> None:
    url, payload = build_gemini_request("gemini-2.5-flash", "プロンプト")
    assert url == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent"
    )
    assert payload["contents"][0]["parts"][0]["text"] == "プロンプト"
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    # API キーは URL/ペイロードに含めない (params で渡す)
    assert "key=" not in url


def test_build_extraction_prompt_mentions_opponent_and_text() -> None:
    prompt = build_extraction_prompt("オランダ", "記事本文テキスト")
    assert "オランダ戦" in prompt
    assert "記事本文テキスト" in prompt
    assert '{"found": false}' in prompt


def test_parse_gemini_response_extracts_json() -> None:
    data = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": '{"found": true, "formation": "4-3-3"}'}
                    ]
                }
            }
        ]
    }
    parsed = parse_gemini_response(data)
    assert parsed == {"found": True, "formation": "4-3-3"}


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"candidates": []},
        {"candidates": [{"content": {"parts": [{"text": "not json"}]}}]},
        {"candidates": [{"content": {"parts": [{"text": "[1, 2]"}]}}]},
    ],
)
def test_parse_gemini_response_invalid_returns_none(data: dict) -> None:
    assert parse_gemini_response(data) is None


# --- 記事まわり ---


def test_rss_url_encodes_query() -> None:
    url = rss_url("オランダ")
    assert url.startswith("https://news.google.com/rss/search?q=")
    assert "hl=ja&gl=JP&ceid=JP:ja" in url
    assert " " not in url


def test_strip_html_removes_tags_and_scripts() -> None:
    html_text = (
        "<html><head><script>var x = 1;</script>"
        "<style>.a{color:red}</style></head>"
        "<body><h1>スタメン発表</h1><p>GK&amp;DF</p>"
        "<p>先発は  以下の通り</p></body></html>"
    )
    text = strip_html(html_text)
    assert "<" not in text
    assert "var x" not in text
    assert "color:red" not in text
    assert "GK&DF" in text
    assert "スタメン発表" in text
    assert "先発は 以下の通り" in text


# --- ドライラン: 記事テキスト → 抽出 → 照合 (LLMはモック) ---

SAMPLE_ARTICLE = (
    "【スタメン発表】日本代表、オランダ戦の先発11人を発表！ "
    "森保監督が選んだのは4-3-3。GKは鈴木彩艶。最終ラインは右から"
    "菅原由勢、板倉滉、冨安健洋、伊藤洋輝。中盤は遠藤航をアンカーに"
    "田中碧と鎌田大地。前線は伊東純也、上田綺世、久保建英が並ぶ。"
    "(ゲキサカ)"
)


def fake_gemini_found(prompt: str) -> dict[str, Any]:
    assert "オランダ戦" in prompt
    assert SAMPLE_ARTICLE in prompt
    return {"found": True, "formation": "4-3-3", "players": list(STARTERS)}


def test_extract_lineup_from_text_dry_run() -> None:
    lineup = extract_lineup_from_text(
        SAMPLE_ARTICLE, MATCH_CONFIG, SQUAD, fake_gemini_found
    )
    assert lineup is not None
    assert lineup["formation"] == "4-3-3"
    assert [p["name"] for p in lineup["players"]] == STARTERS
    assert [p["number"] for p in lineup["players"]] == [
        1, 2, 4, 22, 21, 6, 7, 15, 14, 18, 8,
    ]


def test_extract_lineup_from_text_not_found() -> None:
    lineup = extract_lineup_from_text(
        "予想スタメンの記事", MATCH_CONFIG, SQUAD, lambda _: {"found": False}
    )
    assert lineup is None


def test_extract_lineup_from_text_rejects_bad_formation() -> None:
    lineup = extract_lineup_from_text(
        SAMPLE_ARTICLE,
        MATCH_CONFIG,
        SQUAD,
        lambda _: {"found": True, "formation": "4-3-4", "players": STARTERS},
    )
    assert lineup is None


def test_extract_lineup_from_text_rejects_unmatched_players() -> None:
    players = STARTERS[:10] + ["本田圭佑"]
    lineup = extract_lineup_from_text(
        SAMPLE_ARTICLE,
        MATCH_CONFIG,
        SQUAD,
        lambda _: {"found": True, "formation": "4-3-3", "players": players},
    )
    assert lineup is None


def test_extract_lineup_from_text_rejects_llm_none() -> None:
    assert (
        extract_lineup_from_text(SAMPLE_ARTICLE, MATCH_CONFIG, SQUAD, lambda _: None)
        is None
    )


# --- main の窓外/フォールバック/二重投稿防止 (ファイルは tmp_path に差し替え) ---


@pytest.fixture
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config = {"matches": [MATCH_CONFIG]}
    config_path = tmp_path / "auto_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    lineups_dir = tmp_path
    (lineups_dir / "sample.json").write_text("{}", encoding="utf-8")
    state_path = tmp_path / "notified.json"
    monkeypatch.setattr(fetch_lineup_auto, "CONFIG_PATH", config_path)
    monkeypatch.setattr(fetch_lineup_auto, "STATE_PATH", state_path)
    monkeypatch.setattr(fetch_lineup_auto, "LINEUPS_DIR", lineups_dir)
    return tmp_path


def test_main_no_window(
    isolated_paths: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    now = datetime(2026, 6, 14, 12, 0, tzinfo=JST)
    assert main(now=now) == 0
    assert "no window" in capsys.readouterr().out


def test_main_fallback_window_emits_ready(
    isolated_paths: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    now = KICKOFF - timedelta(minutes=15)
    assert main(now=now) == 0
    out = capsys.readouterr().out
    assert "LINEUP_MATCH_ID=537357" in out
    assert "LINEUP_READY=sample FALLBACK=1" in out


def test_main_skips_when_already_posted(
    isolated_paths: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (isolated_paths / "notified.json").write_text(
        json.dumps(
            {
                "digest_dates": [],
                "prematch": [],
                "result": [],
                "lineup": [537357],
            }
        ),
        encoding="utf-8",
    )
    now = KICKOFF - timedelta(minutes=15)
    assert main(now=now) == 0
    out = capsys.readouterr().out
    assert "LINEUP_READY" not in out
    assert "already posted" in out


def test_main_fetch_window_without_api_key(
    isolated_paths: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    now = KICKOFF - timedelta(minutes=40)
    assert main(now=now) == 0
    out = capsys.readouterr().out
    assert "GOOGLE_API_KEY" in out
    assert "LINEUP_READY" not in out


def test_main_fetch_window_success_writes_auto_json(
    isolated_paths: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    auto_path = isolated_paths / "auto.json"
    monkeypatch.setattr(fetch_lineup_auto, "AUTO_LINEUP_PATH", auto_path)

    members = order_players(match_players(STARTERS, SQUAD) or [])
    assert members is not None
    lineup = build_lineup(MATCH_CONFIG, "4-3-3", members)
    monkeypatch.setattr(
        fetch_lineup_auto,
        "attempt_auto_fetch",
        lambda *args, **kwargs: lineup,
    )

    now = KICKOFF - timedelta(minutes=40)
    assert main(now=now) == 0
    out = capsys.readouterr().out
    assert "LINEUP_MATCH_ID=537357" in out
    assert "LINEUP_READY=auto" in out
    saved = json.loads(auto_path.read_text(encoding="utf-8"))
    assert len(saved["players"]) == 11


def test_main_fetch_window_network_error_exits_zero(
    isolated_paths: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

    def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("network down")

    monkeypatch.setattr(fetch_lineup_auto, "attempt_auto_fetch", boom)
    now = KICKOFF - timedelta(minutes=40)
    assert main(now=now) == 0
    out = capsys.readouterr().out
    assert "auto fetch failed" in out
    assert "LINEUP_READY" not in out


def test_auto_config_fallback_files_are_valid():
    """auto_config が参照する全 fallback_lineup の .json が存在し11人で対戦相手が整合。"""
    import json
    from pathlib import Path

    base = Path(__file__).resolve().parent.parent / "data" / "lineups"
    config = json.loads((base / "auto_config.json").read_text(encoding="utf-8"))
    for entry in config["matches"]:
        path = base / f"{entry['fallback_lineup']}.json"
        assert path.exists(), f"missing fallback: {path}"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data["players"]) == 11, path
        assert data["opponent"] == entry["opponent"], path
        assert data["stage"] == entry["stage"], path
