from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from hockey_domain import QualificationState, StageKind


@dataclass(frozen=True)
class SeasonPlan:
    team_key: str
    league: str
    regular_end: date | None = None
    play_in_start: date | None = None
    play_in_end: date | None = None
    playoff_start: date | None = None
    playoff_end: date | None = None


@dataclass(frozen=True)
class StageDecision:
    kind: StageKind
    name: str
    summary_hint: str | None = None
    series_since: datetime | None = None
    wins_needed: int | None = None
    source: str = "source"


PLANS = {
    "ska": SeasonPlan(
        "ska", "КХЛ",
        regular_end=date(2027, 3, 20),
        playoff_start=date(2027, 3, 23),
        playoff_end=date(2027, 5, 23),
    ),
    "ska_vmf": SeasonPlan(
        "ska_vmf", "ВХЛ",
        regular_end=date(2027, 3, 18),
        playoff_start=date(2027, 3, 22),
        playoff_end=date(2027, 5, 30),
    ),
    "ska_1946": SeasonPlan(
        "ska_1946", "МХЛ",
        regular_end=date(2027, 3, 22),
        play_in_start=date(2027, 3, 25),
        play_in_end=date(2027, 3, 30),
        playoff_start=date(2027, 4, 2),
        playoff_end=date(2027, 5, 24),
    ),
    "academy": SeasonPlan(
        "academy", "МХЛ",
        regular_end=date(2027, 3, 22),
        play_in_start=date(2027, 3, 25),
        play_in_end=date(2027, 3, 30),
        playoff_start=date(2027, 4, 2),
        playoff_end=date(2027, 5, 24),
    ),
}


def _norm(value: str) -> str:
    return " ".join(str(value or "").casefold().replace("ё", "е").split())


def _source_kind(table: dict) -> StageKind | None:
    explicit = _norm(table.get("postseason_stage") or "")
    if explicit in {"play_in", "play-in", "play in", "плей-ин"}:
        return StageKind.PLAY_IN
    if explicit in {"playoff", "play-off", "плей-офф"}:
        return StageKind.PLAYOFF

    text = _norm(" ".join(str(table.get(k) or "") for k in ("title", "note", "status_text")))
    if any(x in text for x in ("плей-ин", "play-in", "play in")):
        return StageKind.PLAY_IN
    if any(x in text for x in ("плей-офф", "playoff", "кубок гагарина", "кубок харламова", "кубок чемпиона")):
        return StageKind.PLAYOFF
    return None


def _at_start(day: date, now: datetime) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=now.tzinfo)


def _has_games_since(team_name: str, games, start: date) -> bool:
    for game in games:
        if team_name not in (game.home_team, game.away_team):
            continue
        if game.start_at.date() >= start:
            return True
    return False


def _official_postseason_games(team_name: str, games, now: datetime):
    return [
        g for g in games
        if team_name in (g.home_team, g.away_team)
        and getattr(g, "stage_hint", None) in {"playoff", "play_in"}
        and g.start_at <= now + timedelta(days=35)
    ]


def calendar_label(team_key: str) -> str:
    plan = PLANS.get(team_key)
    if not plan:
        return "СПбХЛ: этап определяется по текущему турниру"
    if plan.play_in_start:
        return (
            f"{plan.league}: регулярка до {plan.regular_end:%d.%m.%Y} · "
            f"плей-ин {plan.play_in_start:%d.%m}–{plan.play_in_end:%d.%m} · "
            f"плей-офф с {plan.playoff_start:%d.%m.%Y}"
        )
    return (
        f"{plan.league}: регулярка до {plan.regular_end:%d.%m.%Y} · "
        f"плей-офф {plan.playoff_start:%d.%m}–{plan.playoff_end:%d.%m.%Y}"
    )


