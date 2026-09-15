from __future__ import annotations

from dataclasses import asdict, dataclass
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
app = FastAPI(title="Мой хоккей", version="0.3.0")

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

# Небольшой стартовый снимок Эскулапа, чтобы первый экран не был пустым до сети.
for number, d, t, home, away, hs, a_s in [
    ("24", "02.09.2026", "21:30", "Эскулап", "СБС", 4, 2),
    ("25", "09.09.2026", "21:30", "Эскулап", "Снежный", 2, 3),
    ("30", "16.09.2026", "21:30", "Эскулап", "Космос-В", None, None),
]:
    dt = datetime.strptime(f"{d} {t}", "%d.%m.%Y %H:%M").replace(tzinfo=MOSCOW)
    g = Game("spbhl", f"spbhl-{number}", "СПбХЛ", home, away, dt,
             "finished" if hs is not None else "scheduled", hs, a_s,
             source_url=TEAMS[-1].url)
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


def score(event: dict, side: str):
    for key in (f"team_{side}_score", f"score_{side}", f"{side}_score"):
        v = event.get(key)
        if v is not None and str(v).isdigit():
            return int(v)
    team = event.get(f"team_{side}") or {}
    if isinstance(team, dict):
        for key in ("score", "goals"):
            v = team.get(key)
            if v is not None and str(v).isdigit():
                return int(v)
    return None


def fetch_khl(base: str, league: str, wanted_name: str) -> list[Game]:
    params = {"locale": "ru", "application": "khl_web"}
    headers = {"User-Agent": "KHL/4.11.2 (HockeyHub; Python)"}
    r = requests.get(f"{base}/teams_v2.json", params=params, headers=headers, timeout=25)
    r.raise_for_status()
    teams = unwrap_list(r.json(), ("data", "teams", "items"))
    wanted = next((t for t in teams if team_name(t).casefold() == wanted_name.casefold()), None)
    if wanted is None:
        wanted = next((t for t in teams if wanted_name.casefold() in team_name(t).casefold()), None)
    if wanted is None:
        raise ValueError(f"команда {wanted_name} не найдена")
    team_id = wanted.get("id")
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
    events = unwrap_list(r.json(), ("data", "events", "items"))
    out = []
    for e in events:
        event_id = e.get("id") or e.get("khl_id")
        if event_id is None:
            continue
        a = e.get("team_a") or e.get("home_team") or {}
        b = e.get("team_b") or e.get("away_team") or {}
        raw = e.get("start_at") or e.get("start_time") or e.get("date")
        if isinstance(raw, (int, float)):
            dt = datetime.fromtimestamp(raw, MOSCOW)
        elif isinstance(raw, str):
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            dt = (dt.replace(tzinfo=MOSCOW) if dt.tzinfo is None else dt.astimezone(MOSCOW))
        else:
            continue
        hs, av = score(e, "a"), score(e, "b")
        state = str(e.get("state") or e.get("status") or "").lower()
        if any(s in state for s in ("finish", "ended", "completed", "final")):
            status = "finished"
        elif "live" in state:
            status = "live"
        elif hs is not None and av is not None and dt < now:
            status = "finished"
        else:
            status = "scheduled"
        out.append(Game(f"{league.lower()}_api", str(event_id), league, team_name(a), team_name(b), dt,
                        status, hs, av, arena=compact(str(e.get("arena_name") or e.get("arena") or "")) or None))
    return out


def fetch_ska_vmf(url: str) -> list[Game]:
    r = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0 HockeyHub"})
    r.raise_for_status()
    tokens = [compact(x) for x in BeautifulSoup(r.text, "html.parser").stripped_strings if compact(x)]
    weekday = {"Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"}
    date_re = re.compile(r"^\d{2}\.\d{2}(?:\.\d{4})?$")
    time_re = re.compile(r"^\d{1,2}:\d{2}$")
    season_text = next((x for x in tokens if re.fullmatch(r"20\d{2}/20\d{2}", x)), None)
    season_start = int(season_text[:4]) if season_text else datetime.now(MOSCOW).year
    out = []
    i = 0
    while i < len(tokens) - 7:
        if not date_re.match(tokens[i]) or tokens[i+1] not in weekday or not time_re.match(tokens[i+2]):
            i += 1; continue
        date_text, time_text = tokens[i], tokens[i+2]
        home, s1, colon, s2 = tokens[i+3:i+7]
        if colon != ":" or not (s1.isdigit() or s1 == "-") or not (s2.isdigit() or s2 == "-"):
            i += 1; continue
        j = i + 7
        decision = None
        if j < len(tokens) and tokens[j] in {"Буллиты", "Овертайм", "ОТ"}:
            decision = "SO" if tokens[j] == "Буллиты" else "OT"; j += 1
        if j >= len(tokens): break
        away = tokens[j]
        if "СКА-ВМФ" not in (home, away):
            i += 1; continue
        month = int(date_text[3:5]); year = season_start if month >= 7 else season_start + 1
        dt = datetime.strptime(f"{date_text}.{year} {time_text}", "%d.%m.%Y %H:%M").replace(tzinfo=MOSCOW) if len(date_text)==5 else datetime.strptime(f"{date_text} {time_text}", "%d.%m.%Y %H:%M").replace(tzinfo=MOSCOW)
        finished = s1.isdigit() and s2.isdigit()
        out.append(Game("vhl_ska_site", make_id(date_text,time_text,home,away), "ВХЛ", home, away, dt,
                        "finished" if finished else "scheduled", int(s1) if s1.isdigit() else None,
                        int(s2) if s2.isdigit() else None, decision, source_url=url))
        i = j + 1
    if not out: raise ValueError("не удалось распознать матчи СКА-ВМФ")
    return out


