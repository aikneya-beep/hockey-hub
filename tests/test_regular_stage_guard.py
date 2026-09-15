from datetime import datetime
from zoneinfo import ZoneInfo

from hockey_domain import StageKind
from playoff_monitor import build_snapshot


def test_in_playoff_zone_text_does_not_activate_postseason():
    now = datetime(2026, 9, 15, 20, 0, tzinfo=ZoneInfo("Europe/Moscow"))
    table = {
        "title": "Западная конференция",
        "headers": ["М", "Команда", "И", "О"],
        "rows": [["1", "Локомотив", "5", "10"], ["2", "СКА", "5", "8"]],
        "zones": {1: "direct", 2: "direct"},
        "status_text": "2-е место на Западе · в зоне плей-офф",
    }
    snap = build_snapshot("ska", "СКА", "КХЛ", table, [], now)
    assert snap.stage_kind == StageKind.REGULAR
    assert snap.series is None
