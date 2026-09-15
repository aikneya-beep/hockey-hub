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
app = FastAPI(title="Мой хоккей", version="0.4.0")


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
    Team("ska_1946", "СКА-1946", "МХЛ", "khl", "https://khl.api.webcaster.pro/api/mhl_mobile"),
    Team("academy", "Академия СКА", "МХЛ", "khl", "https://khl.api.webcaster.pro/api/mhl_mobile"),
    Team("eskulap", "Эскулап", "СПбХЛ", "spbhl", "https://spbhl.ru/Schedule?TeamID=ea948f99-4b9a-4275-8105-157aa9c95559"),
]

GAMES: dict[tuple[str, str], Game] = {}
RUNS: dict[str, dict] = {}
LOCK = Lock()
REFRESH_LOCK = Lock()

# Стартовый снимок Эскулапа: полезен, если СПбХЛ временно недоступна.
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


def compact(x: str) -> str:
    return " ".join(x.replace("\xa0", " ").split())


def make_id(*parts: str) -> str:
    raw = "|".join(compact(str(x)) for x in parts)
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
    for k in ("name", "title", "short_name", "full_name"):
        value = obj.get(k)
        if value:
            if isinstance(value, dict):
                value = value.get("ru") or next(iter(value.values()), "")
            return compact(str(value))
    return "?"


def parse_score_string(value) -> tuple[int | None, int | None]:
    if value is None:
        return None, None
    m = re.search(r"(\d+)\s*:\s*(\d+)", str(value))
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def fetch_khl(base: str, league: str, wanted_name: str) -> list[Game]:
    """KHL/MHL mobile API.

    List endpoints return wrappers like {"team": {...}} and {"event": {...}}.
    Event start_at is milliseconds, while filter query timestamps are seconds.
    """
    params = {"locale": "ru", "application": "khl_web"}
    headers = {
        "User-Agent": "KHL/4.11.2 (iPhone; iOS 16.3; Scale/2.00)",
        "Accept-Language": "ru-RU,ru;q=0.9",
    }

    r = requests.get(f"{base}/teams_v2.json", params=params, headers=headers, timeout=25)
    r.raise_for_status()
    raw_teams = unwrap_list(r.json(), ("data", "teams", "items"))
    teams = [x.get("team", x) if isinstance(x, dict) else x for x in raw_teams]

    wanted = next((t for t in teams if team_name(t).casefold() == wanted_name.casefold()), None)
    if wanted is None:
        wanted = next((t for t in teams if wanted_name.casefold() in team_name(t).casefold()), None)
    if wanted is None:
        names = ", ".join(team_name(t) for t in teams[:8])
        raise ValueError(f"команда {wanted_name} не найдена; примеры ответа: {names}")

    team_id = wanted.get("id")
    if team_id is None:
        raise ValueError(f"у команды {wanted_name} нет id")

    now = datetime.now(MOSCOW)
    query = {
        **params,
        "q[start_at_gt_time_from_unixtime]": int((now - timedelta(days=60)).timestamp()),
        "q[start_at_lt_time_from_unixtime]": int((now + timedelta(days=260)).timestamp()),
        "q[team_a_or_team_b_in][]": str(team_id),
        "order_direction": "asc",
    }
    r = requests.get(f"{base}/events_v2.json", params=query, headers=headers, timeout=25)
    r.raise_for_status()
    raw_events = unwrap_list(r.json(), ("data", "events", "items"))
    events = [x.get("event", x) if isinstance(x, dict) else x for x in raw_events]

    out: list[Game] = []
    for e in events:
        if not isinstance(e, dict):
            continue
        if e.get("type_id") not in (None, 24):
            continue
        event_id = e.get("id") or e.get("khl_id")
        if event_id is None:
            continue

        a = e.get("team_a") or {}
        b = e.get("team_b") or {}
        raw = e.get("start_at") or e.get("event_start_at")
        if isinstance(raw, (int, float)):
            timestamp = raw / 1000 if raw > 10_000_000_000 else raw
            dt = datetime.fromtimestamp(timestamp, MOSCOW)
        elif isinstance(raw, str):
            if raw.isdigit():
                n = int(raw)
                dt = datetime.fromtimestamp(n / 1000 if n > 10_000_000_000 else n, MOSCOW)
            else:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                dt = dt.replace(tzinfo=MOSCOW) if dt.tzinfo is None else dt.astimezone(MOSCOW)
        else:
            continue

        hs, av = parse_score_string(e.get("score"))
        state = str(e.get("game_state_key") or e.get("state") or e.get("status") or "").lower()
        if state == "finished" or any(s in state for s in ("ended", "completed", "final")):
            status = "finished"
        elif state in {"in_progress", "live"} or "live" in state:
            status = "live"
        else:
            status = "scheduled"

        scores = e.get("scores") or {}
        decision = None
        if isinstance(scores, dict):
            if scores.get("bullitt"):
                decision = "SO"
            elif scores.get("overtime"):
                decision = "OT"

        khl_id = e.get("khl_id")
        host = "www.khl.ru" if league == "КХЛ" else "mhl.khl.ru"
        source_url = f"https://{host}/game-center/{khl_id}/" if khl_id else None
        arena = compact(str(e.get("location") or "")) or None
        out.append(
            Game(
                f"{league.lower()}_api",
                str(event_id),
                league,
                team_name(a),
                team_name(b),
                dt,
                status,
                hs,
                av,
                decision,
                arena,
                source_url,
            )
        )

    if not out:
        raise ValueError(f"API не вернул матчи {wanted_name}")
    return out


