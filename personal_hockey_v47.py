from __future__ import annotations

import personal_hockey_v46  # noqa: F401 - applies v0.46 renderer first
import personal_hockey_v42 as base


_previous_renderer = base.render_personal_page

SOYUZ_ACCENT_CSS = r'''
:root{
  --soyuz-blue:#2a86d9;
  --soyuz-blue-muted:#365c7d;
  --soyuz-blue-soft:rgba(42,134,217,.16);
  --soyuz-silver:#c8d0da;
}
body{
  background:
    radial-gradient(circle at 82% 6%,rgba(42,134,217,.105),transparent 25%),
    radial-gradient(circle at 8% 72%,rgba(54,92,125,.045),transparent 22%),
    linear-gradient(180deg,#05070b,#080b0f 58%,#05070b);
}

/* Tabs: black first, thin Soyuz-blue seam second. */
.mine-tabs a{position:relative;overflow:hidden;transition:border-color .16s ease,color .16s ease,background .16s ease}
.mine-tabs a:hover{border-color:#354b61;color:#c8d3df}
.mine-tabs a.active{border-color:#596674;background:linear-gradient(180deg,#161c23,#0e1319);box-shadow:inset 0 1px rgba(255,255,255,.035)}
.mine-tabs a.active:after{content:"";position:absolute;left:10px;right:10px;bottom:0;height:2px;background:var(--soyuz-blue);box-shadow:0 0 10px rgba(42,134,217,.32)}

/* Metric cards: silver/black remains dominant; blue appears as a short equipment-like insert. */
.stat{position:relative;overflow:hidden}
.stat:before{content:"";position:absolute;left:16px;top:0;width:14%;height:2px;background:linear-gradient(90deg,var(--soyuz-blue),var(--soyuz-blue-muted));opacity:.7;box-shadow:0 0 9px var(--soyuz-blue-soft)}
.stat:nth-child(2):before{width:19%;opacity:1}
.stat:nth-child(3):before{width:10%;opacity:.58}

/* Progress is the clearest functional home for blue. */
.chart-wrap{position:relative;box-shadow:inset 0 1px rgba(42,134,217,.06)}
.chart-wrap .hub-section-head .hub-eyebrow{color:#4e91cb}
.chart-wrap .line{stroke:var(--soyuz-blue)!important;stroke-width:2.35!important}
.chart-wrap .point{fill:var(--soyuz-silver)!important;stroke:var(--soyuz-blue)!important;stroke-width:2.4!important}
.chart-wrap .value{fill:#f2f5f8!important}

/* Technical markers on personal feedback cards. */
.latest .hub-section-head h2:before,.side-stack>.panel:last-child .hub-section-head h2:before{content:"";display:inline-block;width:12px;height:2px;background:var(--soyuz-blue);vertical-align:middle;margin-right:8px;box-shadow:0 0 7px var(--soyuz-blue-soft)}
.latest-date,.coach-row time{color:#557fa7!important}
.latest-meta{color:#6b9ac3!important}

/* Add-session keeps its silver action button, with blue only in interaction states. */
details.add-session{transition:border-color .16s ease,box-shadow .16s ease}
details.add-session:hover,details.add-session[open]{border-color:#36566f;box-shadow:inset 0 1px rgba(42,134,217,.06)}
details.add-session summary:after{color:var(--soyuz-blue)!important;text-shadow:0 0 8px var(--soyuz-blue-soft)}
input:focus,textarea:focus,select:focus{outline:none;border-color:var(--soyuz-blue-muted);box-shadow:0 0 0 2px rgba(42,134,217,.11)}
button.save{box-shadow:inset 0 -2px rgba(42,134,217,.12)}
button.save:hover{border-color:#9ba8b6;box-shadow:inset 0 -2px rgba(42,134,217,.23),0 0 14px rgba(42,134,217,.07)}

/* Training history: restrained blue tick, brightest on the latest record. */
.history-row{position:relative;padding-left:10px}
.history-row:before{content:"";position:absolute;left:0;top:13px;width:2px;height:18px;background:var(--soyuz-blue-muted);opacity:.38}
.history-row:first-of-type:before{background:var(--soyuz-blue);opacity:.95;box-shadow:0 0 7px var(--soyuz-blue-soft)}
.history-row em{color:#5f8db7!important}

/* Ecosystem: Tema = mostly silver, Closet = strongest Soyuz cue, Memory = quiet silver. */
.ecosystem-card:before{background:linear-gradient(#bfc7d0,#4a6175)!important}
#tema:before{background:linear-gradient(#c8d0da,#536b82)!important}
#closet{border-color:#29465d;box-shadow:inset 0 1px rgba(42,134,217,.055)}
#closet:before{width:3px;background:linear-gradient(var(--soyuz-blue),#315f86)!important;box-shadow:0 0 10px var(--soyuz-blue-soft)}
#closet:after{content:"";position:absolute;right:-8px;top:16px;width:54px;height:2px;background:linear-gradient(90deg,transparent,var(--soyuz-blue),transparent);transform:rotate(-34deg);opacity:.75}
#closet .badge{color:#78a9d2;border-color:#315674;background:rgba(42,134,217,.035)}
#closet h3{color:#e9edf2}
#memory:before{background:linear-gradient(#bfc7d0,#65717e)!important}

.footer-note span:last-child{color:#657c91}

@media(max-width:760px){
  .mine-tabs a.active:after{left:8px;right:8px}
  .stat:before{left:14px}
}
'''


def render_personal_page_v47(saved: bool = False, error: str | None = None) -> str:
    page = _previous_renderer(saved=saved, error=error)
    page = page.replace("Личный хоккей · v0.46", "Личный хоккей · v0.47", 1)
    page = page.replace("</style>", SOYUZ_ACCENT_CSS + "\n</style>", 1)
    return page


base.render_personal_page = render_personal_page_v47
