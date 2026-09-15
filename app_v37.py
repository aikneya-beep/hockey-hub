from __future__ import annotations

from datetime import datetime
import html

import app_v36 as prev
import app_v33 as playoff_ui
import app_v19 as feature
import app_v05 as core
from hockey_domain import StageKind
from playoff_monitor import build_snapshot

core.app.version = "0.37.0"


def _series_games(snapshot, games):
    if not snapshot.series:
        return []
    ids = set(snapshot.series.game_ids)
    return sorted(
        [g for g in games if g.source_game_id in ids],
        key=lambda g: g.start_at,
    )


def _series_block(team_key: str) -> str:
    meta = feature.TEAM_META.get(team_key)
    if not meta:
        return ""
    name = meta["name"]
    now = datetime.now(core.MOSCOW)
    with core.LOCK:
        games = [g for g in core.GAMES.values() if name in (g.home_team, g.away_team)]

    try:
        table = feature._fetch_standings(team_key)
        snap = build_snapshot(team_key, name, meta["league"], table, games, now)
    except Exception as exc:
        print(f"[postseason-card] {team_key}: {type(exc).__name__}: {exc}", flush=True)
        return ""

    if snap.stage_kind not in {StageKind.PLAY_IN, StageKind.PLAYOFF}:
        return ""

    phase = "Плей-ин" if snap.stage_kind == StageKind.PLAY_IN else "Плей-офф"
    series = snap.series
    if series is None:
        return f'''<section class="postseason-wrap">
          <div class="postseason-kicker">{html.escape(phase)} · ТЕКУЩИЙ ЭТАП</div>
          <div class="postseason-card waiting">
            <div><h2>{html.escape(snap.stage_name)}</h2><p>{html.escape(snap.summary)}</p></div>
            <div class="postseason-wait">Серия ещё не определена</div>
          </div>
        </section>'''

    sgames = _series_games(snap, games)
    completed = [g for g in sgames if g.status == "finished"]
    future = [g for g in sgames if g.status != "finished" and g.start_at >= now]
    next_game = future[0] if future else None

    need = f"до {series.wins_needed} побед" if series.wins_needed else "формат серии — по данным лиги"
    status = {
        "upcoming": "Серия ещё не началась",
        "active": "Серия идёт",
        "finished": "Серия завершена",
    }.get(str(series.status), str(series.status))

    next_html = '<div class="series-next empty">Следующий матч пока не опубликован</div>'
    if next_game:
        arena = f" · 📍 {html.escape(core.compact(next_game.arena or ''))}" if core.compact(next_game.arena or "") else ""
        next_html = (
            '<div class="series-next"><span>Следующий матч</span>'
            f'<b>{next_game.start_at.strftime("%d.%m · %H:%M")}</b>'
            f'<small>{html.escape(next_game.home_team)} — {html.escape(next_game.away_team)}{arena}</small></div>'
        )

    played_html = ""
    if completed:
        chips = []
        for g in completed:
            score = f"{g.home_score}:{g.away_score}" if g.home_score is not None and g.away_score is not None else "—"
            chips.append(
                f'<div class="series-game"><span>{g.start_at.strftime("%d.%m")}</span>'
                f'<b>{html.escape(g.home_team)} <em class="series-game-score">{score}</em> {html.escape(g.away_team)}</b></div>'
            )
        played_html = f'<div class="series-history"><span>Матчи серии</span>{"".join(chips)}</div>'

    source = (
        f'<a class="series-source" href="{html.escape(series.source_url)}" target="_blank" rel="noopener">источник ↗</a>'
        if series.source_url else ""
    )
    return f'''<section class="postseason-wrap">
      <div class="postseason-kicker">{html.escape(phase)} · ТЕКУЩАЯ СЕРИЯ</div>
      <div class="postseason-card" onclick="if(document.documentElement.classList.contains('spoiler-mode'))this.classList.add('revealed')">
        <div class="series-main">
          <div class="series-meta"><span>{html.escape(status)}</span><small>{html.escape(need)}</small></div>
          <div class="series-pair"><b>{html.escape(series.team_a)}</b><strong class="series-score">{series.wins_a}:{series.wins_b}</strong><b>{html.escape(series.team_b)}</b></div>
          <button type="button" class="series-reveal" onclick="this.closest('.postseason-card').classList.add('revealed');event.stopPropagation()">показать счёт серии</button>
        </div>
        {next_html}
        {played_html}
        <div class="series-foot"><span>{html.escape(snap.stage_name)}</span>{source}</div>
      </div>
    </section>'''


