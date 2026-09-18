from __future__ import annotations

import app_v512  # load current production stack first
import app_v05 as core
import home_v44


def _event_card_v513(game, today) -> str:
    day, clock = home_v44._when(game, today)
    league = home_v44._tracked_label(game)
    status_class = "live" if game.status == "live" else ("personal" if "Эскулап" in (game.home_team, game.away_team) else "big")
    score = home_v44._score(game)
    arena = f'<div class="event-arena">{home_v44._esc(game.arena)}</div>' if game.arena else ""
    source = f'<a class="event-link" href="{home_v44._esc(game.source_url)}" target="_blank" rel="noopener">источник ↗</a>' if game.source_url else ""
    live = '<span class="event-live">LIVE</span>' if game.status == "live" else ""
    return f'''<article class="event-card {status_class}">
      <div class="event-top"><span class="event-day">{day}</span><span class="event-tag"><span class="event-league">{league}</span>{live}</span></div>
      <div class="event-time">{clock}</div>
      <div class="event-match"><b>{home_v44._esc(game.home_team)}</b><span>—</span><b>{home_v44._esc(game.away_team)}</b></div>
      <div class="event-score score-value">{score}</div>
      {arena}{source}
    </article>'''


home_v44._event_card = _event_card_v513

_previous_home = core.render_page


def render_home_v513() -> str:
    page = _previous_home()
    css = r"""
/* v0.51.3: league context is persistent; LIVE is an additional state. */
.event-card.live .event-tag{color:#adb8c7}
.event-live{margin-left:7px;color:#ff6078;font-weight:750;letter-spacing:.08em}
"""
    page = page.replace("</style>", css + "\n</style>", 1)
    return page.replace("v0.51", "v0.51.3", 1)


core.render_page = render_home_v513
core.app.version = "0.51.3"

app = core.app
