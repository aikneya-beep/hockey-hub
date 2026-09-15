from __future__ import annotations

from threading import Thread
import time

import app_v18 as stable
import app_v19 as prev
import app_v05 as core


# Keep v0.19's automatic KHL history attempt, but never regress the verified
# current-season results that were already working in v0.18.
def fetch_khl_v20(api_base: str, league: str, wanted_name: str) -> list[core.Game]:
    games = prev.fetch_khl_v19(api_base, league, wanted_name)
    if wanted_name != "СКА":
        return games

    by_match = {
        (g.start_at.date(), g.home_team.casefold(), g.away_team.casefold()): g
        for g in games
    }
    added = 0
    for seed in stable._seeded_ska_results():
        key = (seed.start_at.date(), seed.home_team.casefold(), seed.away_team.casefold())
        current = by_match.get(key)
        if current is None or current.status != "finished" or current.home_score is None or current.away_score is None:
            games.append(seed)
            by_match[key] = seed
            added += 1

    games.sort(key=lambda g: g.start_at)
    finished = [g for g in games if g.status == "finished"]
    print(
        f"[verify] SKA v20 fallback_added={added} finished={len(finished)}: "
        + "; ".join(
            f"{g.start_at:%d.%m} {g.home_team} {g.home_score}:{g.away_score} {g.away_team}"
            for g in finished[-10:]
        ),
        flush=True,
    )
    return games


core.fetch_khl = fetch_khl_v20
core.app.version = "0.20.0"


# The /team/{team_key} route registered by app_v19 resolves this module global
# at request time, so replacing it here also updates the visible team-page label.
_render_team_v19 = prev.render_team_page


def render_team_page_v20(team_key: str) -> str:
    return _render_team_v19(team_key).replace("v0.19", "v0.20")


prev.render_team_page = render_team_page_v20


def render_page_v20() -> str:
    return prev.render_page_v19().replace("v0.19", "v0.20", 1)


core.render_page = render_page_v20


def _verify_standings() -> None:
    # Wait for the web process and the regular game refresh to get going first.
    time.sleep(7)
    for key, meta in prev.TEAM_META.items():
        try:
            # Ignore cache from any accidental earlier request so startup logs tell
            # us whether the actual source works on Render.
            prev.STANDINGS_CACHE.pop(key, None)
            data = prev._fetch_standings(key)
            rows = len(data.get("rows") or [])
            error = data.get("error")
            print(
                f"[verify] standings {key} ({meta['name']}): rows={rows} error={error!r}",
                flush=True,
            )
        except Exception as exc:
            print(
                f"[verify] standings {key} ({meta['name']}): ERROR {type(exc).__name__}: {exc}",
                flush=True,
            )


@core.app.on_event("startup")
def verify_standings_on_startup() -> None:
    Thread(target=_verify_standings, daemon=True).start()


app = core.app
