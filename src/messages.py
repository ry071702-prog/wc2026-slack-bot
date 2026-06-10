from __future__ import annotations

from datetime import date
from urllib.parse import quote_plus

from src.providers.base import Match

TEAM_NAMES = {
    "Algeria": "アルジェリア",
    "Argentina": "アルゼンチン",
    "Australia": "オーストラリア",
    "Austria": "オーストリア",
    "Belgium": "ベルギー",
    "Bosnia-Herzegovina": "ボスニア・ヘルツェゴビナ",
    "Brazil": "ブラジル",
    "Canada": "カナダ",
    "Cape Verde": "カーボベルデ",
    "Cape Verde Islands": "カーボベルデ",
    "Congo DR": "コンゴ民主共和国",
    "Chile": "チリ",
    "China PR": "中国",
    "Colombia": "コロンビア",
    "Costa Rica": "コスタリカ",
    "Croatia": "クロアチア",
    "Curaçao": "キュラソー",
    "Czechia": "チェコ",
    "Denmark": "デンマーク",
    "Ecuador": "エクアドル",
    "Egypt": "エジプト",
    "England": "イングランド",
    "France": "フランス",
    "Germany": "ドイツ",
    "Ghana": "ガーナ",
    "Haiti": "ハイチ",
    "IR Iran": "イラン",
    "Iran": "イラン",
    "Iraq": "イラク",
    "Italy": "イタリア",
    "Ivory Coast": "コートジボワール",
    "Côte d'Ivoire": "コートジボワール",
    "Japan": "日本",
    "Jordan": "ヨルダン",
    "Korea Republic": "韓国",
    "South Korea": "韓国",
    "Mexico": "メキシコ",
    "Morocco": "モロッコ",
    "Netherlands": "オランダ",
    "New Zealand": "ニュージーランド",
    "Nigeria": "ナイジェリア",
    "Norway": "ノルウェー",
    "Panama": "パナマ",
    "Paraguay": "パラグアイ",
    "Peru": "ペルー",
    "Poland": "ポーランド",
    "Portugal": "ポルトガル",
    "Qatar": "カタール",
    "Saudi Arabia": "サウジアラビア",
    "Scotland": "スコットランド",
    "Senegal": "セネガル",
    "Serbia": "セルビア",
    "South Africa": "南アフリカ",
    "Spain": "スペイン",
    "Sweden": "スウェーデン",
    "Switzerland": "スイス",
    "Tunisia": "チュニジア",
    "Türkiye": "トルコ",
    "Turkey": "トルコ",
    "Ukraine": "ウクライナ",
    "United States": "アメリカ",
    "USA": "アメリカ",
    "Uruguay": "ウルグアイ",
    "Uzbekistan": "ウズベキスタン",
    "Venezuela": "ベネズエラ",
    "Wales": "ウェールズ",
}

KNOCKOUT_STAGE_NAMES = {
    "LAST_32": "ラウンド32",
    "LAST_16": "ラウンド16",
    "QUARTER_FINALS": "準々決勝",
    "SEMI_FINALS": "準決勝",
    "THIRD_PLACE": "3位決定戦",
    "FINAL": "決勝",
}

VIEWING_TEXT_JAPAN = "📺 ABEMA de DAZN / DAZN ／ 地上波（NHK・日テレ）"
VIEWING_TEXT = "📺 ABEMA de DAZN / DAZN"
DIGEST_CONTEXT = (
    "📺 ABEMA de DAZN / DAZN（全試合）｜日本戦は地上波も｜時刻はJST"
)
WEEKDAYS_JA = "月火水木金土日"


def team_name(name: str) -> str:
    return TEAM_NAMES.get(name, name)


def stage_name(match: Match, include_matchday: bool = True) -> str:
    if match.stage == "GROUP_STAGE":
        group = _group_letter(match.group)
        label = f"グループ{group}" if group else "グループステージ"
        if include_matchday and match.matchday is not None:
            return f"{label} 第{match.matchday}節"
        return label
    return KNOCKOUT_STAGE_NAMES.get(match.stage, match.stage or "ステージ未定")


