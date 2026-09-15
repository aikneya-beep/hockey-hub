from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from hockey_domain import QualificationState, SeriesStatus, StageKind
from playoff_monitor import build_snapshot


class Game:
    def __init__(self, home, away, when, status="scheduled", hs=None, aw=None, gid="g"):
        self.home_team = home
        self.away_team = away
        self.start_at = when
        self.status = status
        self.home_score = hs
        self.away_score = aw
        self.source_url = "https://example.test/game"
        self.source_game_id = gid


TZ = ZoneInfo("Europe/Moscow")
REGULAR_NOW = datetime(2026, 9, 15, 12, 0, tzinfo=TZ)


def _table(team, zone="direct", title="Западная конференция"):
    return {
        "title": title,
        "headers": ["#", "Команда", "И", "О"],
        "rows": [["1", "Локомотив", "10", "15"], ["2", team, "10", "14"]],
        "zones": {1: "direct", 2: zone},
        "status_text": f"2-е место · {zone}",
    }


def test_regular_repeated_opponent_is_not_a_series():
    games = [
        Game("СКА", "ЦСКА", REGULAR_NOW - timedelta(days=10), "finished", 3, 2, "1"),
        Game("ЦСКА", "СКА", REGULAR_NOW + timedelta(days=10), "scheduled", gid="2"),
    ]
    snap = build_snapshot("ska", "СКА", "КХЛ", _table("СКА"), games, REGULAR_NOW)
    assert snap.stage_kind == StageKind.REGULAR
    assert snap.series is None
    assert snap.position == 2
    assert snap.qualification_state == QualificationState.DIRECT


def test_regular_play_in_and_outside_are_machine_readable():
    base = {
        "title": "Запад · Золотой дивизион",
        "headers": ["#", "Команда"],
        "rows": [["1", "A"], ["2", "B"], ["3", "C"]],
        "zones": {1: "direct", 2: "playin"},
    }
    playin = build_snapshot("x", "B", "МХЛ", base, [], REGULAR_NOW)
    outside = build_snapshot("x", "C", "МХЛ", base, [], REGULAR_NOW)
    assert playin.qualification_state == QualificationState.PLAY_IN
    assert outside.qualification_state == QualificationState.OUTSIDE


def test_source_playoff_title_builds_series_score():
    now = datetime(2027, 3, 25, 12, 0, tzinfo=TZ)
    games = [
        Game("СКА", "ЦСКА", now - timedelta(days=2), "finished", 3, 2, "1"),
        Game("ЦСКА", "СКА", now - timedelta(days=1), "finished", 4, 1, "2"),
        Game("СКА", "ЦСКА", now + timedelta(days=1), "scheduled", gid="3"),
    ]
    table = {"title": "Плей-офф · 1/8 финала", "source": "https://example.test/playoff"}
    snap = build_snapshot("ska", "СКА", "КХЛ", table, games, now)
    assert snap.stage_kind == StageKind.PLAYOFF
    assert snap.qualification_state == QualificationState.POSTSEASON
    assert snap.series is not None
    assert snap.series.team_b == "ЦСКА"
    assert snap.series.score_text == "1:1"
    assert snap.series.wins_needed == 4
    assert snap.series.status == SeriesStatus.ACTIVE
    assert set(snap.series.game_ids) == {"1", "2", "3"}


def test_play_in_is_detected_before_generic_playoff():
    now = datetime(2027, 3, 25, 12, 0, tzinfo=TZ)
    table = {"title": "Плей-ин МХЛ", "status_text": "серия ещё не началась"}
    snap = build_snapshot("academy", "Академия СКА", "МХЛ", table, [], now)
    assert snap.stage_kind == StageKind.PLAY_IN
    assert snap.qualification_state == QualificationState.POSTSEASON
    assert snap.series is None


def test_khl_calendar_switches_final_regular_table_to_playoff():
    now = datetime(2027, 3, 23, 12, 0, tzinfo=TZ)
    games = [
        # A late regular-season rematch must be excluded by the March 23 boundary.
        Game("СКА", "ЦСКА", datetime(2027, 3, 18, 19, 30, tzinfo=TZ), "finished", 2, 1, "reg"),
        Game("СКА", "Динамо М", datetime(2027, 3, 23, 19, 30, tzinfo=TZ), gid="po1"),
        Game("Динамо М", "СКА", datetime(2027, 3, 25, 19, 30, tzinfo=TZ), gid="po2"),
    ]
    snap = build_snapshot("ska", "СКА", "КХЛ", _table("СКА"), games, now)
    assert snap.stage_kind == StageKind.PLAYOFF
    assert snap.series is not None
    assert snap.series.team_b == "Динамо М"
    assert set(snap.series.game_ids) == {"po1", "po2"}


def test_mhl_playin_and_direct_qualifier_have_different_stage_on_march_25():
    now = datetime(2027, 3, 25, 12, 0, tzinfo=TZ)
    playin_table = _table("Академия СКА", zone="playin", title="Запад · Серебряный дивизион")
    direct_table = _table("СКА-1946", zone="direct", title="Запад · Золотой дивизион")

    academy = build_snapshot("academy", "Академия СКА", "МХЛ", playin_table, [], now)
    ska1946 = build_snapshot("ska_1946", "СКА-1946", "МХЛ", direct_table, [], now)

    assert academy.stage_kind == StageKind.PLAY_IN
    assert academy.qualification_state == QualificationState.POSTSEASON
    assert ska1946.stage_kind == StageKind.OTHER
    assert ska1946.qualification_state == QualificationState.DIRECT
    assert "ожидание" in ska1946.summary.casefold()


def test_finished_best_of_seven_series_is_marked_finished():
    now = datetime(2027, 4, 5, 12, 0, tzinfo=TZ)
    games = [
        Game("СКА", "ЦСКА", datetime(2027, 3, 23 + i, 19, 30, tzinfo=TZ), "finished", 3, 1, str(i))
        for i in range(4)
    ]
    snap = build_snapshot("ska", "СКА", "КХЛ", _table("СКА"), games, now)
    assert snap.series is not None
    assert snap.series.wins_a == 4
    assert snap.series.status == SeriesStatus.FINISHED
