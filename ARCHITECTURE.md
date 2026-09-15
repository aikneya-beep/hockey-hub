# Hockey Hub architecture

## Current production path (v0.33)

The UI remains backed by the existing in-process cache so the refactor does not risk the stable match/standings experience.

New code is organized around explicit domain concepts:

- `hockey_domain.py` — season, stage, playoff series, venue, match identity.
- `playoff_monitor.py` — league-agnostic playoff/series state built from normalized games + stage data.
- `schema.sql` — target normalized relational model for durable storage.
- `/api/v1/games` — normalized game feed for future UI/assistant clients.
- `/api/v1/playoffs` — normalized playoff state for future UI/assistant clients.

## Persistence migration

Target tables:

`leagues -> teams -> seasons -> stages -> games -> playoff_series`

`arenas` is a separate entity referenced by games. `playoff_series_games` links games into a series.

Migration is intentionally staged:

1. Keep current collectors and UI stable.
2. Mirror collector output to PostgreSQL.
3. Verify counts/scores/arenas against the in-memory cache.
4. Switch reads to PostgreSQL.
5. Only after that add user-owned data (training, notes, watchlists, assistant memory).

This avoids putting personal data into the current ephemeral in-process cache.

## Playoff model

Regular standings are a qualification view, not the playoff itself. When a source switches to play-in/playoff, the app represents the competition as:

`Season -> Stage (regular/play_in/playoff) -> Series -> Games`

The team page can then replace the standings-first layout with the active series once a postseason stage becomes active.
