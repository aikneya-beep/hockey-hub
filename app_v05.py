from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock, Thread
import hashlib
import html
import re
import time
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse, Response

MOSCOW = ZoneInfo("Europe/Moscow")
app = FastAPI(title="Мой хоккей", version="0.5.0")


@dataclass
class Game:
    source: str
    source_game_id: str
    league: str
    home_team: str
    away_team: str
    start_at: datetime
    status: str = "scheduled"
    home_score: int | None = None
    away_score: int | None = None
    decision: str | None = None
    arena: str | None = None
    source_url: str | None = None


@dataclass(frozen=True)
class Team:
    key: str
    name: str
    league: str
    source: str
    url: str


TEAMS = [
    Team("ska", "СКА", "КХЛ", "khl", "https://khl.api.webcaster.pro/api/khl_mobile"),
    Team("ska_vmf", "СКА-ВМФ", "ВХЛ", "ska_html", "https://vmf.ska.ru/championship/games/"),
    Team("ska_1946", "СКА-1946", "МХЛ", "ska_html", "https://1946.ska.ru/championship/games/"),
    Team("academy", "Академия СКА", "МХЛ", "ska_html", "https://junior.ska.ru/championship/games/"),
    Team("eskulap", "Эскулап", "СПбХЛ", "spbhl", "https://spbhl.ru/Schedule?TeamID=ea948f99-4b9a-4275-8105-157aa9c95559"),
]

GAMES: dict[tuple[str, str], Game] = {}
RUNS: dict[str, dict] = {}
LOCK = Lock()
REFRESH_LOCK = Lock()

# Небольшой резервный снимок ближайших матчей Эскулапа.
for number, d, t, home, away, hs, a_s in [
    ("24", "02.09.2026", "21:30", "Эскулап", "СБС", 4, 2),
    ("25", "09.09.2026", "21:30", "Эскулап", "Снежный", 2, 3),
    ("30", "16.09.2026", "21:30", "Эскулап", "Космос-В", None, None),
]:
    dt = datetime.strptime(f"{d} {t}", "%d.%m.%Y %H:%M").replace(tzinfo=MOSCOW)
    g = Game(
        "spbhl",
        f"spbhl-{number}",
        "СПбХЛ",
        home,
        away,
        dt,
        "finished" if hs is not None else "scheduled",
        hs,
        a_s,
        source_url=TEAMS[-1].url,
    )
    GAMES[(g.source, g.source_game_id)] = g


def compact(value: str) -> str:
    return " ".join(str(value).replace("\xa0", " ").split())


def make_id(*parts: str) -> str:
    raw = "|".join(compact(x) for x in parts)
    return hashlib.sha1(raw.encode()).hexdigest()[:20]


def unwrap_list(payload, candidates=("data", "events", "teams", "items")):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in candidates:
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                for nested in candidates:
                    if isinstance(value.get(nested), list):
                        return value[nested]
    raise ValueError("не найден список объектов в JSON")


def team_name(obj) -> str:
    if not isinstance(obj, dict):
        return "?"
    for key in ("name", "title", "short_name", "full_name"):
        value = obj.get(key)
        if value:
            if isinstance(value, dict):
                value = value.get("ru") or next(iter(value.values()), "")
            return compact(value)
    return "?"


