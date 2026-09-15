from __future__ import annotations

import app_v22 as prev
import app_v19 as feature
import app_v05 as core

core.app.version = "0.23.0"

_old_compact = prev._compact_table


def compact_table_v23(table: dict, team_key: str) -> dict:
    if team_key != "eskulap":
        return _old_compact(table, team_key)

    rows = []
    for raw in table.get("rows") or []:
        row = list(raw)
        while row and core.compact(str(row[-1])) == "":
            row.pop()
        if len(row) >= 10:
            # SPbHL omits the diagonal H2H cell, so deleting columns by their
            # header indexes shifts the stats. The last 8 cells are stable:
            # И, В, ВБ, ПБ, П, РШ, ШТ, О.
            rows.append([row[0], row[1], *row[-8:]])
        else:
            rows.append(row)

    return {
        **table,
        "headers": ["№", "Команда", "И", "В", "ВБ", "ПБ", "П", "РШ", "ШТ", "О"],
        "rows": rows,
    }


prev._compact_table = compact_table_v23

_old_khl = feature._fetch_khl_standings

_KHL_SNAPSHOT = {
    "title": "Западная конференция",
    "headers": ["М", "Команда", "И", "В", "П", "Ш", "О"],
    "rows": [
        ["1", "Локомотив", "4", "4", "0", "13:5", "8"],
        ["2", "Торпедо", "5", "4", "1", "15:10", "8"],
        ["3", "СКА", "5", "4", "1", "13:10", "8"],
        ["4", "Спартак", "4", "3", "1", "14:4", "6"],
        ["5", "Динамо М", "5", "3", "2", "11:10", "6"],
        ["6", "Драконы", "3", "2", "1", "10:10", "4"],
        ["7", "Лада", "5", "1", "4", "10:16", "4"],
        ["8", "Динамо Мн", "4", "0", "4", "10:15", "3"],
        ["9", "Северсталь", "5", "1", "4", "4:15", "3"],
        ["10", "ЦСКА", "4", "1", "3", "9:10", "2"],
        ["11", "ХК Сочи", "3", "0", "3", "2:10", "0"],
    ],
    "source": "https://www.khl.ru/standings/",
    "note": "резервная копия на 15.09.2026",
}


def khl_standings_v23() -> dict:
    try:
        data = _old_khl()
        data["note"] = "данные КХЛ"
        return data
    except Exception as exc:
        print(f"[standings] KHL fallback snapshot: {type(exc).__name__}: {exc}", flush=True)
        return dict(_KHL_SNAPSHOT)


feature._fetch_khl_standings = khl_standings_v23

_old_standings_render = prev._render_standings_exact


def render_standings_v23(table: dict, target: str) -> str:
    base = _old_standings_render(table, target)
    note = core.compact(table.get("note") or "")
    if note:
        base += f'<div class="table-source">{note}</div>'
    return base


prev._render_standings_exact = render_standings_v23

_old_team_page = prev.render_team_page_v22


def render_team_page_v23(team_key: str) -> str:
    return _old_team_page(team_key).replace("v0.22", "v0.23")


feature.render_team_page = render_team_page_v23


def render_page_v23() -> str:
    return prev.render_page_v22().replace("v0.22", "v0.23", 1)


core.render_page = render_page_v23
app = core.app
