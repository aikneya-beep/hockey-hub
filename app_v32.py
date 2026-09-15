from __future__ import annotations

from datetime import datetime, timedelta
import html
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import app_v31 as prev
import app_v23 as stable
import app_v22 as team_ui
import app_v19 as feature
import app_v05 as core

core.app.version = "0.32.0"

# 2026/27 Western conference division composition from the official MHL structure.
MHL_WEST_GOLD = {
    "академия михайлова",
    "алмаз",
    "динамо-шинник",
    "красная армия",
    "локо",
    "мхк динамо м",
    "мхк динамо спб",
    "мхк спартак",
    "ска-1946",
}
MHL_WEST_SILVER = {
    "академия ска",
    "амурские тигры",
    "красная машина атлант",
    "красная машина юниор",
    "крылья советов",
    "мхк спартак мах",
    "сахалинские акулы",
    "тайфун",
}

_BASE_FETCH_STANDINGS = feature._fetch_standings
_ESK_CACHE: tuple[float, dict] | None = None


def _norm(value: str) -> str:
    return core.compact(str(value)).casefold().replace("ё", "е").replace("–", "-").replace("—", "-")


def _team_index(headers: list[str]) -> int:
    for i, h in enumerate(headers):
        if _norm(h) in {"команда", "команды", "клуб"}:
            return i
    return 1 if len(headers) > 1 else 0


def _renumber(rows: list[list[str]]) -> list[list[str]]:
    out = []
    for pos, row in enumerate(rows, 1):
        r = list(row)
        if r:
            r[0] = str(pos)
        out.append(r)
    return out


def _position(table: dict, team: str) -> int | None:
    headers = list(table.get("headers") or [])
    idx = _team_index(headers)
    for pos, row in enumerate(table.get("rows") or [], 1):
        if idx < len(row) and _norm(row[idx]) == _norm(team):
            return pos
    return None


def _places_away(pos: int | None, cutoff: int) -> int | None:
    if pos is None or pos <= cutoff:
        return 0 if pos else None
    return pos - cutoff


def _decorate(table: dict, team_key: str, target: str) -> dict:
    rows = list(table.get("rows") or [])
    pos = _position(table, target)
    zones: dict[int, str] = {}
    legend: list[tuple[str, str]] = []
    status = ""

    if team_key == "ska":
        for p in range(1, min(8, len(rows)) + 1):
            zones[p] = "direct"
        legend = [("direct", "зона плей-офф")]
        if pos:
            status = f"{pos}-е место на Западе · " + ("в зоне плей-офф" if pos <= 8 else f"до зоны плей-офф: {pos - 8} мест.")

    elif team_key == "ska_vmf":
        for p in range(1, min(16, len(rows)) + 1):
            zones[p] = "direct"
        legend = [("direct", "зона плей-офф: топ-16")]
        if pos:
            status = f"{pos}-е место в ВХЛ · " + ("в зоне плей-офф" if pos <= 16 else f"до зоны плей-офф: {pos - 16} место")

    elif team_key == "ska_1946":
        for p in range(1, min(5, len(rows)) + 1):
            zones[p] = "direct"
        for p in range(6, min(8, len(rows)) + 1):
            zones[p] = "playin"
        legend = [("direct", "напрямую в плей-офф"), ("playin", "плей-ин")]
        if pos:
            if pos <= 5:
                status = f"{pos}-е место в Золотом дивизионе · напрямую в плей-офф"
            elif pos <= 8:
                status = f"{pos}-е место в Золотом дивизионе · зона плей-ин"
            else:
                status = f"{pos}-е место в Золотом дивизионе · вне плей-ин"

    elif team_key == "academy":
        for p in range(1, min(3, len(rows)) + 1):
            zones[p] = "playin"
        legend = [("playin", "зона плей-ин: топ-3")]
        if pos:
            status = f"{pos}-е место в Серебряном дивизионе · " + ("в зоне плей-ин" if pos <= 3 else f"до зоны плей-ин: {pos - 3} места")

    elif team_key == "eskulap":
        cutoff = table.get("playoff_cutoff")
        if isinstance(cutoff, int) and cutoff > 0:
            for p in range(1, min(cutoff, len(rows)) + 1):
                zones[p] = "direct"
            legend = [("direct", f"зона плей-офф: топ-{cutoff}")]
            if pos:
                status = f"{pos}-е место · " + ("в зоне плей-офф" if pos <= cutoff else f"до зоны плей-офф: {pos - cutoff} места")
        elif pos:
            status = f"{pos}-е место из {len(rows)} · на странице турнира граница плей-офф не указана"

    return {**table, "zones": zones, "legend": legend, "status_text": status}


