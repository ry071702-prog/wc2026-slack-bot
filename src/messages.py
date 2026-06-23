from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from src.flags import opponent_flag, opponent_reaction
from src.providers.base import Match


@dataclass(frozen=True)
class MatchContext:
    """prematch メッセージ強化用の付随情報。

    fifa_ranks: チーム英語名 -> FIFAランク。
    group_positions: チーム英語名 -> (組レター, 順位)。決勝T専用 (何位通過か)。
    """

    fifa_ranks: dict[str, int] = field(default_factory=dict)
    group_positions: dict[str, tuple[str, int]] = field(default_factory=dict)

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

SITE_BASE_URL = "https://ry071702-prog.github.io/wc2026-slack-bot"
STANDINGS_URL = f"{SITE_BASE_URL}/standings.html"
VIEWING_TEXT_JAPAN = "📺 ABEMA de DAZN / DAZN ／ 地上波（NHK・日テレ）"
VIEWING_TEXT = "📺 ABEMA de DAZN / DAZN"
DIGEST_CONTEXT = "📺 全試合 DAZN ｜ 時刻はJST"
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
    return f"⚽ 今日のW杯 {day.month}/{day.day}({weekday})"


def date_label(day: date) -> str:
    weekday = WEEKDAYS_JA[day.weekday()]
    return f"{day.month}/{day.day}({weekday})"


def _kickoff_hhmm(match: Match) -> str:
    """JST のキックオフ時刻を H:MM (時は0埋めしない) で返す。"""
    jst = match.kickoff_jst
    return f"{jst.hour}:{jst.minute:02d}"


def digest_match_line(match: Match) -> str:
    kickoff = _kickoff_hhmm(match)
    stage = stage_name(match)
    has_score = (
        match.score.home is not None and match.score.away is not None
    )
    if match.is_japan:
        # 日本を常に先頭に置く (日本ファン視点)。スコアも日本側を先に並べる。
        opponent = team_name(japan_opponent(match))
        opp_flag = opponent_flag(japan_opponent(match))
        if match.home == "Japan":
            jp_score, opp_score = match.score.home, match.score.away
        else:
            jp_score, opp_score = match.score.away, match.score.home
        if match.status == "FINISHED" and has_score:
            card = f"日本 {jp_score} - {opp_score} {opp_flag} {opponent}"
            suffix = "　🏁終了"
        elif match.status in ("IN_PLAY", "PAUSED"):
            card = (
                f"日本 {jp_score} - {opp_score} {opp_flag} {opponent}"
                if has_score
                else f"日本 vs {opp_flag} {opponent}"
            )
            suffix = "　🔴LIVE"
        else:
            card = f"日本 vs {opp_flag} {opponent}"
            suffix = ""
        # 閉じ * の直後が全角「（」だとSlackが太字にしないため半角スペースを挟む
        return f"🇯🇵 *{kickoff}　{card}* （{stage}）{suffix}← *日本戦！*"

    home = team_name(match.home)
    away = team_name(match.away)
    hf = opponent_flag(match.home)
    af = opponent_flag(match.away)
    if match.status == "FINISHED" and has_score:
        card = f"{hf} {home} {match.score.home} - {match.score.away} {af} {away}"
        suffix = "　🏁終了"
    elif match.status in ("IN_PLAY", "PAUSED"):
        card = (
            f"{hf} {home} {match.score.home} - {match.score.away} {af} {away}"
            if has_score
            else f"{hf} {home} vs {af} {away}"
        )
        suffix = "　🔴LIVE"
    else:
        card = f"{hf} {home} vs {af} {away}"
        suffix = ""
    return f"`{kickoff}`　{card}（{stage}）{suffix}"


def prematch_text(
    match: Match,
    mention_japan: bool = False,
    context: Optional[MatchContext] = None,
) -> str:
    """開始前メッセージの本文 (引用ブロック)。日本戦は日本を先頭に固定。
    context があれば FIFAランク・組順位 (決勝T)・予想を追記する。"""
    kickoff = _kickoff_hhmm(match)
    if match.is_japan:
        opponent = japan_opponent(match)
        card = (
            f"🇯🇵 *日本*  vs  "
            f"{opponent_flag(opponent)} {team_name(opponent)}"
        )
    else:
        card = (
            f"{opponent_flag(match.home)} {team_name(match.home)}"
            f"  vs  "
            f"{opponent_flag(match.away)} {team_name(match.away)}"
        )
    body = f">{card}\n>🕔 `{kickoff}` KO ｜ {stage_name(match)}"
    if context is not None:
        extra = _context_lines(match, context)
        if extra:
            body += "\n" + "\n".join(extra)
    if match.is_japan and mention_japan:
        body = f"<!here>\n{body}"
    return body


