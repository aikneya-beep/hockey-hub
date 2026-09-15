from __future__ import annotations

import app_v09 as prev

core = prev.core
core.app.version = "0.10.0"

_original_render_page = prev.render_page_v09


def render_page_v10() -> str:
    page = _original_render_page().replace("v0.9", "v0.10", 1)

    extra_css = r'''
/* v0.10: фильтры по командам */
.pill{cursor:pointer;user-select:none;transition:opacity .15s ease,border-color .15s ease,background .15s ease}
.pill:hover{border-color:#414b5a}
.pill:focus-visible{outline:2px solid #76849a;outline-offset:2px}
.pill.filter-selected{background:#202632;border-color:#657187;color:#fff}
.sources.has-team-filter .pill:not(.filter-selected){opacity:.38}
.match[hidden],.day[hidden]{display:none!important}
.filter-empty{display:none;color:#8993a4;padding:28px 2px}
'''
    page = page.replace("</style>", extra_css + "\n</style>", 1)

    extra_js = r'''
  // Фильтр по отслеживаемым командам. Пустой выбор означает «показывать все».
  const teamFilterKey='hockeyHubTeams';
  const sources=document.querySelector('.sources');
  const teamPills=[...document.querySelectorAll('.sources .pill')];
  let selectedTeams=new Set();
  try{
    const saved=JSON.parse(localStorage.getItem(teamFilterKey)||'[]');
    if(Array.isArray(saved)) selectedTeams=new Set(saved);
  }catch(e){}

  const trackedNames=new Set(teamPills.map(p=>p.querySelector('b')?.textContent.trim()).filter(Boolean));

  function matchTrackedTeams(match){
    return [...match.querySelectorAll('.team-name')]
      .map(el=>el.textContent.trim())
      .filter(name=>trackedNames.has(name));
  }

  function ensureFilterEmpty(panel,kind){
    let el=panel.querySelector(':scope > .filter-empty');
    if(!el){
      el=document.createElement('section');
      el.className='filter-empty';
      el.textContent=kind==='results'?'Для выбранных команд результатов в этом окне нет.':'Для выбранных команд ближайших матчей нет.';
      panel.appendChild(el);
    }
    return el;
  }

  function updateVisibleCounts(){
    ['upcoming','results'].forEach(kind=>{
      const panel=document.querySelector('.view-panel.'+kind);
      if(!panel) return;
      const visible=[...panel.querySelectorAll('.match')].filter(m=>!m.hidden).length;
      const counter=document.querySelector('.view-tab[data-view="'+kind+'"] .view-count');
      if(counter) counter.textContent=String(visible);
      ensureFilterEmpty(panel,kind).style.display=visible?'none':'block';
    });
  }

  function applyTeamFilter(){
    const filtering=selectedTeams.size>0;
    sources?.classList.toggle('has-team-filter',filtering);

    teamPills.forEach(pill=>{
      const name=pill.querySelector('b')?.textContent.trim()||'';
      const selected=selectedTeams.has(name);
      pill.classList.toggle('filter-selected',selected);
      pill.setAttribute('aria-pressed',selected?'true':'false');
    });

    document.querySelectorAll('.match').forEach(match=>{
      const teams=matchTrackedTeams(match);
      match.hidden=filtering && !teams.some(name=>selectedTeams.has(name));
    });

    document.querySelectorAll('.day').forEach(day=>{
      day.hidden=![...day.querySelectorAll('.match')].some(match=>!match.hidden);
    });

    updateVisibleCounts();
  }

  function toggleTeam(pill){
    const name=pill.querySelector('b')?.textContent.trim();
    if(!name) return;
    if(selectedTeams.has(name)) selectedTeams.delete(name); else selectedTeams.add(name);
    try{localStorage.setItem(teamFilterKey,JSON.stringify([...selectedTeams]));}catch(e){}
    applyTeamFilter();
  }

  teamPills.forEach(pill=>{
    pill.setAttribute('role','button');
    pill.setAttribute('tabindex','0');
    pill.setAttribute('title','Фильтр по команде');
    pill.addEventListener('click',()=>toggleTeam(pill));
    pill.addEventListener('keydown',event=>{
      if(event.key==='Enter'||event.key===' '){event.preventDefault();toggleTeam(pill);}
    });
  });

  applyTeamFilter();
'''
    marker = "  if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js');"
    page = page.replace(marker, extra_js + "\n" + marker, 1)
    return page


core.render_page = render_page_v10
app = core.app
