-- Hockey Hub persistence foundation.
-- The live app still reads from the existing in-memory cache in v0.33;
-- this schema is the migration target before user-owned data is added.

create table if not exists leagues (
    id bigserial primary key,
    code text not null unique,
    name text not null
);

create table if not exists teams (
    id bigserial primary key,
    key text unique,
    name text not null,
    league_code text not null,
    source text,
    source_team_id text,
    unique (league_code, name)
);

create table if not exists seasons (
    id bigserial primary key,
    league_code text not null,
    name text not null,
    starts_on date,
    ends_on date,
    unique (league_code, name)
);

create table if not exists stages (
    id bigserial primary key,
    season_id bigint not null references seasons(id) on delete cascade,
    name text not null,
    kind text not null check (kind in ('regular','play_in','playoff','other')),
    source_url text,
    starts_on date,
    ends_on date,
    unique (season_id, name)
);

create table if not exists arenas (
    id bigserial primary key,
    name text not null,
    city text,
    source text,
    unique (name, city)
);

create table if not exists games (
    id bigserial primary key,
    source text not null,
    source_game_id text not null,
    league_code text not null,
    season_id bigint references seasons(id),
    stage_id bigint references stages(id),
    home_team text not null,
    away_team text not null,
    start_at timestamptz not null,
    status text not null,
    home_score integer,
    away_score integer,
    decision text,
    arena_id bigint references arenas(id),
    arena_text text,
    source_url text,
    updated_at timestamptz not null default now(),
    unique (source, source_game_id)
);

create index if not exists games_start_at_idx on games(start_at);
create index if not exists games_home_team_idx on games(home_team);
create index if not exists games_away_team_idx on games(away_team);

create table if not exists playoff_series (
    id bigserial primary key,
    stage_id bigint references stages(id),
    league_code text not null,
    team_a text not null,
    team_b text not null,
    wins_a integer not null default 0,
    wins_b integer not null default 0,
    wins_needed integer,
    status text not null check (status in ('upcoming','active','finished')),
    source_url text,
    unique (stage_id, team_a, team_b)
);

create table if not exists playoff_series_games (
    series_id bigint not null references playoff_series(id) on delete cascade,
    game_id bigint not null references games(id) on delete cascade,
    primary key (series_id, game_id)
);