def _ordered_sides(match: Match) -> list[tuple[str, str, str]]:
    """表示順 (日本戦は日本先頭) に (英語名, 表示名, 国旗) を返す。"""
    if match.is_japan:
        opponent = japan_opponent(match)
        return [
            ("Japan", "日本", "🇯🇵"),
            (opponent, team_name(opponent), opponent_flag(opponent)),
        ]
    return [
        (match.home, team_name(match.home), opponent_flag(match.home)),
        (match.away, team_name(match.away), opponent_flag(match.away)),
    ]


def _context_lines(match: Match, context: MatchContext) -> list[str]:
    """FIFAランク・組順位・予想の追記行 (引用ブロック)。情報が無い行は省く。"""
    knockout = match.stage != "GROUP_STAGE"
    lines: list[str] = []
    for name, display, flag in _ordered_sides(match):
        segments: list[str] = []
        rank = context.fifa_ranks.get(name)
        if rank:
            segments.append(f"FIFA {rank}位")
        if knockout:
            position = context.group_positions.get(name)
            if position:
                segments.append(f"{position[0]}組{position[1]}位通過")
        if segments:
            lines.append(f">{flag} {display} ・ " + " ・ ".join(segments))

    favorite = _favorite_line(match, context)
    if favorite:
        lines.append(f">{favorite}")
    return lines


def _favorite_line(match: Match, context: MatchContext) -> Optional[str]:
    """FIFAランク差からの「どちらが勝ちそうか」の一文。両者のランクが必要。"""
    (name_a, disp_a, _), (name_b, disp_b, _) = _ordered_sides(match)
    rank_a = context.fifa_ranks.get(name_a)
    rank_b = context.fifa_ranks.get(name_b)
    if not rank_a or not rank_b or rank_a == rank_b:
        return None
    if rank_a < rank_b:
        fav_disp, fav_rank, other_rank = disp_a, rank_a, rank_b
    else:
        fav_disp, fav_rank, other_rank = disp_b, rank_b, rank_a
    high, low = min(rank_a, rank_b), max(rank_a, rank_b)
    if other_rank - fav_rank <= 3:
        return f"🔮 予想: 互角の対戦（FIFA {high}位 vs {low}位）"
    return f"🔮 予想: {fav_disp} やや優勢（FIFA {fav_rank}位 vs {other_rank}位）"


def result_text(match: Match) -> str:
    """試合結果メッセージの本文 (引用ブロック2行)。日本戦は日本を先頭に固定。"""
    score_suffix = _score_suffix(match)
    stage = stage_name(match, include_matchday=False)
    outcome = _outcome_text(match)
    if match.is_japan:
        opponent = team_name(japan_opponent(match))
        opp_flag = opponent_flag(japan_opponent(match))
        if match.home == "Japan":
            jp_score, opp_score = match.score.home, match.score.away
        else:
            jp_score, opp_score = match.score.away, match.score.home
        score = f"`{_score_value(jp_score)} - {_score_value(opp_score)}`"
        card = f"🇯🇵 *日本*  {score}  {opp_flag} {opponent}{score_suffix}"
    else:
        home = team_name(match.home)
        away = team_name(match.away)
        hf = opponent_flag(match.home)
        af = opponent_flag(match.away)
        side = _winner_side(match)
        home_disp = f"*{home}*" if side == "home" else home
        away_disp = f"*{away}*" if side == "away" else away
        score = (
            f"`{_score_value(match.score.home)} - "
            f"{_score_value(match.score.away)}`"
        )
        card = f"{hf} {home_disp}  {score}  {af} {away_disp}{score_suffix}"
    return f">{card}\n>{outcome}  ｜  {stage}"


def result_context(match: Match) -> str:
    """結果メッセージ下部の context (ハイライト・順位表リンク)。"""
    return (
        f"▶️ <{match_detail_url(match)}|ハイライト・試合詳細>"
        f"　📊 <{STANDINGS_URL}|順位表>"
    )


def match_detail_url(match: Match) -> str:
    return f"{SITE_BASE_URL}/match.html?id={match.id}"