def detect_stage(
    team_key: str,
    team_name: str,
    table: dict,
    games,
    now: datetime,
    qualification: QualificationState,
) -> StageDecision:
    """Return the current competition stage for one tracked team.

    Strong source signals always win. Calendar rules are a fallback for league
    pages that keep showing the final regular-season table after postseason
    starts. This avoids treating repeated regular-season opponents as a series.
    """
    title = str(table.get("title") or "Регулярный сезон")
    source_kind = _source_kind(table)
    if source_kind == StageKind.PLAY_IN:
        return StageDecision(
            StageKind.PLAY_IN,
            title,
            series_since=now - timedelta(days=35),
            wins_needed=2 if team_key in {"ska_1946", "academy"} else None,
            source="table",
        )
    if source_kind == StageKind.PLAYOFF:
        wins_needed = 4 if team_key in {"ska", "ska_vmf"} else None
        return StageDecision(
            StageKind.PLAYOFF,
            title,
            series_since=now - timedelta(days=35),
            wins_needed=wins_needed,
            source="table",
        )

    plan = PLANS.get(team_key)

    # Official KHL events carry a non-regular marker. Once the regular season is
    # over, that is stronger evidence than a standings page that may still show
    # the final regular table.
    official_games = _official_postseason_games(team_name, games, now)
    if official_games and (not plan or not plan.regular_end or now.date() > plan.regular_end):
        first = min(g.start_at for g in official_games)
        kind = StageKind.PLAY_IN if any(getattr(g, "stage_hint", None) == "play_in" for g in official_games) else StageKind.PLAYOFF
        return StageDecision(
            kind,
            f"{'Плей-ин' if kind == StageKind.PLAY_IN else 'Плей-офф'} {league_name(team_key)}",
            series_since=first - timedelta(hours=1),
            wins_needed=4 if team_key in {"ska", "ska_vmf"} else 2 if kind == StageKind.PLAY_IN else None,
            source="events",
        )

    # SPbHL has no fixed common season calendar. Its tournament title is the
    # authoritative signal; absence of postseason words means a regular stage.
    if not plan:
        return StageDecision(StageKind.REGULAR, title, source="tournament")

    today = now.date()
    if plan.regular_end and today <= plan.regular_end:
        return StageDecision(StageKind.REGULAR, title, source="calendar")

    # MHL play-in is a separate stage. Direct qualifiers wait for the round of
    # 16, while teams outside both zones are done for the season.
    if plan.play_in_start and plan.play_in_end and plan.play_in_start <= today <= plan.play_in_end:
        if qualification == QualificationState.PLAY_IN:
            return StageDecision(
                StageKind.PLAY_IN,
                "Плей-ин МХЛ",
                "Команда играет за выход в 1/8 финала",
                _at_start(plan.play_in_start, now),
                2,
                "calendar",
            )
        if qualification == QualificationState.DIRECT:
            return StageDecision(
                StageKind.OTHER,
                "Ожидание плей-офф",
                "Прямой выход в 1/8 финала · ожидание старта плей-офф",
                source="calendar",
            )
        if qualification == QualificationState.OUTSIDE:
            return StageDecision(
                StageKind.OTHER,
                "Сезон завершён",
                "Команда не попала в постсезон",
                source="calendar",
            )

    # Gap between the regular season/play-in and the first playoff games.
    if plan.playoff_start and today < plan.playoff_start:
        if qualification == QualificationState.DIRECT:
            return StageDecision(
                StageKind.OTHER,
                "Ожидание плей-офф",
                f"Команда квалифицировалась · плей-офф начнётся {plan.playoff_start:%d.%m.%Y}",
                source="calendar",
            )
        if qualification == QualificationState.PLAY_IN and plan.play_in_start and today < plan.play_in_start:
            return StageDecision(
                StageKind.OTHER,
                "Ожидание плей-ин",
                f"Команда в зоне плей-ин · старт {plan.play_in_start:%d.%m.%Y}",
                source="calendar",
            )
        if qualification == QualificationState.OUTSIDE:
            return StageDecision(
                StageKind.OTHER,
                "Сезон завершён",
                "Команда не попала в постсезон",
                source="calendar",
            )
        return StageDecision(StageKind.OTHER, "Между этапами", source="calendar")

    if plan.playoff_start and plan.playoff_end and plan.playoff_start <= today <= plan.playoff_end:
        # KHL/VHL direct qualification is enough. For an MHL team that entered
        # through play-in, require an actual playoff game in the feed before we
        # claim it advanced.
        advanced = qualification == QualificationState.DIRECT
        if qualification == QualificationState.PLAY_IN:
            advanced = _has_games_since(team_name, games, plan.playoff_start)
        if advanced:
            return StageDecision(
                StageKind.PLAYOFF,
                f"Плей-офф {plan.league}",
                series_since=_at_start(plan.playoff_start, now),
                wins_needed=4 if team_key in {"ska", "ska_vmf"} else None,
                source="calendar",
            )
        return StageDecision(
            StageKind.OTHER,
            "Постсезон",
            "Участие команды в текущем раунде не подтверждено матчами источника",
            source="calendar",
        )

    if plan.playoff_end and today > plan.playoff_end:
        return StageDecision(StageKind.OTHER, "Сезон завершён", source="calendar")

    return StageDecision(StageKind.REGULAR, title, source="calendar")


def league_name(team_key: str) -> str:
    plan = PLANS.get(team_key)
    return plan.league if plan else ""
