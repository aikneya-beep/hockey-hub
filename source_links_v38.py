from __future__ import annotations

from datetime import datetime
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import app_v05 as core

# KHL tournament id for the 2026/27 championship. The event payload is checked
# first, so this is only a season fallback for payloads that expose the match id
# but omit tournament metadata.
KHL_2026_27_TOURNAMENT_ID = "1436"


def _as_id(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("id") or value.get("khl_id")
    value = str(value).strip()
    return value if value and value.lower() != "none" else None


def khl_tournament_id(event: dict) -> str | None:
    """Best-effort tournament id extraction from official KHL event payload."""
    for key in ("tournament_id", "championship_id"):
        value = _as_id(event.get(key))
        if value:
            return value
    for key in ("tournament", "championship"):
        value = _as_id(event.get(key))
        if value:
            return value
    stage = event.get("stage")
    if isinstance(stage, dict):
        for key in ("tournament_id", "championship_id"):
            value = _as_id(stage.get(key))
            if value:
                return value
        for key in ("tournament", "championship"):
            value = _as_id(stage.get(key))
            if value:
                return value
    return None


def khl_match_url(event: dict) -> str | None:
    match_id = _as_id(event.get("khl_id")) or _as_id(event.get("id"))
    if not match_id:
        return None
    tournament_id = khl_tournament_id(event)
    if not tournament_id:
        # All KHL events currently collected by Hockey Hub belong to 2026/27.
        tournament_id = KHL_2026_27_TOURNAMENT_ID
    return f"https://www.khl.ru/game/{tournament_id}/{match_id}/preview/"


def _detail_href(href: str) -> bool:
    path = str(href or "")
    return bool(re.search(r"/championship/games/\d+/?(?:[?#].*)?$", path))


def _candidate_context(anchor, wanted_name: str) -> str:
    """Find the smallest ancestor that looks like one match card."""
    node = anchor
    best = ""
    for _ in range(7):
        if node is None:
            break
        try:
            text = core.compact(node.get_text(" ", strip=True))
        except Exception:
            text = ""
        if text and wanted_name in text and re.search(r"\b\d{2}\.\d{2}(?:\.\d{4})?\b", text):
            best = text
            break
        node = getattr(node, "parent", None)
    return best


def enrich_ska_site_match_links(page_url: str, wanted_name: str, games: list[core.Game]) -> int:
    """Replace list-page links with official per-match pages when available."""
    try:
        response = requests.get(page_url, timeout=20, headers={"User-Agent": "Mozilla/5.0 HockeyHub"})
        response.raise_for_status()
    except Exception as exc:
        print(f"[source-link] {wanted_name}: detail page scan failed: {type(exc).__name__}: {exc}", flush=True)
        return 0

    soup = BeautifulSoup(response.text, "html.parser")
    candidates: list[tuple[str, str]] = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href") or ""
        if not _detail_href(href):
            continue
        absolute = urljoin(page_url, href)
        if absolute in seen:
            continue
        context = _candidate_context(anchor, wanted_name)
        if not context:
            continue
        seen.add(absolute)
        candidates.append((absolute, context))

    enriched = 0
    for game in games:
        date_short = game.start_at.strftime("%d.%m")
        date_full = game.start_at.strftime("%d.%m.%Y")
        time_text = game.start_at.strftime("%H:%M")
        matches = []
        for absolute, context in candidates:
            if game.home_team not in context or game.away_team not in context:
                continue
            if date_short not in context and date_full not in context:
                continue
            # Date + both teams is already strong; time resolves double-headers.
            score = 0 if time_text in context else 1
            matches.append((score, len(context), absolute))
        if matches:
            matches.sort()
            game.source_url = matches[0][2]
            enriched += 1

    print(f"[verify] source links {wanted_name}: detail={enriched}/{len(games)} candidates={len(candidates)}", flush=True)
    return enriched
