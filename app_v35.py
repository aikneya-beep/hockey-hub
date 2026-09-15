from __future__ import annotations

import html

import app_v34 as prev
import app_v33 as playoff_ui
import app_v19 as feature
import app_v05 as core
from hockey_domain import QualificationState, StageKind

core.app.version = "0.35.0"


STATUS_META = {
    QualificationState.DIRECT: ("direct", "В зоне плей-офф"),
    QualificationState.PLAY_IN: ("playin", "В зоне плей-ин"),
    QualificationState.OUTSIDE: ("outside", "Вне зоны"),
    QualificationState.POSTSEASON: ("postseason", "Постсезон"),
    QualificationState.UNKNOWN: ("unknown", "Статус не определён"),
}


def render_playoffs_page_v35() -> str:
    cards = []
    for team, table, snap, error in playoff_ui._snapshots():
        if error or snap is None:
            cards.append(f'''<article class="p-card"><div class="p-head"><b>{html.escape(team.name)}</b><span>{html.escape(team.league)}</span></div>
            <div class="p-summary bad">Не удалось получить положение: {html.escape(error or 'ошибка')}</div></article>''')
            continue

        status_kind, status_label = STATUS_META.get(snap.qualification_state, STATUS_META[QualificationState.UNKNOWN])
        position = f'<span class="position">{snap.position}-е место</span>' if snap.position else ""
        context = "Если бы регулярка закончилась сегодня" if snap.stage_kind == StageKind.REGULAR else "Текущий этап"

        series_html = ""
        if snap.series:
            series_html = (
                f'<div class="series"><div><span>Текущая серия</span><b>{html.escape(snap.series.team_a)} — {html.escape(snap.series.team_b)}</b></div>'
                f'<strong>{snap.series.wins_a}:{snap.series.wins_b}</strong></div>'
            )

        source = f'<a href="{html.escape(snap.source_url)}" target="_blank" rel="noopener">источник ↗</a>' if snap.source_url else ""
        cards.append(f'''<article class="p-card status-{status_kind}">
          <div class="p-head"><div><b>{html.escape(team.name)}</b><span>{html.escape(team.league)}</span></div>{position}</div>
          <div class="status-row"><span class="qual-badge">{html.escape(status_label)}</span><span class="phase">{html.escape(playoff_ui._phase_label(snap.stage_kind))}</span></div>
          <div class="context">{html.escape(context)}</div>
          <div class="p-summary">{html.escape(snap.summary)}</div>
          {series_html}
          <div class="p-foot"><span>{html.escape(playoff_ui.PLAYOFF_CALENDAR.get(team.key, ''))}</span>{source}</div>
        </article>''')

    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Плей-офф · Мой хоккей</title><meta name="theme-color" content="#0b0d11"><style>
:root{{color-scheme:dark;font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}*{{box-sizing:border-box}}body{{margin:0;background:#0b0d11;color:#f5f7fa}}a{{color:inherit}}.wrap{{max-width:920px;margin:auto;padding:26px 20px 80px}}.back{{color:#96a0b0;text-decoration:none;font-size:13px}}header{{border-bottom:1px solid #262b35;padding:18px 0 22px}}.eyebrow{{font-size:12px;letter-spacing:.13em;color:#8993a4}}h1{{font-size:40px;margin:7px 0 4px}}header p{{margin:0;color:#9aa4b3;line-height:1.45}}.grid{{display:grid;gap:10px;margin-top:26px}}.p-card{{position:relative;background:#12161d;border:1px solid #252a33;border-radius:14px;padding:15px 16px;overflow:hidden}}.p-card:before{{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:#596273}}.status-direct:before{{background:#72bd84}}.status-playin:before{{background:#d4ae62}}.status-outside:before{{background:#985f65}}.status-postseason:before{{background:#7c91c4}}.p-head{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}}.p-head>div{{display:flex;align-items:baseline;gap:8px;min-width:0}}.p-head b{{font-size:18px}}.p-head div span{{font-size:11px;color:#7f8999}}.position{{font-size:12px;color:#c1c9d5;white-space:nowrap;padding-top:2px}}.status-row{{display:flex;align-items:center;gap:7px;margin-top:12px;flex-wrap:wrap}}.qual-badge,.phase{{display:inline-block;padding:5px 8px;border-radius:7px;font-size:10px;font-weight:800;letter-spacing:.035em;text-transform:uppercase}}.qual-badge{{background:#1b222d;color:#dce2eb}}.status-direct .qual-badge{{background:#183020;color:#a9dfb5}}.status-playin .qual-badge{{background:#302916;color:#e4c77f}}.status-outside .qual-badge{{background:#301d20;color:#dfa0a7}}.status-postseason .qual-badge{{background:#1c263d;color:#b9c9ee}}.phase{{background:#171c24;color:#8f9aaa}}.context{{margin-top:9px;color:#697586;font-size:10px;text-transform:uppercase;letter-spacing:.055em}}.p-summary{{margin-top:5px;color:#e2e6ec;font-size:14px;line-height:1.4}}.bad{{color:#ff9b9b}}.series{{display:flex;justify-content:space-between;align-items:center;margin-top:13px;padding:11px 12px;background:#171c24;border-radius:9px}}.series>div{{display:grid;gap:3px}}.series span{{font-size:10px;color:#7e8999;text-transform:uppercase;letter-spacing:.05em}}.series b{{font-size:14px}}.series strong{{font-size:22px}}.p-foot{{display:flex;justify-content:space-between;gap:15px;margin-top:12px;color:#7e8898;font-size:11px}}.p-foot a{{text-decoration:none;white-space:nowrap}}@media(max-width:600px){{.wrap{{padding:20px 14px 60px}}h1{{font-size:34px}}.p-foot{{flex-direction:column;gap:5px}}.p-head b{{font-size:17px}}}}
</style></head><body><main class="wrap"><a class="back" href="/">← Все матчи</a><header><div class="eyebrow">МОЙ ХОККЕЙ · v0.35</div><h1>Плей-офф</h1><p>Сейчас — положение относительно проходной зоны. Когда начнётся постсезон, эти карточки переключатся на текущие серии и их счёт.</p></header><section class="grid">{''.join(cards)}</section></main></body></html>'''


# The route was registered in app_v33 and resolves its renderer from that module.
playoff_ui.render_playoffs_page = render_playoffs_page_v35


def render_team_page_v35(team_key: str) -> str:
    return feature.render_team_page(team_key).replace("v0.34", "v0.35")


# Capture the v0.34 renderer before replacing it.
_old_team_page = feature.render_team_page


def _team_page(team_key: str) -> str:
    return _old_team_page(team_key).replace("v0.34", "v0.35")


feature.render_team_page = _team_page

_old_home = core.render_page


def render_page_v35() -> str:
    return _old_home().replace("v0.34", "v0.35", 1)


core.render_page = render_page_v35
app = core.app
