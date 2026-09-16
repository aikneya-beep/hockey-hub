create table if not exists personal_hockey_meta (
    key text primary key,
    value text not null
);

create table if not exists personal_hockey_sessions (
    id bigserial primary key,
    session_date date not null,
    session_type text not null,
    focus text[] not null default '{}',
    wellbeing integer check (wellbeing between 1 and 10),
    load integer check (load between 1 and 10),
    note text,
    homework text,
    created_at timestamptz not null default now()
);

create index if not exists personal_hockey_sessions_date_idx
    on personal_hockey_sessions(session_date desc);

create table if not exists personal_hockey_coach_notes (
    id bigserial primary key,
    note_date date not null,
    text text not null,
    session_id bigint references personal_hockey_sessions(id) on delete set null,
    created_at timestamptz not null default now()
);

create table if not exists personal_hockey_tests (
    id bigserial primary key,
    test_date date not null,
    metric text not null,
    rink text,
    start_mode text,
    direction text,
    seconds numeric(7,3),
    session_id bigint references personal_hockey_sessions(id) on delete set null,
    created_at timestamptz not null default now()
);

create index if not exists personal_hockey_tests_date_idx
    on personal_hockey_tests(test_date desc);
