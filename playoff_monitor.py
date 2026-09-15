from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import Counter

from hockey_domain import QualificationState, Series, SeriesStatus, StageKind


@dataclass(frozen=True)
class PlayoffSnapshot:
    team_key: str
    team_name: str
    league: str
    stage_kind: StageKind
    stage_name: str
    summary: str
    source_url: str | None
    series: Series | None = None
    qualification_state: QualificationState = QualificationState.UNKNOWN
    position: int | None = None


def _norm(value: str) -> str:
    return " ".join(str(value or "").casefold().replace("ё", "е").split())


def _kind_from_title(title: str) -> StageKind:
    text = _norm(title)
    if "плей-ин" in text or "play-in" in text or "play in" in text:
        return StageKind.PLAY_IN
    if "плей-офф" in text or "playoff" in text or "кубок" in text:
        return StageKind.PLAYOFF
    return StageKind.REGULAR


def _team_column(headers: list[str]) -> int:
    for i, h in enumerate(headers):
        if _norm(h) in {"команда", "команды", "клуб"}:
            return i
    return 1 if len(headers) > 1 else 0


def _qualification_from_table(table: dict, team_name: str) -> tuple[QualificationState, int | None]:
    headers = list(table.get("headers") or [])
    rows = list(table.get("rows") or [])
    idx = _team_column(headers)
    position = None
    for pos, row in enumerate(rows, 1):
        if idx < len(row) and _norm(row[idx]) == _norm(team_name):
            position = pos
            break
    if position is None:
        return QualificationState.UNKNOWN, None

    zones = table.get("zones") or {}
    zone = zones.get(position)
    if zone == "direct":
        return QualificationState.DIRECT, position
    if zone == "playin":
        return QualificationState.PLAY_IN, position
    if zones:
        return QualificationState.OUTSIDE, position
    return QualificationState.UNKNOWN, position


def _series_from_games(team_name: str, league: str, stage_name: str, games, now: datetime) -> Series | None:
    # Series detection is intentionally enabled only once the source itself says
    # that we are in play-in/playoff. Repeated opponents are common in regular
    # seasons and must not be mistaken for a series.
    recent = [
        g for g in games
        if team_name in (g.home_team, g.away_team)
        and now - timedelta(days=35) <= g.start_at <= now + timedelta(days=35)
    ]
    if not recent:
        return None

    opponents = []
    for g in recent:
        opponents.append(g.away_team if g.home_team == team_name else g.home_team)
    if not opponents:
        return None
    opponent, count = Counter(opponents).most_common(1)[0]
    if count < 2:
        return None

    series_games = [g for g in recent if opponent in (g.home_team, g.away_team)]
    wins_team = 0
    wins_opp = 0
    for g in series_games:
        if g.status != "finished" or g.home_score is None or g.away_score is None:
            continue
        winner = g.home_team if g.home_score > g.away_score else g.away_team
        if winner == team_name:
            wins_team += 1
        elif winner == opponent:
            wins_opp += 1

    has_future = any(g.status != "finished" and g.start_at >= now - timedelta(hours=4) for g in series_games)
    status = SeriesStatus.ACTIVE if has_future else SeriesStatus.UPCOMING
    if not has_future and (wins_team or wins_opp):
        status = SeriesStatus.ACTIVE

    return Series(
        league=league,
        season="2026/2027",
        stage=stage_name,
        team_a=team_name,
        team_b=opponent,
        wins_a=wins_team,
        wins_b=wins_opp,
        status=status,
        source_url=next((g.source_url for g in series_games if g.source_url), None),
        game_ids=[g.source_game_id for g in series_games],
    )


def build_snapshot(team_key: str, team_name: str, league: str, table: dict, games, now: datetime) -> PlayoffSnapshot:
    title = str(table.get("title") or "Регулярный сезон")
    kind = _kind_from_title(title)
    summary = str(table.get("status_text") or "")
    source = table.get("source")

    if kind == StageKind.REGULAR:
        qualification, position = _qualification_from_table(table, team_name)
        stage_name = title
        if not summary:
            summary = "Регулярный этап · положение относительно зоны плей-офф пока определяется по таблице"
        return PlayoffSnapshot(
            team_key, team_name, league, kind, stage_name, summary, source, None,
            qualification, position,
        )

    series = _series_from_games(team_name, league, title, games, now)
    if series:
        summary = f"{title} · серия с {series.team_b} {series.score_text}"
    elif not summary:
        summary = f"{title} · серия ещё не определена"
    return PlayoffSnapshot(
        team_key, team_name, league, kind, title, summary, source, series,
        QualificationState.POSTSEASON, None,
    )
