from persistence import HockeyStorage


def test_storage_is_safe_noop_without_database_url():
    store = HockeyStorage("")
    before = store.status()
    assert before["enabled"] is False
    after = store.mirror([], [])
    assert after["enabled"] is False
    assert after["connected"] is False
    assert after["error"] is None