def _filter_mhl(table: dict, team_key: str) -> dict:
    headers = list(table.get("headers") or [])
    rows = [list(r) for r in table.get("rows") or []]
    idx = _team_index(headers)
    allowed = MHL_WEST_GOLD if team_key == "ska_1946" else MHL_WEST_SILVER
    filtered = [r for r in rows if idx < len(r) and _norm(r[idx]) in allowed]
    target = "СКА-1946" if team_key == "ska_1946" else "Академия СКА"
    if not filtered or not any(idx < len(r) and _norm(r[idx]) == _norm(target) for r in filtered):
        # Never show a confidently wrong division: fall back to conference table.
        return {**table, "note": "не удалось автоматически выделить дивизион — показана конференция"}
    title = "Запад · Золотой дивизион" if team_key == "ska_1946" else "Запад · Серебряный дивизион"
    return {**table, "title": title, "rows": _renumber(filtered)}


def _parse_date_range(text: str):
    m = re.search(r"(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}\.\d{2}\.\d{4})", text)
    if not m:
        return None, None
    try:
        start = datetime.strptime(m.group(1), "%d.%m.%Y").date()
        end = datetime.strptime(m.group(2), "%d.%m.%Y").date()
        return start, end
    except ValueError:
        return None, None


def _discover_eskulap_tournament() -> dict:
    global _ESK_CACHE
    if _ESK_CACHE and time.time() - _ESK_CACHE[0] < 900:
        return _ESK_CACHE[1]

    headers = {"User-Agent": "Mozilla/5.0 HockeyHub", "Accept-Language": "ru-RU,ru;q=0.9"}
    home = requests.get("https://spbhl.ru/", headers=headers, timeout=20)
    home.raise_for_status()
    home.encoding = home.apparent_encoding or home.encoding
    soup = BeautifulSoup(home.text, "html.parser")

    candidates: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        href = a.get("href") or ""
        m = re.search(r"TournamentID=(\d+)", href, re.I)
        if not m:
            continue
        tid = m.group(1)
        label = core.compact(a.get_text(" ", strip=True))
        candidates.setdefault(tid, label)

    # Current Eskulap is D5-level. Prioritize the relevant family, then newer ids.
    ordered = sorted(
        candidates.items(),
        key=lambda x: (
            0 if "север парк" in _norm(x[1]) else 1 if "д5" in _norm(x[1]) else 2,
            -int(x[0]),
        ),
    )

    today = datetime.now(core.MOSCOW).date()
    found = []
    for tid, label in ordered[:28]:
        url = f"https://spbhl.ru/Tournament?TournamentID={tid}"
        try:
            r = requests.get(url, headers=headers, timeout=8)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or r.encoding
        except Exception:
            continue
        text = core.compact(BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True))
        if "Эскулап" not in text:
            continue
        start, end = _parse_date_range(text)
        pm = re.search(r"в\s+плей-офф\s+выходят\s+(\d+)", text, re.I)
        cutoff = int(pm.group(1)) if pm else None
        heading_soup = BeautifulSoup(r.text, "html.parser")
        heading = next((core.compact(h.get_text(" ", strip=True)) for h in heading_soup.find_all(["h1", "h2", "h3"]) if "турнир" not in _norm(h.get_text(" ", strip=True)) and len(core.compact(h.get_text(" ", strip=True))) > 4), "")
        found.append({
            "id": tid,
            "label": heading or label or f"Турнир {tid}",
            "start": start,
            "end": end,
            "playoff_cutoff": cutoff,
            "url": url,
            "standings_url": f"https://spbhl.ru/Standings.aspx?TournamentID={tid}",
        })

    if not found:
        info = {
            "id": "6533",
            "label": "Летнее Первенство 2026 · Север Парк Д5",
            "start": datetime(2026, 7, 6).date(),
            "end": datetime(2026, 10, 1).date(),
            "playoff_cutoff": None,
            "url": "https://spbhl.ru/Tournament?TournamentID=6533",
            "standings_url": "https://spbhl.ru/Standings.aspx?TournamentID=6533",
        }
    else:
        active = [x for x in found if x["start"] and x["end"] and x["start"] <= today <= x["end"]]
        if active:
            # If tournaments overlap, prefer the one that started later; this lets
            # the regular season naturally replace the summer tournament.
            info = max(active, key=lambda x: x["start"])
        else:
            future = [x for x in found if x["start"] and x["start"] > today]
            if future:
                info = min(future, key=lambda x: x["start"])
            else:
                info = max(found, key=lambda x: x["end"] or datetime(2000, 1, 1).date())

    _ESK_CACHE = (time.time(), info)
    print(f"[verify] Eskulap tournament auto: {info['id']} {info['label']} {info.get('start')}..{info.get('end')}", flush=True)
    return info