def parse_score(value) -> tuple[int | None, int | None]:
    match = re.search(r"(\d+)\s*:\s*(\d+)", str(value or ""))
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def fetch_khl(base: str, league: str, wanted_name: str) -> list[Game]:
    params = {"locale": "ru", "application": "khl_web"}
    headers = {
        "User-Agent": "KHL/4.11.2 (iPhone; HockeyHub)",
        "Accept-Language": "ru-RU,ru;q=0.9",
    }

    response = requests.get(f"{base}/teams_v2.json", params=params, headers=headers, timeout=25)
    response.raise_for_status()
    raw_teams = unwrap_list(response.json(), ("data", "teams", "items"))
    teams = [x.get("team", x) if isinstance(x, dict) else x for x in raw_teams]
    wanted = next((x for x in teams if team_name(x).casefold() == wanted_name.casefold()), None)
    if wanted is None:
        wanted = next((x for x in teams if wanted_name.casefold() in team_name(x).casefold()), None)
    if wanted is None or wanted.get("id") is None:
        raise ValueError(f"команда {wanted_name} не найдена в KHL API")

    now = datetime.now(MOSCOW)
    query = {
        **params,
        "q[start_at_gt_time_from_unixtime]": int((now - timedelta(days=60)).timestamp()),
        "q[start_at_lt_time_from_unixtime]": int((now + timedelta(days=260)).timestamp()),
        "q[team_a_or_team_b_in][]": str(wanted["id"]),
        "order_direction": "asc",
    }
    response = requests.get(f"{base}/events_v2.json", params=query, headers=headers, timeout=25)
    response.raise_for_status()
    raw_events = unwrap_list(response.json(), ("data", "events", "items"))
    events = [x.get("event", x) if isinstance(x, dict) else x for x in raw_events]

    games: list[Game] = []
    for event in events:
        if not isinstance(event, dict) or event.get("type_id") not in (None, 24):
            continue
        event_id = event.get("id") or event.get("khl_id")
        raw_time = event.get("start_at") or event.get("event_start_at")
        if event_id is None or raw_time is None:
            continue
        if isinstance(raw_time, str) and raw_time.isdigit():
            raw_time = int(raw_time)
        if isinstance(raw_time, (int, float)):
            ts = raw_time / 1000 if raw_time > 10_000_000_000 else raw_time
            start_at = datetime.fromtimestamp(ts, MOSCOW)
        else:
            start_at = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
            start_at = start_at.replace(tzinfo=MOSCOW) if start_at.tzinfo is None else start_at.astimezone(MOSCOW)

        home_score, away_score = parse_score(event.get("score"))
        state = str(event.get("game_state_key") or "").lower()
        status = "finished" if state == "finished" else "live" if state == "in_progress" else "scheduled"
        scores = event.get("scores") or {}
        decision = "SO" if isinstance(scores, dict) and scores.get("bullitt") else "OT" if isinstance(scores, dict) and scores.get("overtime") else None
        khl_id = event.get("khl_id")
        source_url = f"https://www.khl.ru/game-center/{khl_id}/" if khl_id else None
        games.append(
            Game(
                "khl_api",
                str(event_id),
                league,
                team_name(event.get("team_a") or {}),
                team_name(event.get("team_b") or {}),
                start_at,
                status,
                home_score,
                away_score,
                decision,
                compact(event.get("location") or "") or None,
                source_url,
            )
        )
    if not games:
        raise ValueError(f"KHL API не вернул матчи {wanted_name}")
    return games


def fetch_ska_site(url: str, wanted_name: str, league: str) -> list[Game]:
    response = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0 HockeyHub"})
    response.raise_for_status()
    tokens = [compact(x) for x in BeautifulSoup(response.text, "html.parser").stripped_strings if compact(x)]
    weekday = {"Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"}
    date_re = re.compile(r"^\d{2}\.\d{2}(?:\.\d{4})?$")
    time_re = re.compile(r"^\d{1,2}:\d{2}$")
    season_text = next((x for x in tokens if re.fullmatch(r"20\d{2}/20\d{2}", x)), None)
    season_start = int(season_text[:4]) if season_text else datetime.now(MOSCOW).year

    games: list[Game] = []
    i = 0
    while i < len(tokens) - 7:
        if not date_re.match(tokens[i]) or tokens[i + 1] not in weekday or not time_re.match(tokens[i + 2]):
            i += 1
            continue
        date_text, time_text = tokens[i], tokens[i + 2]
        home, s1, colon, s2 = tokens[i + 3 : i + 7]
        if colon != ":" or not (s1.isdigit() or s1 == "-") or not (s2.isdigit() or s2 == "-"):
            i += 1
            continue
        j = i + 7
        decision = None
        if j < len(tokens) and tokens[j] in {"Буллиты", "Овертайм", "ОТ"}:
            decision = "SO" if tokens[j] == "Буллиты" else "OT"
            j += 1
        if j >= len(tokens):
            break
        away = tokens[j]
        if wanted_name not in (home, away):
            i += 1
            continue

        if len(date_text) == 5:
            month = int(date_text[3:5])
            year = season_start if month >= 7 else season_start + 1
            full_date = f"{date_text}.{year}"
        else:
            full_date = date_text
        start_at = datetime.strptime(f"{full_date} {time_text}", "%d.%m.%Y %H:%M").replace(tzinfo=MOSCOW)
        finished = s1.isdigit() and s2.isdigit()
        games.append(
            Game(
                f"{league.lower()}_ska_site",
                make_id(full_date, time_text, home, away),
                league,
                home,
                away,
                start_at,
                "finished" if finished else "scheduled",
                int(s1) if s1.isdigit() else None,
                int(s2) if s2.isdigit() else None,
                decision,
                source_url=url,
            )
        )
        i = j + 1

    if not games:
        raise ValueError(f"не удалось распознать матчи {wanted_name}")
    return games


