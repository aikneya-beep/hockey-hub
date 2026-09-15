from __future__ import annotations

from datetime import datetime, date, timedelta
import html

from fastapi.responses import HTMLResponse

import app_v32 as prev
import app_v28 as khl_results
import app_v22 as team_ui
import app_v08 as card_ui
import app_v19 as feature
import app_v05 as core
from hockey_domain import StageKind
from playoff_monitor import build_snapshot

core.app.version = "0.33.0"

# ---------------------------------------------------------------------------
# Venue enrichment
# ---------------------------------------------------------------------------
# Source data always wins. These are only season-level fallbacks for tracked
# teams' home games when their list page does not expose a venue.
DEFAULT_HOME_ARENAS = {
    "СКА": "СКА Арена",
    "СКА-ВМФ": "Ледовый дворец",
    "СКА-1946": "СК «Хоккейный Город»",
    "Академия СКА": "СК «Хоккейный Город»",
}


def _text_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return core.compact(value)
    if isinstance(value, dict):
        for key in ("name", "title", "short_name", "full_name", "address"):
            if value.get(key):
                raw = value[key]
                if isinstance(raw, dict):
                    raw = raw.get("ru") or next(iter(raw.values()), "")
                return core.compact(raw)
    return ""


def _arena_from_khl_event(event: dict) -> str:
    # Prefer a real arena/stadium field; `location` in some KHL payloads is only
    # a city, so it is deliberately the last fallback.
    for key in ("arena_name", "arena", "stadium_name", "stadium", "venue", "place"):
        value = _text_value(event.get(key))
        if value:
            return value
    return _text_value(event.get("location"))


_old_khl_game_from_event = khl_results._game_from_event


def _khl_game_from_event_v33(event: dict, league: str, now: datetime):
    game = _old_khl_game_from_event(event, league, now)
    if game is None:
        return None
    source_arena = _arena_from_khl_event(event)
    # If KHL only gives us the city for a tracked home match, the known home
    # arena is more useful than repeating the city.
    if game.home_team in DEFAULT_HOME_ARENAS and (not source_arena or source_arena in {"Санкт-Петербург", "СПб"}):
        game.arena = DEFAULT_HOME_ARENAS[game.home_team]
    elif source_arena:
        game.arena = source_arena
    return game


khl_results._game_from_event = _khl_game_from_event_v33


def _backfill_home_arenas() -> None:
    with core.LOCK:
        for game in core.GAMES.values():
            if not core.compact(game.arena or "") and game.home_team in DEFAULT_HOME_ARENAS:
                game.arena = DEFAULT_HOME_ARENAS[game.home_team]


_old_refresh_all = core.refresh_all


def refresh_all_v33() -> None:
    _old_refresh_all()
    _backfill_home_arenas()


core.refresh_all = refresh_all_v33
_backfill_home_arenas()

# Main-page cards already have a secondary line; make the venue explicit.
_old_secondary = card_ui._secondary_text


def _secondary_text_v33(game: core.Game) -> str:
    decision = "Б" if game.decision == "SO" else "ОТ" if game.decision == "OT" else ""
    arena = core.compact(game.arena or "")
    if arena:
        pair = f"{game.home_team} - {game.away_team}"
        if card_ui._normalize_label(arena) == card_ui._normalize_label(pair):
            arena = ""
    venue = f"📍 {arena}" if arena else ""
    return " · ".join(x for x in (decision, venue) if x)


card_ui._secondary_text = _secondary_text_v33

# Team-page cards did not previously display game.arena at all.
def _team_game_row_v33(g: core.Game, target: str, played: bool) -> str:
    score = "—"
    if played and g.home_score is not None and g.away_score is not None:
        score = f"{g.home_score}:{g.away_score}"
    decision = "Б" if g.decision == "SO" else "ОТ" if g.decision == "OT" else ""
    source = (
        f'<a class="src" href="{html.escape(g.source_url)}" target="_blank" rel="noopener" title="Источник">↗</a>'
        if g.source_url else ""
    )

    def tn(name: str) -> str:
        cls = " fav" if team_ui._norm(name) == team_ui._norm(target) else ""
        return f'<div class="team-name{cls}">{html.escape(name)}</div>'

    arena = core.compact(g.arena or "")
    venue_html = f'<div class="game-venue">📍 {html.escape(arena)}</div>' if arena else ""
    reveal = (
        '<button type="button" class="score-mask" onclick="revealTeamScore(this);event.stopPropagation()">показать<br>счёт</button>'
        if played else ""
    )
    return f'''<div class="tgame {'played' if played else ''}">
      <div class="tdate"><b>{g.start_at.strftime('%d.%m')}</b><span>{g.start_at.strftime('%H:%M')}</span></div>
      <div class="tpair">{tn(g.home_team)}{tn(g.away_team)}{venue_html}</div>
      <div class="tscore"><b class="score-sensitive">{score}</b>{reveal}<span>{html.escape(decision)} {source}</span></div>
    </div>'''