def fetch_ska_site(url: str, wanted_name: str, league: str) -> list[Game]:
    r = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0 HockeyHub"})
    r.raise_for_status()
    tokens = [compact(x) for x in BeautifulSoup(r.text, "html.parser").stripped_strings if compact(x)]
    weekday = {"Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"}
    date_re = re.compile(r"^\d{2}\.\d{2}(?:\.\d{4})?$")
    time_re = re.compile(r"^\d{1,2}:\d{2}$")
    season_text = next((x for x in tokens if re.fullmatch(r"20\d{2}/20\d{2}", x)), None)
    season_start = int(season_text[:4]) if season_text else datetime.now(MOSCOW).year
    out: list[Game] = []
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
        month = int(date_text[3:5])
        year = season_start if month >= 7 else season_start + 1
        if len(date_text) == 5:
            dt = datetime.strptime(f"{date_text}.{year} {time_text}", "%d.%m.%Y %H:%M").replace(tzinfo=MOSCOW)
        else:
            dt = datetime.strptime(f"{date_text} {time_text}", "%d.%m.%Y %H:%M").replace(tzinfo=MOSCOW)
        finished = s1.isdigit() and s2.isdigit()
        out.append(
            Game(
                f"{league.lower()}_ska_site",
                make_id(date_text, time_text, home, away),
                league,
                home,
                away,
                dt,
                "finished" if finished else "scheduled",
                int(s1) if s1.isdigit() else None,
                int(s2) if s2.isdigit() else None,
                decision,
                source_url=url,
            )
        )
        i = j + 1
    if not out:
        raise ValueError(f"не удалось распознать матчи {wanted_name}")
    return out


def fetch_spbhl(url: str) -> list[Game]:
    r = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0 HockeyHub"})
    r.raise_for_status()
    r.encoding = r.apparent_encoding or r.encoding
    soup = BeautifulSoup(r.text, "html.parser")
    table = None
    for t in soup.find_all("table"):
        h = " | ".join(compact(x.get_text(" ", strip=True)) for x in t.find_all("th"))
        if all(x in h for x in ("Дата", "Время", "Команды", "Результат")):
            table = t
            break
    if table is None:
        raise ValueError("таблица СПбХЛ не найдена")

    out: list[Game] = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        cells = [compact(x.get_text(" ", strip=True)) for x in tds]
        if len(cells) < 8:
            continue
        tournament, _, number, raw_date, time_text, arena, teams_text, result = cells[:8]
        date_match = re.search(r"\d{2}\.\d{2}\.\d{4}", raw_date)
        if not date_match or " - " not in teams_text or not re.fullmatch(r"\d{1,2}:\d{2}", time_text):
            continue
        date_text = date_match.group(0)
        home, away = [compact(x) for x in teams_text.split(" - ", 1)]
        dt = datetime.strptime(f"{date_text} {time_text}", "%d.%m.%Y %H:%M").replace(tzinfo=MOSCOW)
        m = re.search(r"(\d+)\s*:\s*(\d+)\s*([А-ЯA-Z]*)", result)
        hs = int(m.group(1)) if m else None
        av = int(m.group(2)) if m else None
        decision = None
        if m and m.group(3).upper() in {"ПБ", "Б", "SO"}:
            decision = "SO"
        elif m and m.group(3).upper() in {"ОТ", "OT"}:
            decision = "OT"
        link = None
        if len(tds) > 6 and (a := tds[6].find("a", href=True)):
            link = requests.compat.urljoin(url, a["href"])
        out.append(
            Game(
                "spbhl",
                f"spbhl-{number or make_id(date_text, time_text, home, away)}",
                "СПбХЛ",
                home,
                away,
                dt,
                "finished" if m else "scheduled",
                hs,
                av,
                decision,
                arena or None,
                link or url,
            )
        )
    if not out:
        raise ValueError("не удалось распознать матчи Эскулапа")
    return out


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
                    for g in games:
                        GAMES[(g.source, g.source_game_id)] = g
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
def startup():
    Thread(target=refresh_loop, daemon=True).start()


