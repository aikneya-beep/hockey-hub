from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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


def _table():
    return {
        "title": "Западная конференция",
        "headers": ["#", "Команда"],
        "rows": [["1", "Локомотив"], ["2", "СКА"]],
        "zones": {1: "direct", 2: "direct"},
    }


def test_next_round_scheduled_game_beats_longer_previous_series():
    now = datetime(2027, 4, 12, 12, 0, tzinfo=TZ)
    games = []
    # Six games in round one.
    for i in range(6):
        games.append(
            Game(
                "СКА" if i % 2 == 0 else "ЦСКА",
                "ЦСКА" if i % 2 == 0 else "СКА",
                datetime(2027, 3, 23, 19, 30, tzinfo=TZ) + timedelta(days=i * 2),
                "finished",
                3 if i % 2 == 0 else 1,
                1 if i % 2 == 0 else 3,
                f"r1-{i}",
            )
        )
    # Quarterfinal has just been published and must become the current series.
    games.extend([
        Game("СКА", "Динамо М", datetime(2027, 4, 13, 19, 30, tzinfo=TZ), gid="r2-1"),
        Game("Динамо М", "СКА", datetime(2027, 4, 15, 19, 30, tzinfo=TZ), gid="r2-2"),
    ])

    snap = build_snapshot("ska", "СКА", "КХЛ", _table(), games, now)
    assert snap.series is not None
    assert snap.series.team_b == "Динамо М"
    assert snap.series.game_ids == ["r2-1", "r2-2"]
    assert snap.series.score_text == "0:0"