team_ui._team_game_row = _team_game_row_v33

# ---------------------------------------------------------------------------
# Playoff monitor
# ---------------------------------------------------------------------------
PLAYOFF_CALENDAR = {
    "ska": "КХЛ: плей-офф 23.03–23.05.2027",
    "ska_vmf": "ВХЛ: плей-офф 22.03–30.05.2027",
    "ska_1946": "МХЛ: прямой выход из топ-5 Золотого дивизиона; 6–8 — плей-ин",
    "academy": "МХЛ: топ-3 Серебряного дивизиона выходит в плей-ин",
    "eskulap": "СПбХЛ: этап определяется автоматически по текущему турниру",
}


def _snapshots():
    now = datetime.now(core.MOSCOW)
    with core.LOCK:
        games = list(core.GAMES.values())
    out = []
    for team in core.TEAMS:
        try:
            table = feature._fetch_standings(team.key)
            snap = build_snapshot(team.key, team.name, team.league, table, games, now)
            out.append((team, table, snap, None))
        except Exception as exc:
            out.append((team, {}, None, f"{type(exc).__name__}: {exc}"))
    return out


def _phase_label(kind: StageKind) -> str:
    return {
        StageKind.REGULAR: "Регулярный этап",
        StageKind.PLAY_IN: "Плей-ин",
        StageKind.PLAYOFF: "Плей-офф",
        StageKind.OTHER: "Другой этап",
    }.get(kind, str(kind))


def render_playoffs_page() -> str:
    cards = []
    for team, table, snap, error in _snapshots():
        if error or snap is None:
            cards.append(f'''<article class="p-card"><div class="p-head"><b>{html.escape(team.name)}</b><span>{html.escape(team.league)}</span></div>
            <div class="p-summary bad">Не удалось получить положение: {html.escape(error or 'ошибка')}</div></article>''')
            continue
        series_html = ""
        if snap.series:
            series_html = (
                f'<div class="series"><b>{html.escape(snap.series.team_a)} — {html.escape(snap.series.team_b)}</b>'
                f'<strong>{snap.series.wins_a}:{snap.series.wins_b}</strong></div>'
            )
        source = f'<a href="{html.escape(snap.source_url)}" target="_blank" rel="noopener">источник ↗</a>' if snap.source_url else ""
        cards.append(f'''<article class="p-card">
          <div class="p-head"><b>{html.escape(team.name)}</b><span>{html.escape(team.league)}</span></div>
          <div class="phase">{html.escape(_phase_label(snap.stage_kind))}</div>
          <div class="p-summary">{html.escape(snap.summary)}</div>
          {series_html}
          <div class="p-foot"><span>{html.escape(PLAYOFF_CALENDAR.get(team.key, ''))}</span>{source}</div>
        </article>''')

    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Плей-офф · Мой хоккей</title><meta name="theme-color" content="#0b0d11"><style>
