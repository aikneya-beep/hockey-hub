from __future__ import annotations

from datetime import datetime
import html
import re

import environment_v50 as env
import personal_hockey_v42 as personal_base


_previous_renderer = env.render_environment


def _esc(value) -> str:
    return html.escape(str(value or ""))


def _result_for_eskulap_v501(game) -> tuple[str, str]:
    if game.home_score is None or game.away_score is None:
        return "—", "neutral"
    home = game.home_team == "Эскулап"
    gf = game.home_score if home else game.away_score
    ga = game.away_score if home else game.home_score
    if gf > ga:
        return "В", "win"
    if gf < ga:
        return "П", "loss"
    return "Н", "draw"


def _recent_games_html_v501(finished) -> str:
    if not finished:
        return '<div class="empty">Матчей пока нет.</div>'
    rows = []
    for game in reversed(finished[-3:]):
        label, cls = _result_for_eskulap_v501(game)
        source = (
            f'<a href="{html.escape(game.source_url, quote=True)}" target="_blank" rel="noopener">источник ↗</a>'
            if game.source_url else ""
        )
        rows.append(
            f'''<article class="match-row">
              <time>{game.start_at.strftime('%d.%m')}</time>
              <span class="result-mark {cls}">{label}</span>
              <div><b>{_esc(game.home_team)} <strong>{game.home_score}:{game.away_score}</strong> {_esc(game.away_team)}</b><em>{_esc(game.arena or 'СПбХЛ')}</em></div>
              {source}
            </article>'''
        )
    return "".join(rows)


def _coach_focus_html() -> str:
    try:
        data = personal_base.STORE.load()
        notes = sorted(data.get("coach_notes") or [], key=lambda x: x.get("date", ""), reverse=True)
        sessions = sorted(data.get("sessions") or [], key=lambda x: x.get("date", ""), reverse=True)
    except Exception:
        notes, sessions = [], []

    latest = notes[0] if notes else None
    if latest:
        raw_date = latest.get("date") or ""
        try:
            date_label = datetime.strptime(raw_date, "%Y-%m-%d").strftime("%d.%m.%Y")
        except Exception:
            date_label = raw_date
        focus_text = _esc(latest.get("text") or "")
        return f'''<div class="coach-link-grid">
          <div><span>Текущий фокус</span><b>{focus_text}</b><em>{_esc(date_label)}</em></div>
          <div><span>Тренировок в истории</span><strong>{len(sessions)}</strong><em>личная история</em></div>
          <div><span>Комментариев тренера</span><strong>{len(notes)}</strong><em>сохранено</em></div>
        </div>'''

    return f'''<div class="coach-link-grid">
      <div><span>Текущий фокус</span><b>Новый комментарий тренера появится здесь после тренировки.</b></div>
      <div><span>Тренировок в истории</span><strong>{len(sessions)}</strong><em>личная история</em></div>
      <div><span>Комментариев тренера</span><strong>0</strong><em>сохранено</em></div>
    </div>'''


def render_environment_v501() -> str:
    page = _previous_renderer()

    page = page.replace("Мой хоккей · v0.50", "Мой хоккей · v0.50.1", 1)
    page = page.replace("5 последних", "3 последних", 1)

    # Promote the coach from the left column to a full-width primary block.
    coach_match = re.search(r'<article class="coach-card">.*?</article>', page, flags=re.S)
    if coach_match:
        coach = coach_match.group(0)
        coach = coach.replace(
            '<div class="coach-tags">',
            _coach_focus_html() + '<div class="coach-tags">',
            1,
        )
        page = page[:coach_match.start()] + page[coach_match.end():]
        marker = '<section class="env-grid">'
        page = page.replace(marker, coach + marker, 1)

    # The last-match stat duplicates the recent-matches block; remove it.
    page = re.sub(
        r'<div class="mini-stat"><span>Последний матч</span><b style="font-size:11px;line-height:1\.35">.*?</b></div>',
        '',
        page,
        count=1,
        flags=re.S,
    )

    # Make personal coach notes the first thing in the side column; empty next match goes lower.
    aside_match = re.search(r'<aside class="side-stack">(.*?)</aside>', page, flags=re.S)
    if aside_match:
        aside = aside_match.group(1)
        cards = re.findall(r'<article class="hub-card panel">.*?</article>', aside, flags=re.S)
        if len(cards) >= 3:
            next_card, notes_card, teams_card = cards[:3]
            reordered = notes_card + teams_card + next_card
            page = page[:aside_match.start(1)] + reordered + page[aside_match.end(1):]

    extra_css = '''
/* v0.50.1 composition */
.coach-card{margin-bottom:14px;min-height:0;padding:22px 22px 20px}
.coach-copy{margin-top:14px;max-width:820px}
.coach-link-grid{display:grid;grid-template-columns:minmax(0,1.8fr) .6fr .6fr;gap:8px;margin-top:18px}
.coach-link-grid>div{border:1px solid #26313c;background:#090d12;border-radius:11px;padding:11px 12px;min-height:74px}
.coach-link-grid span{display:block;color:#667587;font-size:8px;text-transform:uppercase;letter-spacing:.08em}
.coach-link-grid b{display:block;color:#cbd2db;font-size:10px;line-height:1.45;margin-top:7px;font-weight:650}
.coach-link-grid strong{display:block;font-size:20px;margin-top:7px}
.coach-link-grid em{display:block;color:#617080;font-size:8px;font-style:normal;margin-top:5px}
.env-grid{grid-template-columns:minmax(0,1.15fr) minmax(330px,.85fr);align-items:start}
.team-card{margin-top:0}
.team-stats{grid-template-columns:repeat(3,1fr)}
.next-game{min-height:0;padding:11px 12px}
.next-game .empty{padding:2px 0}
.side-stack>.hub-card:last-child{padding:14px 16px}
.side-stack>.hub-card:last-child .section-title{margin-bottom:8px}
.match-row{padding:9px 0}
@media(max-width:900px){.coach-link-grid{grid-template-columns:1fr 1fr}.coach-link-grid>div:first-child{grid-column:1/-1}}
@media(max-width:620px){.coach-link-grid,.team-stats{grid-template-columns:1fr}.coach-link-grid>div:first-child{grid-column:auto}}
'''
    page = page.replace('</style>', extra_css + '</style>', 1)
    return page


env._result_for_eskulap = _result_for_eskulap_v501
env._recent_games_html = _recent_games_html_v501
env.render_environment = render_environment_v501
