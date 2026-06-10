"""Match data providers."""

from src.providers.base import Match, MatchScore, Provider
from src.providers.football_data import FootballDataProvider

__all__ = ["FootballDataProvider", "Match", "MatchScore", "Provider"]
