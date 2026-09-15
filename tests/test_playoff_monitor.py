from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from hockey_domain import StageKind
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


NOW = datetime(2027, 3, 25, 12, 0, tzinfo=ZoneInfo("Europe/Moscow"))


def test_regular_repeated_opponent_is_not_a_series():
    games = [
        Game("СКА", "ЦСКА", NOW - timedelta(days=10), "finished", 3, 2, "1"),
        Game("ЦСКА", "СКА", NOW + timedelta(days=10), "scheduled", gid="2"),
    ]
    table = {"title": "Западная конференция", "status_text": "5-е место · в зоне плей-офф"}
    snap = build_snapshot("ska", "СКА", "КХЛ", table, games, NOW)
    assert snap.stage_kind == StageKind.REGULAR
    assert snap.series is None


def test_playoff_title_builds_series_score_from_finished_games():
    games = [
        Game("СКА", "ЦСКА", NOW - timedelta(days=2), "finished", 3, 2, "1"),
        Game("ЦСКА", "СКА", NOW - timedelta(days=1), "finished", 4, 1, "2"),
        Game("СКА", "ЦСКА", NOW + timedelta(days=1), "scheduled", gid="3"),
    ]
    table = {"title": "Плей-офф · 1/8 финала", "source": "https://example.test/playoff"}
    snap = build_snapshot("ska", "СКА", "КХЛ", table, games, NOW)
    assert snap.stage_kind == StageKind.PLAYOFF
    assert snap.series is not None
    assert snap.series.team_b == "ЦСКА"
    assert snap.series.score_text == "1:1"
    assert set(snap.series.game_ids) == {"1", "2", "3"}


def test_play_in_is_detected_before_generic_playoff():
    table = {"title": "Плей-ин МХЛ", "status_text": "серия ещё не началась"}
    snap = build_snapshot("academy", "Академия СКА", "МХЛ", table, [], NOW)
    assert snap.stage_kind == StageKind.PLAY_IN
    assert snap.series is None
