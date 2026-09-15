from persistence import HockeyStorage


class Game:
    pass


def test_storage_is_safe_noop_without_database_url():
    store = HockeyStorage("")
    before = store.status()
    assert before["enabled"] is False
    after = store.mirror([], [])
    assert after["enabled"] is False
    assert after["connected"] is False
    assert after["error"] is None
    assert after["missing_games"] == 0
    assert after["mismatched_games"] == 0


def test_stage_hint_is_mapped_to_normalized_stage():
    regular = Game()
    playoff = Game()
    playoff.stage_hint = "playoff"
    playin = Game()
    playin.stage_hint = "play_in"

    assert HockeyStorage._stage_for_game(regular) == ("Регулярный сезон", "regular")
    assert HockeyStorage._stage_for_game(playoff) == ("Плей-офф", "playoff")
    assert HockeyStorage._stage_for_game(playin) == ("Плей-ин", "play_in")
