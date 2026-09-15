# Hockey Hub architecture

## Current production path (v0.34)

The public UI still reads from the proven in-process cache so the refactor cannot silently break the stable match/standings experience.

Domain and service code is being split out of the historical `app_vXX.py` chain:

- `hockey_domain.py` — season, stage, playoff series, venue, match identity.
- `playoff_monitor.py` — league-agnostic playoff/series state built from normalized games + stage data.
- `persistence.py` — optional PostgreSQL mirror, enabled only by `DATABASE_URL`.
- `schema.sql` — normalized relational schema.
- `/api/v1/games` — normalized game feed for future UI/assistant clients.
- `/api/v1/playoffs` — normalized playoff state for future UI/assistant clients.
- `/api/v1/storage` — migration/connection status without exposing credentials.

## Persistence migration

Target model:

`leagues -> teams -> seasons -> stages -> games -> playoff_series`

`arenas` is a separate entity referenced by games. `playoff_series_games` links games into a series.

Migration is deliberately staged:

1. Keep current collectors and UI stable.
2. Mirror the exact collector output to PostgreSQL after every refresh.
3. Verify row counts, scores, timestamps and arenas against the in-memory cache.
4. Switch read APIs to PostgreSQL.
5. Switch the UI to those APIs.
6. Only after that add user-owned data (training, notes, watchlists, assistant memory).

v0.34 implements step 2 in code. If `DATABASE_URL` is absent the mirror is a no-op and the site works exactly as before. The Render PostgreSQL instance must be linked to the web service before persistence becomes active.

## Playoff model

Regular standings are a qualification view, not the playoff itself. Postseason data is represented as:

`Season -> Stage (regular/play_in/playoff) -> Series -> Games`

The `/playoffs` page is the first consumer of this model. During the regular season it shows qualification state. Once a source exposes a postseason stage, the monitor can attach games to a series and the team page can replace the standings-first layout with the active series.

League-specific source adapters should determine the actual postseason stage. The generic monitor must not infer a playoff series merely because two clubs play each other repeatedly during the regular season.

## Venue model

`Game.arena` remains the normalized UI field during migration. Collectors should prefer an explicit source venue; known home-arena defaults are only fallbacks when a source omits the venue. PostgreSQL stores both normalized `arena_id` and original `arena_text` so venue cleanup can happen later without losing source data.