def fetch_spbhl(url: str) -> list[Game]:
    r = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0 HockeyHub"})
    r.raise_for_status(); r.encoding = r.apparent_encoding or r.encoding
    soup = BeautifulSoup(r.text, "html.parser")
    table = None
    for t in soup.find_all("table"):
        h = " | ".join(compact(x.get_text(" ", strip=True)) for x in t.find_all("th"))
        if all(x in h for x in ("Дата", "Время", "Команды", "Результат")):
            table = t; break
    if table is None: raise ValueError("таблица СПбХЛ не найдена")
    out = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td"); cells = [compact(x.get_text(" ", strip=True)) for x in tds]
        if len(cells) < 8: continue
        tournament, _, number, date_text, time_text, arena, teams_text, result = cells[:8]
        if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", date_text) or " - " not in teams_text: continue
        home, away = [compact(x) for x in teams_text.split(" - ", 1)]
        dt = datetime.strptime(f"{date_text} {time_text}", "%d.%m.%Y %H:%M").replace(tzinfo=MOSCOW)
        m = re.search(r"(\d+)\s*:\s*(\d+)\s*([А-ЯA-Z]*)", result)
        hs = int(m.group(1)) if m else None; av = int(m.group(2)) if m else None
        decision = None
        if m and m.group(3).upper() in {"ПБ", "Б", "SO"}: decision = "SO"
        elif m and m.group(3).upper() in {"ОТ", "OT"}: decision = "OT"
        link = None
        if len(tds) > 6 and (a := tds[6].find("a", href=True)):
            link = requests.compat.urljoin(url, a["href"])
        out.append(Game("spbhl", f"spbhl-{number or make_id(date_text,time_text,home,away)}", "СПбХЛ", home, away, dt,
                        "finished" if m else "scheduled", hs, av, decision, arena or None, link or url))
    if not out: raise ValueError("не удалось распознать матчи Эскулапа")
    return out


def fetch_team(team: Team):
    if team.source == "khl": return fetch_khl(team.url, team.league, team.name)
    if team.source == "ska_html": return fetch_ska_vmf(team.url)
    return fetch_spbhl(team.url)


def refresh_all():
    if not REFRESH_LOCK.acquire(blocking=False): return
    try:
        for team in TEAMS:
            try:
                games = fetch_team(team)
                with LOCK:
                    for g in games: GAMES[(g.source, g.source_game_id)] = g
                    RUNS[team.key] = {"ok": True, "rows": len(games), "at": datetime.now(MOSCOW), "error": None}
            except Exception as exc:
                with LOCK:
                    RUNS[team.key] = {"ok": False, "rows": 0, "at": datetime.now(MOSCOW), "error": str(exc)[:220]}
    finally:
        REFRESH_LOCK.release()


def refresh_loop():
    refresh_all()
    while True:
        time.sleep(1800)
        refresh_all()

@app.on_event("startup")
def startup():
    Thread(target=refresh_loop, daemon=True).start()


