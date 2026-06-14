from __future__ import annotations

from src.flags import flag_emoji, flag_reaction

ENGLAND_EMOJI = (
    "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F"
)


def test_flag_reaction_japan_is_jp() -> None:
    assert flag_reaction("Japan") == "jp"


def test_flag_reaction_regular_countries() -> None:
    assert flag_reaction("Netherlands") == "flag-nl"
    assert flag_reaction("Sweden") == "flag-se"
    assert flag_reaction("Tunisia") == "flag-tn"
    assert flag_reaction("United States") == "flag-us"
    assert flag_reaction("South Korea") == "flag-kr"


def test_flag_reaction_uk_subdivisions() -> None:
    assert flag_reaction("England") == "flag-england"
    assert flag_reaction("Scotland") == "flag-scotland"
    assert flag_reaction("Wales") == "flag-wales"


def test_flag_reaction_unknown_is_empty() -> None:
    assert flag_reaction("Atlantis") == ""
    assert flag_reaction("") == ""


def test_flag_emoji_japan() -> None:
    assert flag_emoji("Japan") == "🇯🇵"


def test_flag_emoji_regular_countries() -> None:
    assert flag_emoji("Netherlands") == "🇳🇱"
    assert flag_emoji("Sweden") == "🇸🇪"
    assert flag_emoji("Tunisia") == "🇹🇳"
    assert flag_emoji("United States") == "🇺🇸"
    assert flag_emoji("South Korea") == "🇰🇷"


def test_flag_emoji_england() -> None:
    assert flag_emoji("England") == ENGLAND_EMOJI


def test_flag_emoji_unknown_is_empty() -> None:
    assert flag_emoji("Atlantis") == ""


def test_team_iso_covers_all_team_names():
    # TEAM_NAMES に載る全チームが空でないリアクション名に解決される (相手勝利票が壊れない)
    from src.flags import opponent_reaction
    from src.messages import TEAM_NAMES

    empties = [name for name in TEAM_NAMES if not opponent_reaction(name)]
    assert empties == []


def test_opponent_reaction_falls_back_to_soccer():
    from src.flags import opponent_flag, opponent_reaction

    assert opponent_reaction("Netherlands") == "flag-nl"
    assert opponent_reaction("Atlantis") == "soccer"  # 未知名
    assert opponent_flag("Atlantis") == "⚽"


def test_formerly_missing_isos_resolve():
    from src.flags import flag_reaction

    for team in ("Italy", "Chile", "Denmark", "Serbia", "Ukraine"):
        assert flag_reaction(team).startswith("flag-")