def _fetch_eskulap_standings() -> dict:
    info = _discover_eskulap_tournament()
    try:
        data = feature._table_from_html(info["standings_url"], "Эскулап")
    except Exception as exc:
        # Current tournament page itself also contains a compact standings table.
        try:
            data = feature._table_from_html(info["url"], "Эскулап")
        except Exception:
            raise exc
    data["source"] = info["url"]
    data["title"] = info["label"]
    data["tournament_id"] = info["id"]
    data["playoff_cutoff"] = info.get("playoff_cutoff")
    if info.get("end"):
        data["note"] = f"турнир определяется автоматически · до {info['end'].strftime('%d.%m.%Y')}"
    else:
        data["note"] = "турнир определяется автоматически"
    return data


def fetch_standings_v32(team_key: str) -> dict:
    target = feature.TEAM_META[team_key]["name"]
    if team_key == "eskulap":
        data = _fetch_eskulap_standings()
    else:
        data = _BASE_FETCH_STANDINGS(team_key)
    if team_key in {"ska_1946", "academy"}:
        data = _filter_mhl(data, team_key)
    return _decorate(data, team_key, target)


feature._fetch_standings = fetch_standings_v32
feature.STANDINGS_CACHE.clear()


def render_standings_v32(table: dict, target: str) -> str:
    if not table.get("rows"):
        return (
            '<div class="notice">Таблица сейчас не загрузилась. '
            f'<a href="{html.escape(table.get("source") or "#")}" target="_blank" rel="noopener">Открыть источник ↗</a></div>'
        )

    headers = list(table.get("headers") or [])
    rows = list(table.get("rows") or [])
    head = "".join(f"<th>{html.escape(str(x))}</th>" for x in headers)
    idx = _team_index(headers)
    zones = table.get("zones") or {}

    body = []
    for pos, row in enumerate(rows, 1):
        team_cell = row[idx] if idx < len(row) else ""
        classes = []
        if _norm(team_cell) == _norm(target):
            classes.append("me")
        zone = zones.get(pos)
        if zone:
            classes.append(f"zone-{zone}")
        cells = "".join(f"<td>{html.escape(str(x))}</td>" for x in row)
        body.append(f'<tr class="{" ".join(classes)}">{cells}</tr>')

    status = core.compact(table.get("status_text") or "")
    status_html = f'<div class="qual-status">{html.escape(status)}</div>' if status else ""
    legend_bits = []
    for kind, label in table.get("legend") or []:
        legend_bits.append(f'<span class="legend-item"><i class="legend-dot {kind}"></i>{html.escape(label)}</span>')
    legend_html = f'<div class="zone-legend">{"".join(legend_bits)}</div>' if legend_bits else ""
    source = html.escape(table.get("source") or "#")
    note = core.compact(table.get("note") or "")
    note_html = f'<div class="table-source">{html.escape(note)}</div>' if note else ""

    return (
        status_html
        + f'<div class="table-scroll"><table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
        + legend_html
        + f'<div class="table-source"><a href="{source}" target="_blank" rel="noopener">Источник таблицы ↗</a></div>'
        + note_html
    )


# The team page renderer in v22 resolves this function dynamically from its module.
team_ui._render_standings_exact = render_standings_v32

_OLD_TEAM_PAGE = feature.render_team_page


def render_team_page_v32(team_key: str) -> str:
    page = _OLD_TEAM_PAGE(team_key)
    for old in ("v0.31", "v0.30", "v0.29", "v0.23"):
        page = page.replace(old, "v0.32")
    extra_css = '''
.qual-status{margin:0 0 10px;padding:10px 13px;border:1px solid #2b3340;border-radius:11px;background:#151922;color:#d7dde7;font-size:13px;font-weight:650}
tr.zone-direct:not(.me){background:rgba(73,154,96,.055)}
tr.zone-playin:not(.me){background:rgba(194,147,52,.065)}
tr.me.zone-direct{background:#203028;box-shadow:inset 3px 0 0 #78c88d}
tr.me.zone-playin{background:#302a1e;box-shadow:inset 3px 0 0 #d1a853}
.zone-legend{display:flex;flex-wrap:wrap;gap:14px;margin:8px 3px 0;color:#7f8999;font-size:11px}
.legend-item{display:inline-flex;align-items:center;gap:6px}.legend-dot{width:8px;height:8px;border-radius:50%;display:inline-block}.legend-dot.direct{background:#78c88d}.legend-dot.playin{background:#d1a853}
'''
    page = page.replace("</style>", extra_css + "</style>", 1)
    return page


feature.render_team_page = render_team_page_v32


def render_page_v32() -> str:
    return prev.render_page_v31().replace("v0.31", "v0.32", 1)


core.render_page = render_page_v32
app = core.app
