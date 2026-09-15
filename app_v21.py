from __future__ import annotations

import re
import time

import requests
from bs4 import BeautifulSoup

import app_v20 as stable
import app_v19 as feature
import app_v05 as core


_old_html_table = feature._table_from_html
_old_khl_table = feature._fetch_khl_standings

SKA_TABLE_HEADERS = ["М", "Команда", "И", "В", "ВО", "ВБ", "ПБ", "ПО", "П", "ЗШ", "ПШ", "О"]


def _is_int(text: str) -> bool:
    return bool(re.fullmatch(r"\d+", core.compact(text)))


def _parse_ska_block_table(url: str, target: str) -> dict:
    resp = requests.get(
        url,
        timeout=25,
        headers={
            "User-Agent": "Mozilla/5.0 HockeyHub",
            "Accept-Language": "ru-RU,ru;q=0.9",
        },
    )
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding
    soup = BeautifulSoup(resp.text, "html.parser")
    tokens = [core.compact(x) for x in soup.stripped_strings if core.compact(x)]

    # Official SKA standings are rendered as divs rather than a literal <table>.
    # Each standings row is: rank, team, then ten numeric columns
    # И В ВО ВБ ПБ ПО П ЗШ ПШ О. Conference/league blocks restart at rank 1.
    blocks: list[list[list[str]]] = []
    current: list[list[str]] = []
    expected_rank = 1
    i = 0
    while i <= len(tokens) - 12:
        rank = tokens[i]
        name = tokens[i + 1]
        stats = tokens[i + 2 : i + 12]
        valid = (
            _is_int(rank)
            and not _is_int(name)
            and all(_is_int(x) for x in stats)
            and 1 <= int(rank) <= 80
        )
        if valid:
            r = int(rank)
            if r == 1:
                if current:
                    blocks.append(current)
                current = [[rank, name, *stats]]
                expected_rank = 2
                i += 12
                continue
            if current and r == expected_rank:
                current.append([rank, name, *stats])
                expected_rank += 1
                i += 12
                continue
        i += 1
    if current:
        blocks.append(current)

    block = next(
        (b for b in blocks if any(core.compact(row[1]).casefold() == target.casefold() for row in b)),
        None,
    )
    if not block:
        # A tiny naming mismatch should not kill the page; allow containment as a
        # fallback, but only inside a structurally valid standings block.
        block = next(
            (b for b in blocks if any(target.casefold() in core.compact(row[1]).casefold() for row in b)),
            None,
        )
    if not block:
        raise ValueError(f"не найден турнирный блок {target}; blocks={len(blocks)}")

    title = "Турнирная таблица"
    if target in {"СКА-1946", "Академия СКА"}:
        title = "Конференция"
    return {
        "title": title,
        "headers": SKA_TABLE_HEADERS,
        "rows": block,
        "source": url,
    }


def table_from_html_v21(url: str, target: str) -> dict:
    if "ska.ru" in url:
        return _parse_ska_block_table(url, target)
    return _old_html_table(url, target)


def khl_standings_v21() -> dict:
    last = None
    for attempt in range(1, 4):
        try:
            return _old_khl_table()
        except (requests.RequestException, ValueError) as exc:
            last = exc
            print(f"[standings] KHL retry {attempt}/3: {type(exc).__name__}: {exc}", flush=True)
            if attempt < 3:
                time.sleep(1.5 * attempt)
    raise last or RuntimeError("не удалось получить таблицу КХЛ")


feature._table_from_html = table_from_html_v21
feature._fetch_khl_standings = khl_standings_v21

core.app.version = "0.21.0"


_team_page_v20 = feature.render_team_page


def render_team_page_v21(team_key: str) -> str:
    return _team_page_v20(team_key).replace("v0.20", "v0.21")


feature.render_team_page = render_team_page_v21


def render_page_v21() -> str:
    return stable.render_page_v20().replace("v0.20", "v0.21", 1)


core.render_page = render_page_v21
app = core.app
