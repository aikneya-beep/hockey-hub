from datetime import datetime
from zoneinfo import ZoneInfo

import source_links_v38 as links
import app_v05 as core


TZ = ZoneInfo("Europe/Moscow")


def test_khl_match_url_uses_2026_27_tournament_fallback():
    event = {"id": 902027, "khl_id": 902027}
    assert links.khl_match_url(event) == "https://www.khl.ru/game/1436/902027/preview/"


def test_khl_match_url_prefers_tournament_from_event():
    event = {"khl_id": 123, "tournament": {"id": 9999}}
    assert links.khl_match_url(event) == "https://www.khl.ru/game/9999/123/preview/"


def test_ska_site_enrichment_selects_specific_match_page(monkeypatch):
    html = '''
    <html><body>
      <div class="game-card">
        <span>15.09</span><span>18:30</span>
        <span>МХК Спартак МАХ</span><span>Академия СКА</span>
        <a href="/championship/games/46459/">Матч</a>
      </div>
      <div class="game-card">
        <span>16.09</span><span>18:30</span>
        <span>МХК Спартак МАХ</span><span>Академия СКА</span>
        <a href="/championship/games/46460/">Матч</a>
      </div>
    </body></html>
    '''

    class Response:
        text = html
        def raise_for_status(self):
            return None

    monkeypatch.setattr(links.requests, "get", lambda *a, **k: Response())
    game = core.Game(
        "mhl_ska_site", "x", "МХЛ", "МХК Спартак МАХ", "Академия СКА",
        datetime(2026, 9, 15, 18, 30, tzinfo=TZ), source_url="https://junior.ska.ru/championship/games/"
    )
    count = links.enrich_ska_site_match_links(
        "https://junior.ska.ru/championship/games/", "Академия СКА", [game]
    )
    assert count == 1
    assert game.source_url == "https://junior.ska.ru/championship/games/46459/"