def digest_title(day: date) -> str:
    weekday = WEEKDAYS_JA[day.weekday()]
    return f"⚽ 今日のW杯（{day.month}/{day.day} {weekday}）"


def digest_match_line(match: Match) -> str:
    kickoff = match.kickoff_jst.strftime("%H:%M")
    card = f"{team_name(match.home)} vs {team_name(match.away)}"
    stage = stage_name(match)
    if match.is_japan:
        return f"🇯🇵 *{kickoff}　{card}*（{stage}）← *日本戦！*"
    return f"{kickoff}　{card}（{stage}）"


def prematch_text(match: Match, mention_japan: bool = False) -> str:
    prefix = "<!here> " if match.is_japan and mention_japan else ""
    flag = "🇯🇵 " if match.is_japan else ""
    kickoff = match.kickoff_jst.strftime("%H:%M")
    card = f"{team_name(match.home)} vs {team_name(match.away)}"
    viewing = VIEWING_TEXT_JAPAN if match.is_japan else VIEWING_TEXT
    return (
        f"{prefix}🔔 *まもなくキックオフ！（{kickoff}〜）*\n"
        f"{flag}*{card}*｜{stage_name(match)}\n"
        f"{viewing}"
    )


def result_text(match: Match) -> str:
    flag = "🇯🇵 " if match.is_japan else ""
    home_score = _score_value(match.score.home)
    away_score = _score_value(match.score.away)
    score_suffix = _score_suffix(match)
    outcome = _outcome_text(match)
    stage = stage_name(match, include_matchday=False)
    return (
        "🏁 *試合終了*\n"
        f"{flag}{team_name(match.home)} *{home_score} - {away_score}* "
        f"{team_name(match.away)}{score_suffix}\n"
        f"{outcome} {stage}\n"
        f"▶️ <{highlight_search_url(match)}|ハイライトを探す (YouTube)>"
    )


def highlight_search_url(match: Match) -> str:
    query = (
        f"{team_name(match.home)} vs {team_name(match.away)} ハイライト W杯"
    )
    return f"https://www.youtube.com/results?search_query={quote_plus(query)}"


def _group_letter(group: str | None) -> str:
    if not group:
        return ""
    return group.removeprefix("GROUP_")


def _score_value(value: int | None) -> str:
    return "-" if value is None else str(value)


def _score_suffix(match: Match) -> str:
    if (
        match.score.penalties_home is not None
        and match.score.penalties_away is not None
    ):
        return (
            f" (PK {match.score.penalties_home}-{match.score.penalties_away})"
        )
    if match.score.duration == "EXTRA_TIME":
        return " (延長)"
    return ""


def _outcome_text(match: Match) -> str:
    home_score = match.score.home
    away_score = match.score.away
    if home_score is None or away_score is None:
        return "結果確定"

    comparison = _winner_side(match)
    if match.is_japan:
        japan_side = "home" if match.home == "Japan" else "away"
        if comparison == "draw":
            return "🤝 *ドロー*"
        if comparison == japan_side:
            return "🎉 *日本、勝利！*"
        return "😢 *惜敗…次戦に期待！*"

    if comparison == "draw":
        return "🤝 *ドロー*"
    winner = match.home if comparison == "home" else match.away
    return f"🏆 *{team_name(winner)}の勝利*"


def _winner_side(match: Match) -> str:
    penalty_home = match.score.penalties_home
    penalty_away = match.score.penalties_away
    if penalty_home is not None and penalty_away is not None:
        if penalty_home > penalty_away:
            return "home"
        if penalty_home < penalty_away:
            return "away"

    home_score = match.score.home
    away_score = match.score.away
    if home_score is None or away_score is None or home_score == away_score:
        return "draw"
    return "home" if home_score > away_score else "away"