:root{{color-scheme:dark;font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}*{{box-sizing:border-box}}body{{margin:0;background:#0b0d11;color:#f5f7fa}}a{{color:inherit}}.wrap{{max-width:920px;margin:auto;padding:26px 20px 80px}}.back{{color:#96a0b0;text-decoration:none;font-size:13px}}header{{border-bottom:1px solid #262b35;padding:18px 0 22px}}.eyebrow{{font-size:12px;letter-spacing:.13em;color:#8993a4}}h1{{font-size:40px;margin:7px 0 4px}}header p{{margin:0;color:#9aa4b3}}.grid{{display:grid;gap:10px;margin-top:26px}}.p-card{{background:#12161d;border:1px solid #252a33;border-radius:14px;padding:15px 16px}}.p-head{{display:flex;justify-content:space-between;gap:12px;align-items:baseline}}.p-head b{{font-size:18px}}.p-head span{{font-size:11px;color:#7f8999}}.phase{{display:inline-block;margin-top:11px;padding:5px 8px;border-radius:7px;background:#1b222d;color:#cbd3df;font-size:11px;font-weight:750;text-transform:uppercase;letter-spacing:.04em}}.p-summary{{margin-top:10px;color:#e2e6ec;font-size:14px}}.bad{{color:#ff9b9b}}.series{{display:flex;justify-content:space-between;align-items:center;margin-top:12px;padding:11px 12px;background:#171c24;border-radius:9px}}.series strong{{font-size:20px}}.p-foot{{display:flex;justify-content:space-between;gap:15px;margin-top:12px;color:#7e8898;font-size:11px}}.p-foot a{{text-decoration:none;white-space:nowrap}}@media(max-width:600px){{.wrap{{padding:20px 14px 60px}}h1{{font-size:34px}}.p-foot{{flex-direction:column;gap:5px}}}}
</style></head><body><main class="wrap"><a class="back" href="/">← Все матчи</a><header><div class="eyebrow">МОЙ ХОККЕЙ · v0.33</div><h1>Плей-офф</h1><p>Единый монитор квалификации, плей-ин и серий всех моих команд.</p></header><section class="grid">{''.join(cards)}</section></main></body></html>'''


@core.app.get("/playoffs", response_class=HTMLResponse)
def playoffs_page():
    return render_playoffs_page()


@core.app.get("/api/v1/games")
def api_games(team: str | None = None):
    with core.LOCK:
        games = list(core.GAMES.values())
    if team:
        needle = team.casefold()
        games = [g for g in games if needle in {g.home_team.casefold(), g.away_team.casefold()}]
    games.sort(key=lambda g: g.start_at)
    return [
        {
            "source": g.source,
            "id": g.source_game_id,
            "league": g.league,
            "home": g.home_team,
            "away": g.away_team,
            "start_at": g.start_at.isoformat(),
            "status": g.status,
            "home_score": g.home_score,
            "away_score": g.away_score,
            "decision": g.decision,
            "arena": g.arena,
            "source_url": g.source_url,
        }
        for g in games
    ]


@core.app.get("/api/v1/playoffs")
def api_playoffs():
    payload = []
    for team, table, snap, error in _snapshots():
        if snap is None:
            payload.append({"team": team.name, "league": team.league, "error": error})
            continue
        payload.append({
            "team": team.name,
            "league": team.league,
            "stage": snap.stage_name,
            "stage_kind": snap.stage_kind.value,
            "summary": snap.summary,
            "source_url": snap.source_url,
            "series": None if snap.series is None else {
                "opponent": snap.series.team_b,
                "score": snap.series.score_text,
                "status": snap.series.status.value,
            },
        })
    return payload

# ---------------------------------------------------------------------------
# Navigation + version skin
# ---------------------------------------------------------------------------
_old_team_page = feature.render_team_page


def render_team_page_v33(team_key: str) -> str:
    page = _old_team_page(team_key)
    page = page.replace("v0.32", "v0.33")
    page = page.replace(
        '<button type="button" id="spoilerToggle"',
        '<a class="playoffs-nav" href="/playoffs">Плей-офф</a><button type="button" id="spoilerToggle"',
        1,
    )
    css = '.game-venue{font-size:11px;color:#788393;margin-top:3px}.playoffs-nav{margin-left:auto;margin-right:10px;color:#aab4c3;text-decoration:none;font-size:12px}.topbar{flex-wrap:wrap}'
    page = page.replace("</style>", css + "</style>", 1)
    return page


feature.render_team_page = render_team_page_v33


def render_page_v33() -> str:
    page = prev.render_page_v32().replace("v0.32", "v0.33", 1)
    nav = '<a class="playoffs-main" href="/playoffs">Плей-офф</a>'
    page = page.replace('</nav>', nav + '</nav>', 1)
    css = '.playoffs-main{margin-left:auto;align-self:center;color:#9ba6b6;text-decoration:none;font-size:12px;padding:8px 10px;border:1px solid #2b3340;border-radius:9px}'
    page = page.replace("</style>", css + "</style>", 1)
    return page


core.render_page = render_page_v33
app = core.app