def fetch_spbhl(url: str) -> list[Game]:
    response = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0 HockeyHub"})
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    games: list[Game] = []
    for row in soup.find_all("tr"):
        row_text = compact(row.get_text(" ", strip=True))
        if "Эскулап" not in row_text:
            continue
        date_match = re.search(r"\d{2}\.\d{2}\.\d{4}", row_text)
        time_match = re.search(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b", row_text)
        if not date_match or not time_match:
            continue

        match_link = next(
            (a for a in row.find_all("a", href=True) if "Эскулап" in compact(a.get_text(" ", strip=True))),
            None,
        )
        teams_text = compact(match_link.get_text(" ", strip=True)) if match_link else ""
        parts = re.split(r"\s+-\s+", teams_text, maxsplit=1)
        if len(parts) != 2:
            continue
        home, away = parts

        cells = row.find_all("td")
        result_text = compact(cells[-1].get_text(" ", strip=True)) if cells else ""
        score_match = re.search(r"(\d+)\s*:\s*(\d+)\s*([А-ЯA-Z]*)", result_text)
        home_score = int(score_match.group(1)) if score_match else None
        away_score = int(score_match.group(2)) if score_match else None
        suffix = score_match.group(3).upper() if score_match else ""
        decision = "SO" if suffix in {"ПБ", "Б", "SO"} else "OT" if suffix in {"ОТ", "OT"} else None

        number = compact(cells[2].get_text(" ", strip=True)) if len(cells) >= 3 else ""
        arena = compact(cells[5].get_text(" ", strip=True)) if len(cells) >= 6 else None
        date_text = date_match.group(0)
        time_text = time_match.group(0)
        start_at = datetime.strptime(f"{date_text} {time_text}", "%d.%m.%Y %H:%M").replace(tzinfo=MOSCOW)
        game_url = requests.compat.urljoin(url, match_link["href"]) if match_link else url
        game_id = number or make_id(date_text, time_text, home, away)
        games.append(
            Game(
                "spbhl",
                f"spbhl-{game_id}",
                "СПбХЛ",
                home,
                away,
                start_at,
                "finished" if score_match else "scheduled",
                home_score,
                away_score,
                decision,
                arena or None,
                game_url,
            )
        )

    if not games:
        raise ValueError("не удалось распознать матчи Эскулапа")
    return games


def fetch_team(team: Team) -> list[Game]:
    if team.source == "khl":
        return fetch_khl(team.url, team.league, team.name)
    if team.source == "ska_html":
        return fetch_ska_site(team.url, team.name, team.league)
    return fetch_spbhl(team.url)


def refresh_all() -> None:
    if not REFRESH_LOCK.acquire(blocking=False):
        return
    try:
        for team in TEAMS:
            try:
                games = fetch_team(team)
                with LOCK:
                    for game in games:
                        GAMES[(game.source, game.source_game_id)] = game
                    RUNS[team.key] = {"ok": True, "rows": len(games), "at": datetime.now(MOSCOW), "error": None}
                print(f"[refresh] {team.name}: OK {len(games)}", flush=True)
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"[:300]
                with LOCK:
                    RUNS[team.key] = {"ok": False, "rows": 0, "at": datetime.now(MOSCOW), "error": message}
                print(f"[refresh] {team.name}: ERROR {message}", flush=True)
    finally:
        REFRESH_LOCK.release()


def refresh_loop() -> None:
    refresh_all()
    while True:
        time.sleep(1800)
        refresh_all()


@app.on_event("startup")
def startup() -> None:
    Thread(target=refresh_loop, daemon=True).start()


def render_page() -> str:
    now = datetime.now(MOSCOW)
    today = now.date()
    with LOCK:
        games = list(GAMES.values())
        runs = dict(RUNS)

    games = [g for g in games if now - timedelta(days=7) <= g.start_at <= now + timedelta(days=120)]
    by_date: dict = {}
    for game in games:
        by_date.setdefault(game.start_at.date(), []).append(game)
    for day_games in by_date.values():
        day_games.sort(key=lambda x: x.start_at)

    pills = []
    for team in TEAMS:
        run = runs.get(team.key)
        if not run:
            state = '<span class="muted">обновление…</span>'
        elif run["ok"]:
            state = f'<span class="good">✓ {run["rows"]}</span>'
        else:
            state = f'<span class="bad" title="{html.escape(run["error"] or "")}">ошибка</span>'
        pills.append(f'<div class="pill"><b>{team.name}</b> {state}</div>')

    future_dates = sorted(day for day in by_date if day >= today)
    recent_dates = sorted((day for day in by_date if day < today), reverse=True)
    sections = []
    for day in future_dates + recent_dates:
        label = "Сегодня" if day == today else "Завтра" if day == today + timedelta(days=1) else day.strftime("%d.%m.%Y")
        cards = []
        for game in by_date[day]:
            home_score = str(game.home_score) if game.home_score is not None else "—"
            away_score = str(game.away_score) if game.away_score is not None else "—"
            details = ("по буллитам · " if game.decision == "SO" else "овертайм · " if game.decision == "OT" else "") + (game.arena or "")
            link = f'<a href="{html.escape(game.source_url)}" target="_blank" rel="noopener">источник ↗</a>' if game.source_url else ""
            cards.append(
                f'''<article class="game {game.status}">
                <div class="meta"><span>{game.league}</span><time>{game.start_at.strftime('%H:%M')}</time></div>
                <div class="team"><span>{html.escape(game.home_team)}</span><strong>{home_score}</strong></div>
                <div class="team"><span>{html.escape(game.away_team)}</span><strong>{away_score}</strong></div>
                <div class="foot">{html.escape(details)}{link}</div></article>'''
            )
        sections.append(f'<section class="day"><h2>{label}</h2>{"".join(cards)}</section>')

    if not sections:
        sections.append('<section class="empty">Пока нет матчей в выбранном окне.</section>')

    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Мой хоккей</title><link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#0b0d11"><meta name="apple-mobile-web-app-capable" content="yes"><style>
:root{{color-scheme:dark;font-family:Inter,system-ui,-apple-system,sans-serif}}*{{box-sizing:border-box}}body{{margin:0;background:#0b0d11;color:#f5f7fa}}.wrap{{max-width:780px;margin:auto;padding:28px 18px 80px}}.hero{{display:flex;justify-content:space-between;gap:18px;align-items:flex-end;border-bottom:1px solid #262b35;padding-bottom:24px}}.eyebrow{{font-size:12px;letter-spacing:.13em;color:#8993a4}}h1{{font-size:42px;margin:7px 0 3px;line-height:1}}p{{margin:0;color:#a8b0bd}}button{{border:0;border-radius:10px;padding:11px 14px;background:#f0f3f7;color:#11151b;font-weight:700;cursor:pointer}}.sources{{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0 30px}}.pill{{background:#151922;border:1px solid #252b36;border-radius:999px;padding:8px 11px;font-size:12px}}.pill b{{margin-right:6px}}.good{{color:#8bd49c}}.bad{{color:#ff8f8f}}.muted{{color:#818a99}}.day{{margin-top:28px}}.day h2{{font-size:15px;color:#a7afbc;text-transform:uppercase;letter-spacing:.06em}}.game{{background:#12161d;border:1px solid #252a33;border-radius:16px;padding:14px 16px;margin:9px 0}}.game.live{{border-color:#f5f7fa}}.meta{{display:flex;justify-content:space-between;color:#8892a2;font-size:12px;margin-bottom:10px}}.team{{display:flex;justify-content:space-between;font-size:18px;padding:3px 0}}.team strong{{font-variant-numeric:tabular-nums}}.foot{{margin-top:10px;color:#768091;font-size:12px;min-height:16px}}.foot a{{float:right;color:#aeb8c8;text-decoration:none}}.empty{{color:#8993a4;padding:30px 0}}@media(max-width:560px){{.hero{{align-items:flex-start;flex-direction:column}}.hero form,.hero button{{width:100%}}h1{{font-size:36px}}}}
</style></head><body><main class="wrap"><header class="hero"><div><div class="eyebrow">ХОККЕЙНЫЙ АГРЕГАТОР · v0.5</div><h1>Мой хоккей</h1><p>СКА · СКА-ВМФ · СКА-1946 · Академия СКА · Эскулап</p></div><form method="post" action="/refresh"><button>Обновить данные</button></form></header><section class="sources">{"".join(pills)}</section>{"".join(sections)}</main><script>if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js');</script></body></html>'''


@app.get("/", response_class=HTMLResponse)
def home():
    return render_page()


@app.post("/refresh")
def refresh():
    Thread(target=refresh_all, daemon=True).start()
    return RedirectResponse("/", status_code=303)


@app.get("/health")
def health():
    return {"status": "ok", "games": len(GAMES)}


@app.get("/debug")
def debug():
    with LOCK:
        return {
            "runs": {key: {**value, "at": value["at"].isoformat()} for key, value in RUNS.items()},
            "games": len(GAMES),
        }


@app.get("/manifest.webmanifest")
def manifest():
    return Response(
        '{"name":"Мой хоккей","short_name":"Хоккей","start_url":"/","display":"standalone","background_color":"#0b0d11","theme_color":"#0b0d11","lang":"ru"}',
        media_type="application/manifest+json",
    )


@app.get("/sw.js")
def sw():
    return Response("self.addEventListener('fetch',()=>{});", media_type="application/javascript", headers={"Service-Worker-Allowed": "/"})
