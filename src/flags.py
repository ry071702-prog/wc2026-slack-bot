from __future__ import annotations

"""出場国の英語名 → Slack国旗リアクション名 / Unicode国旗絵文字 への純関数変換。

外部依存なし。football-data の英語名 (src/messages.py の TEAM_NAMES キー) を入力とする。
"""

# football-data 英語名 → ISO 3166-1 alpha-2 (小文字)。
# Japan は Slack 上の特別名 "jp" 扱い、England/Scotland/Wales は ISO に無いため
# 後段の関数で flag-england 等に展開する特例値を持たせる。
TEAM_ISO: dict[str, str] = {
    "Japan": "jp",
    "Netherlands": "nl",
    "Tunisia": "tn",
    "Sweden": "se",
    "Spain": "es",
    "Mexico": "mx",
    "South Africa": "za",
    "Canada": "ca",
    "United States": "us",
    "USA": "us",
    "South Korea": "kr",
    "Korea Republic": "kr",
    "Czechia": "cz",
    "Bosnia-Herzegovina": "ba",
    "Paraguay": "py",
    "Saudi Arabia": "sa",
    "Uruguay": "uy",
    "Cape Verde Islands": "cv",
    "Cape Verde": "cv",
    "Argentina": "ar",
    "Brazil": "br",
    "France": "fr",
    "Germany": "de",
    "Portugal": "pt",
    "Belgium": "be",
    "Croatia": "hr",
    "Morocco": "ma",
    "Senegal": "sn",
    "Egypt": "eg",
    "Algeria": "dz",
    "Ghana": "gh",
    "Ivory Coast": "ci",
    "Côte d'Ivoire": "ci",
    "Cote d'Ivoire": "ci",  # アクセント無し表記ゆれの保険
    "Ecuador": "ec",
    "Colombia": "co",
    "Panama": "pa",
    "Haiti": "ht",
    "Curaçao": "cw",
    "Norway": "no",
    "Austria": "at",
    "Switzerland": "ch",
    "Turkey": "tr",
    "Türkiye": "tr",
    "Jordan": "jo",
    "Uzbekistan": "uz",
    "Iran": "ir",
    "IR Iran": "ir",
    "Iraq": "iq",
    "Qatar": "qa",
    "Australia": "au",
    "New Zealand": "nz",
    "Congo DR": "cd",
    "DR Congo": "cd",  # 表記ゆれの保険 (football-data は "Congo DR")
    # 2026 未出場だが TEAM_NAMES に存在する国 (決勝Tや表記ゆれの防御用)
    "Chile": "cl",
    "China PR": "cn",
    "China": "cn",
    "Costa Rica": "cr",
    "Denmark": "dk",
    "Italy": "it",
    "Nigeria": "ng",
    "Peru": "pe",
    "Poland": "pl",
    "Serbia": "rs",
    "Ukraine": "ua",
    "Venezuela": "ve",
    # ISO に無い英国構成国は特例値を持たせ、flag-england 等に展開する
    "England": "england",
    "Scotland": "scotland",
    "Wales": "wales",
}

# 国旗が解決できない相手のフォールバック (リアクション名 / 絵文字)。
# これにより未マッピング相手でも「相手勝利」票が壊れない。
FALLBACK_REACTION = "soccer"
FALLBACK_EMOJI = "⚽"  # ⚽

# 英国構成国の Unicode 旗 (タグシーケンス)
SUBDIVISION_EMOJI: dict[str, str] = {
    "england": "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F",
    "scotland": "\U0001F3F4\U000E0067\U000E0062\U000E0073\U000E0063\U000E0074\U000E007F",
    "wales": "\U0001F3F4\U000E0067\U000E0062\U000E0077\U000E006C\U000E0073\U000E007F",
}


def flag_reaction(name: str) -> str:
    """英語名 → Slack リアクション名。日本は "jp"、英国構成国は "flag-england" 等、
    それ以外は "flag-{iso}"。未知名は "" を返す。"""
    if name == "Japan":
        return "jp"
    iso = TEAM_ISO.get(name)
    if not iso:
        return ""
    return f"flag-{iso}"


def flag_emoji(name: str) -> str:
    """英語名 → Unicode 国旗絵文字。未知名は "" を返す。"""
    if name == "Japan":
        return "\U0001F1EF\U0001F1F5"  # 🇯🇵
    iso = TEAM_ISO.get(name)
    if not iso:
        return ""
    if iso in SUBDIVISION_EMOJI:
        return SUBDIVISION_EMOJI[iso]
    return "".join(chr(0x1F1E6 + ord(char) - ord("a")) for char in iso)


def opponent_reaction(name: str) -> str:
    """相手勝利の種リアクション名。未知名は ⚽(soccer) にフォールバックし、
    空文字 (Slack invalid_name) になるのを防ぐ。"""
    return flag_reaction(name) or FALLBACK_REACTION


def opponent_flag(name: str) -> str:
    """相手の表示用国旗。未知名は ⚽ にフォールバックする。"""
    return flag_emoji(name) or FALLBACK_EMOJI