def render_page() -> str:
    now = datetime.now(MOSCOW)
    with LOCK:
        games = sorted(GAMES.values(), key=lambda x: x.start_at)
        runs = dict(RUNS)
    # Показываем разумное окно вокруг сегодняшнего дня.
    games = [g for g in games if now - timedelta(days=45) <= g.start_at <= now + timedelta(days=180)]
    by_date: dict = {}
    for g in games: by_date.setdefault(g.start_at.date(), []).append(g)
    source_pills = []
    for team in TEAMS:
        r = runs.get(team.key)
        if not r: state = '<span class="muted">обновление…</span>'
        elif r["ok"]: state = f'<span class="good">✓ {r["rows"]}</span>'
        else: state = f'<span class="bad" title="{html.escape(r["error"] or "")}">ошибка</span>'
        source_pills.append(f'<div class="pill"><b>{team.name}</b> {state}</div>')
    sections = []
    for d, day_games in sorted(by_date.items()):
        label = "Сегодня" if d == now.date() else d.strftime("%d.%m.%Y")
        cards = []
        for g in day_games:
            hs = str(g.home_score) if g.home_score is not None else "—"
            av = str(g.away_score) if g.away_score is not None else "—"
            extra = ("по буллитам · " if g.decision == "SO" else "овертайм · " if g.decision == "OT" else "") + (g.arena or "")
            link = f'<a href="{html.escape(g.source_url)}" target="_blank">источник ↗</a>' if g.source_url else ""
            cards.append(f'''<article class="game {g.status}"><div class="meta"><span>{g.league}</span><time>{g.start_at.strftime('%H:%M')}</time></div><div class="team"><span>{html.escape(g.home_team)}</span><strong>{hs}</strong></div><div class="team"><span>{html.escape(g.away_team)}</span><strong>{av}</strong></div><div class="foot">{html.escape(extra)}{link}</div></article>''')
        sections.append(f'<section class="day"><h2>{label}</h2>{"".join(cards)}</section>')
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Мой хоккей</title><link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#0b0d11"><meta name="apple-mobile-web-app-capable" content="yes"><style>
:root{{color-scheme:dark;font-family:Inter,system-ui,-apple-system,sans-serif}}*{{box-sizing:border-box}}body{{margin:0;background:#0b0d11;color:#f5f7fa}}.wrap{{max-width:780px;margin:auto;padding:28px 18px 80px}}.hero{{display:flex;justify-content:space-between;gap:18px;align-items:flex-end;border-bottom:1px solid #262b35;padding-bottom:24px}}.eyebrow{{font-size:12px;letter-spacing:.13em;color:#8993a4}}h1{{font-size:42px;margin:7px 0 3px;line-height:1}}p{{margin:0;color:#a8b0bd}}button{{border:0;border-radius:10px;padding:11px 14px;background:#f0f3f7;color:#11151b;font-weight:700;cursor:pointer}}.sources{{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0 30px}}.pill{{background:#151922;border:1px solid #252b36;border-radius:999px;padding:8px 11px;font-size:12px}}.pill b{{margin-right:6px}}.good{{color:#8bd49c}}.bad{{color:#ff8f8f}}.muted{{color:#818a99}}.day{{margin-top:28px}}.day h2{{font-size:15px;color:#a7afbc;text-transform:uppercase;letter-spacing:.06em}}.game{{background:#12161d;border:1px solid #252a33;border-radius:16px;padding:14px 16px;margin:9px 0}}.game.live{{border-color:#f5f7fa}}.meta{{display:flex;justify-content:space-between;color:#8892a2;font-size:12px;margin-bottom:10px}}.team{{display:flex;justify-content:space-between;font-size:18px;padding:3px 0}}.team strong{{font-variant-numeric:tabular-nums}}.foot{{margin-top:10px;color:#768091;font-size:12px;min-height:16px}}.foot a{{float:right;color:#aeb8c8;text-decoration:none}}@media(max-width:560px){{.hero{{align-items:flex-start;flex-direction:column}}.hero form,.hero button{{width:100%}}h1{{font-size:36px}}}}
</style></head><body><main class="wrap"><header class="hero"><div><div class="eyebrow">ХОККЕЙНЫЙ АГРЕГАТОР · v0.3</div><h1>Мой хоккей</h1><p>СКА · СКА-ВМФ · СКА-1946 · Академия СКА · Эскулап</p></div><form method="post" action="/refresh"><button>Обновить данные</button></form></header><section class="sources">{"".join(source_pills)}</section>{"".join(sections)}</main><script>if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js');</script></body></html>'''

@app.get("/", response_class=HTMLResponse)
def home(): return render_page()

@app.post("/refresh")
def refresh():
    Thread(target=refresh_all, daemon=True).start()
    return RedirectResponse("/", status_code=303)

@app.get("/health")
def health(): return {"status": "ok", "games": len(GAMES)}

@app.get("/debug")
def debug():
    with LOCK:
        return {"runs": {k: {**v, "at": v["at"].isoformat()} for k,v in RUNS.items()}, "games": len(GAMES)}

@app.get("/manifest.webmanifest")
def manifest():
    return Response('{"name":"Мой хоккей","short_name":"Хоккей","start_url":"/","display":"standalone","background_color":"#0b0d11","theme_color":"#0b0d11","lang":"ru"}', media_type="application/manifest+json")

@app.get("/sw.js")
def sw():
    return Response("self.addEventListener('fetch',()=>{});", media_type="application/javascript", headers={"Service-Worker-Allowed":"/"})