def render_page() -> str:
    now = datetime.now(MOSCOW)
    today = now.date()
    with LOCK:
        games = list(GAMES.values())
        runs = dict(RUNS)

    games = [g for g in games if now - timedelta(days=7) <= g.start_at <= now + timedelta(days=120)]
    by_date: dict = {}
    for g in games:
        by_date.setdefault(g.start_at.date(), []).append(g)
    for values in by_date.values():
        values.sort(key=lambda g: g.start_at)

    source_pills = []
    for team in TEAMS:
        r = runs.get(team.key)
        if not r:
            state = '<span class="muted">обновление…</span>'
        elif r["ok"]:
            state = f'<span class="good">✓ {r["rows"]}</span>'
        else:
            state = f'<span class="bad" title="{html.escape(r["error"] or "")}">ошибка</span>'
        source_pills.append(f'<div class="pill"><b>{team.name}</b> {state}</div>')

    future_dates = sorted(d for d in by_date if d >= today)
    past_dates = sorted((d for d in by_date if d < today), reverse=True)
    ordered_dates = future_dates + past_dates
    sections = []
    for d in ordered_dates:
        if d == today:
            label = "Сегодня"
        elif d == today + timedelta(days=1):
            label = "Завтра"
        else:
            label = d.strftime("%d.%m.%Y")
        cards = []
        for g in by_date[d]:
            hs = str(g.home_score) if g.home_score is not None else "—"
            av = str(g.away_score) if g.away_score is not None else "—"
            extra = (("по буллитам · " if g.decision == "SO" else "овертайм · " if g.decision == "OT" else "") + (g.arena or ""))
            link = f'<a href="{html.escape(g.source_url)}" target="_blank" rel="noopener">источник ↗</a>' if g.source_url else ""
            cards.append(f'''<article class="game {g.status}"><div class="meta"><span>{g.league}</span><time>{g.start_at.strftime('%H:%M')}</time></div><div class="team"><span>{html.escape(g.home_team)}</span><strong>{hs}</strong></div><div class="team"><span>{html.escape(g.away_team)}</span><strong>{av}</strong></div><div class="foot">{html.escape(extra)}{link}</div></article>''')
        sections.append(f'<section class="day"><h2>{label}</h2>{"".join(cards)}</section>')

    if not sections:
        sections.append('<section class="empty">Пока нет матчей в выбранном окне.</section>')

    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Мой хоккей</title><link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#0b0d11"><meta name="apple-mobile-web-app-capable" content="yes"><style>
:root{{color-scheme:dark;font-family:Inter,system-ui,-apple-system,sans-serif}}*{{box-sizing:border-box}}body{{margin:0;background:#0b0d11;color:#f5f7fa}}.wrap{{max-width:780px;margin:auto;padding:28px 18px 80px}}.hero{{display:flex;justify-content:space-between;gap:18px;align-items:flex-end;border-bottom:1px solid #262b35;padding-bottom:24px}}.eyebrow{{font-size:12px;letter-spacing:.13em;color:#8993a4}}h1{{font-size:42px;margin:7px 0 3px;line-height:1}}p{{margin:0;color:#a8b0bd}}button{{border:0;border-radius:10px;padding:11px 14px;background:#f0f3f7;color:#11151b;font-weight:700;cursor:pointer}}.sources{{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0 30px}}.pill{{background:#151922;border:1px solid #252b36;border-radius:999px;padding:8px 11px;font-size:12px}}.pill b{{margin-right:6px}}.good{{color:#8bd49c}}.bad{{color:#ff8f8f}}.muted{{color:#818a99}}.day{{margin-top:28px}}.day h2{{font-size:15px;color:#a7afbc;text-transform:uppercase;letter-spacing:.06em}}.game{{background:#12161d;border:1px solid #252a33;border-radius:16px;padding:14px 16px;margin:9px 0}}.game.live{{border-color:#f5f7fa}}.meta{{display:flex;justify-content:space-between;color:#8892a2;font-size:12px;margin-bottom:10px}}.team{{display:flex;justify-content:space-between;font-size:18px;padding:3px 0}}.team strong{{font-variant-numeric:tabular-nums}}.foot{{margin-top:10px;color:#768091;font-size:12px;min-height:16px}}.foot a{{float:right;color:#aeb8c8;text-decoration:none}}.empty{{color:#8993a4;padding:30px 0}}@media(max-width:560px){{.hero{{align-items:flex-start;flex-direction:column}}.hero form,.hero button{{width:100%}}h1{{font-size:36px}}}}
</style></head><body><main class="wrap"><header class="hero"><div><div class="eyebrow">ХОККЕЙНЫЙ АГРЕГАТОР · v0.4</div><h1>Мой хоккей</h1><p>СКА · СКА-ВМФ · СКА-1946 · Академия СКА · Эскулап</p></div><form method="post" action="/refresh"><button>Обновить данные</button></form></header><section class="sources">{"".join(source_pills)}</section>{"".join(sections)}</main><script>if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js');</script></body></html>'''


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
        return {"runs": {k: {**v, "at": v["at"].isoformat()} for k, v in RUNS.items()}, "games": len(GAMES)}


@app.get("/manifest.webmanifest")
def manifest():
    return Response('{"name":"Мой хоккей","short_name":"Хоккей","start_url":"/","display":"standalone","background_color":"#0b0d11","theme_color":"#0b0d11","lang":"ru"}', media_type="application/manifest+json")


@app.get("/sw.js")
def sw():
    return Response("self.addEventListener('fetch',()=>{});", media_type="application/javascript", headers={"Service-Worker-Allowed": "/"})
