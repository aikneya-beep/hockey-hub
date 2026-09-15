from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import Counter

from hockey_domain import QualificationState, Series, SeriesStatus, StageKind
from postseason_adapters import detect_stage


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


def _series_from_games(
    team_name: str,
    league: str,
    stage_name: str,
    games,
    now: datetime,
    series_since: datetime | None = None,
    wins_needed: int | None = None,
) -> Series | None:
    # The stage adapter has already established that this is postseason. Keep
    # the series window inside the actual stage so late regular-season rematches
    # can never be mistaken for playoff games.
    lower_bound = now - timedelta(days=35)
    if series_since and series_since > lower_bound:
        lower_bound = series_since
    recent = [
        g for g in games
        if team_name in (g.home_team, g.away_team)
        and lower_bound <= g.start_at <= now + timedelta(days=35)
    ]
    if not recent:
        return None

    opponents = [g.away_team if g.home_team == team_name else g.home_team for g in recent]
    opponent, _count = Counter(opponents).most_common(1)[0]
    series_games = sorted(
        [g for g in recent if opponent in (g.home_team, g.away_team)],
        key=lambda g: g.start_at,
    )

    wins_team = 0
    wins_opp = 0
    finished_count = 0
    for g in series_games:
        if g.status != "finished" or g.home_score is None or g.away_score is None:
            continue
        finished_count += 1
        winner = g.home_team if g.home_score > g.away_score else g.away_team
        if winner == team_name:
            wins_team += 1
        elif winner == opponent:
            wins_opp += 1

    if wins_needed and max(wins_team, wins_opp) >= wins_needed:
        status = SeriesStatus.FINISHED
    elif finished_count:
        status = SeriesStatus.ACTIVE
    else:
        status = SeriesStatus.UPCOMING

    return Series(
        league=league,
        season="2026/2027",
        stage=stage_name,
        team_a=team_name,
        team_b=opponent,
        wins_a=wins_team,
        wins_b=wins_opp,
        wins_needed=wins_needed,
        status=status,
        source_url=next((g.source_url for g in series_games if g.source_url), None),
        game_ids=[g.source_game_id for g in series_games],
    )


def build_snapshot(team_key: str, team_name: str, league: str, table: dict, games, now: datetime) -> PlayoffSnapshot:
    title = str(table.get("title") or "Регулярный сезон")
    qualification, position = _qualification_from_table(table, team_name)
    decision = detect_stage(team_key, team_name, table, games, now, qualification)
    summary = str(table.get("status_text") or "")
    source = table.get("source")

    if decision.kind == StageKind.REGULAR:
        if not summary:
            summary = "Регулярный этап · положение относительно зоны плей-офф пока определяется по таблице"
        return PlayoffSnapshot(
            team_key, team_name, league, decision.kind, decision.name or title,
            summary, source, None, qualification, position,
        )

    if decision.kind == StageKind.OTHER:
        summary = decision.summary_hint or summary or decision.name
        return PlayoffSnapshot(
            team_key, team_name, league, decision.kind, decision.name,
            summary, source, None, qualification, position,
        )

    series = _series_from_games(
        team_name,
        league,
        decision.name,
        games,
        now,
        series_since=decision.series_since,
        wins_needed=decision.wins_needed,
    )
    if series:
        suffix = f" · серия с {series.team_b} {series.score_text}"
        if series.wins_needed:
            suffix += f" (до {series.wins_needed} побед)"
        summary = f"{decision.name}{suffix}"
    else:
        summary = decision.summary_hint or f"{decision.name} · соперник/серия ещё не определены"

    return PlayoffSnapshot(
        team_key, team_name, league, decision.kind, decision.name, summary, source, series,
        QualificationState.POSTSEASON, None,
    )