def japan_opponent(match: Match) -> str:
    """日本戦における対戦相手の英語名 (home が日本なら away、そうでなければ home)。"""
    return match.away if match.home == "Japan" else match.home


def _japan_side_label(name: str) -> str:
    """チーム表示名。日本は常に「日本」、それ以外は team_name。"""
    return "日本" if name == "Japan" else team_name(name)


def _poll_kickoff_label(match: Match) -> str:
    """ポール用キックオフ表記 "M/D(曜) `H:MM`" (時は0埋めしない・時刻はバッククォート)。"""
    jst = match.kickoff_jst
    weekday = WEEKDAYS_JA[jst.weekday()]
    return f"{jst.month}/{jst.day}({weekday}) `{jst.hour}:{jst.minute:02d}`"


def japan_poll_text(match: Match) -> str:
    """勝敗予想リアクション投票の募集メッセージ (mrkdwn)。日本を先頭に固定。"""
    opponent = japan_opponent(match)
    opponent_name = team_name(opponent)
    opp_flag = opponent_flag(opponent)
    return (
        f"🇯🇵 *日本 vs {opp_flag} {opponent_name}* 結果予想！⚽\n"
        f"{_poll_kickoff_label(match)} KO ｜ {stage_name(match)}\n"
        "\n"
        "下のリアクションで投票しよう👇\n"
        "🇯🇵 日本が勝つ\n"
        "🤝 引き分け\n"
        f"{opp_flag} {opponent_name}が勝つ\n"
        "\n"
        "（試合後にみんなの予想結果を発表📊）"
    )


def japan_poll_reactions(match: Match) -> list[str]:
    """ポールに付ける種リアクション名。順に 日本勝ち / 引き分け / 相手勝ち。
    相手の国旗が解決できない場合も opponent_reaction が ⚽ にフォールバックするため
    空文字 (Slack invalid_name) にはならない。"""
    return ["jp", "handshake", opponent_reaction(japan_opponent(match))]


def poll_outcome(match: Match) -> str:
    """実スコアから的中した選択肢を返す ("japan" / "draw" / "opp")。"""
    side = _winner_side(match)
    japan_side = "home" if match.home == "Japan" else "away"
    if side == "draw":
        return "draw"
    return "japan" if side == japan_side else "opp"


def japan_poll_result_text(
    match: Match,
    votes_jp: int,
    votes_draw: int,
    votes_opp: int,
    winner_names: Optional[list[str]] = None,
    winner_extra: int = 0,
) -> str:
    """ポール集計の発表メッセージ。実スコアから的中選択肢に🎯マーカーを付ける。
    winner_names が渡されたら的中者の名前も列挙する (winner_extra=名前に載らない残り人数)。"""
    opponent = japan_opponent(match)
    opponent_name = team_name(opponent)
    opp_flag = opponent_flag(opponent)
    # 日本を先頭に固定 (日本側のスコアを先に出す)
    japan_is_home = match.home == "Japan"
    jp_score = match.score.home if japan_is_home else match.score.away
    op_score = match.score.away if japan_is_home else match.score.home
    score_line = (
        f"🇯🇵 日本 {_score_value(jp_score)} - "
        f"{_score_value(op_score)} {opp_flag} {opponent_name}"
    )

    outcome = poll_outcome(match)

    marker = " ← 🎯的中！"
    jp_marker = marker if outcome == "japan" else ""
    draw_marker = marker if outcome == "draw" else ""
    opp_marker = marker if outcome == "opp" else ""

    winners = {"japan": votes_jp, "draw": votes_draw, "opp": votes_opp}[outcome]
    if winners <= 0:
        closing = "的中した人はいませんでした…次戦に期待！😢"
    elif winner_names:
        names = "・".join(winner_names)
        if winner_extra > 0:
            names += f" ほか{winner_extra}人"
        closing = f"🎯 *的中者* （{winners}人）: {names}\nおみごと！🎉"
    else:
        closing = f"的中した{winners}人、おみごと！🎉"

    return (
        f"📊 *みんなの予想結果* （{score_line}）\n"
        f"🇯🇵 日本勝利: {votes_jp}票{jp_marker}\n"
        f"🤝 引き分け: {votes_draw}票{draw_marker}\n"
        f"{opp_flag} {opponent_name}勝利: {votes_opp}票{opp_marker}\n"
        "\n"
        f"{closing}"
    )


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