SERIES_CSS = '''
<style id="v37-postseason-style">
.postseason-wrap{margin:24px 0 4px}.postseason-kicker{font-size:11px;color:#8993a4;letter-spacing:.11em;margin-bottom:9px}.postseason-card{background:#12161d;border:1px solid #334157;border-radius:16px;padding:16px;box-shadow:inset 3px 0 0 #7c91c4}.postseason-card.waiting{display:flex;justify-content:space-between;gap:18px;align-items:center}.postseason-card.waiting h2{margin:0 0 5px;color:#f5f7fa;font-size:19px;text-transform:none;letter-spacing:0}.postseason-card.waiting p{margin:0;color:#9ca6b5;font-size:13px}.postseason-wait{color:#b9c9ee;font-size:12px;font-weight:750;white-space:nowrap}.series-main{display:grid;gap:10px}.series-meta{display:flex;justify-content:space-between;gap:12px;color:#92a0b2;font-size:11px;text-transform:uppercase;letter-spacing:.045em}.series-meta small{font-size:10px;color:#727e90}.series-pair{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);align-items:center;gap:14px;font-size:19px}.series-pair b:last-child{text-align:right}.series-score{font-size:30px;font-variant-numeric:tabular-nums;letter-spacing:.02em}.series-reveal{display:none;background:#1b222d;color:#c3ccda;border:1px solid #334052;border-radius:8px;padding:7px 9px;font-size:11px;cursor:pointer}.spoiler-mode .postseason-card:not(.revealed) .series-score,.spoiler-mode .postseason-card:not(.revealed) .series-game-score{display:none}.spoiler-mode .postseason-card:not(.revealed) .series-reveal{display:block;justify-self:center}.series-next{display:grid;grid-template-columns:1fr auto;gap:3px 14px;margin-top:14px;padding:11px 12px;background:#171c24;border-radius:10px}.series-next span{font-size:10px;color:#7f8999;text-transform:uppercase;letter-spacing:.05em}.series-next b{font-size:13px}.series-next small{grid-column:1/-1;color:#adb6c4;font-size:11px}.series-next.empty{display:block;color:#788495;font-size:11px}.series-history{display:grid;gap:5px;margin-top:13px}.series-history>span{font-size:10px;color:#737f90;text-transform:uppercase;letter-spacing:.05em;margin-bottom:2px}.series-game{display:flex;justify-content:space-between;gap:12px;padding:7px 0;border-bottom:1px solid #222935;font-size:11px}.series-game:last-child{border-bottom:0}.series-game span{color:#778394}.series-game b{font-weight:650}.series-game em{font-style:normal;font-weight:850;margin:0 4px}.series-foot{display:flex;justify-content:space-between;gap:12px;margin-top:13px;padding-top:10px;border-top:1px solid #252d3a;color:#737f90;font-size:10px}.series-source{text-decoration:none}.postseason-wrap+h2{margin-top:24px}@media(max-width:600px){.postseason-card.waiting{display:block}.postseason-wait{margin-top:12px}.series-pair{font-size:16px;gap:8px}.series-score{font-size:25px}.series-meta{display:grid}.series-meta small{margin-top:2px}.series-next{grid-template-columns:1fr}.series-next small{grid-column:auto}.series-game{display:grid;gap:3px}.series-game b{font-size:10px}.series-foot{flex-direction:column}}
</style>'''


_old_team_page = feature.render_team_page


def render_team_page_v37(team_key: str) -> str:
    page = _old_team_page(team_key).replace("v0.36", "v0.37")
    block = _series_block(team_key)
    if not block:
        return page
    page = page.replace("</head>", SERIES_CSS + "</head>", 1)
    # The first h2 is the standings title. Putting the current series before it
    # makes postseason pages series-first without rewriting the stable team UI.
    page = page.replace("<h2>", block + "<h2>", 1)
    return page


feature.render_team_page = render_team_page_v37

_old_home = core.render_page


def render_page_v37() -> str:
    return _old_home().replace("v0.36", "v0.37", 1)


core.render_page = render_page_v37

_old_playoffs = playoff_ui.render_playoffs_page


def render_playoffs_page_v37() -> str:
    return _old_playoffs().replace("v0.36", "v0.37")


playoff_ui.render_playoffs_page = render_playoffs_page_v37

app = core.app
