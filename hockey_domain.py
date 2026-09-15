from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from enum import StrEnum


class StageKind(StrEnum):
    REGULAR = "regular"
    PLAY_IN = "play_in"
    PLAYOFF = "playoff"
    OTHER = "other"


class QualificationState(StrEnum):
    DIRECT = "direct_playoff"
    PLAY_IN = "play_in"
    OUTSIDE = "outside"
    POSTSEASON = "postseason"
    UNKNOWN = "unknown"


class SeriesStatus(StrEnum):
    UPCOMING = "upcoming"
    ACTIVE = "active"
    FINISHED = "finished"


@dataclass(frozen=True)
class Season:
    league: str
    name: str
    starts_on: date | None = None
    ends_on: date | None = None


@dataclass(frozen=True)
class Stage:
    league: str
    season: str
    name: str
    kind: StageKind
    source_url: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None


@dataclass
class Series:
    league: str
    season: str
    stage: str
    team_a: str
    team_b: str
    wins_a: int = 0
    wins_b: int = 0
    wins_needed: int | None = None
    status: SeriesStatus = SeriesStatus.UPCOMING
    source_url: str | None = None
    game_ids: list[str] = field(default_factory=list)

    @property
    def score_text(self) -> str:
        return f"{self.wins_a}:{self.wins_b}"


@dataclass(frozen=True)
class Venue:
    name: str
    city: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class MatchIdentity:
    source: str
    source_game_id: str
    league: str
    home_team: str
    away_team: str
    start_at: datetime
