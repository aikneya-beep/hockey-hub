from __future__ import annotations

import app_v48  # noqa: F401 - load v0.48 routes and renderers first
import app_v05 as core
import personal_hockey_v42 as personal_base
import closet_v48


_previous_personal_renderer = personal_base.render_personal_page
_previous_closet_renderer = closet_v48.render_closet

PERSONAL_CLEANUP_CSS = r'''
/* v0.48.1: the closet teaser keeps the Soyuz cue without crossing content. */
#closet:after{content:none!important;display:none!important}
#closet{position:relative}
#closet:before{
  width:3px!important;
  background:linear-gradient(var(--soyuz-blue),#315f86)!important;
  box-shadow:0 0 9px var(--soyuz-blue-soft)!important;
}
'''

CLOSET_CLEANUP_CSS = r'''
/* v0.48.1: no diagonal ornament on content-heavy gear cards. */
.gear-card:after{content:none!important;display:none!important}
.gear-card:before{
  content:"";
  position:absolute;
  left:14px;
  top:0;
  width:42px;
  height:2px;
  background:linear-gradient(90deg,var(--soyuz),var(--soyuz-dim));
  opacity:.68;
  box-shadow:0 0 8px rgba(42,134,217,.11);
}
.gear-card.attention:before{opacity:.9}
.gear-card.fresh:before{opacity:.5}
'''


def render_personal_page_v481(saved: bool = False, error: str | None = None) -> str:
    page = _previous_personal_renderer(saved=saved, error=error)
    page = page.replace("Личный хоккей · v0.47", "Личный хоккей · v0.48.1", 1)
    page = page.replace("</style>", PERSONAL_CLEANUP_CSS + "\n</style>", 1)
    return page


def render_closet_v481(saved: str | None = None, error: str | None = None) -> str:
    page = _previous_closet_renderer(saved=saved, error=error)
    page = page.replace("Мой хоккей · v0.48", "Мой хоккей · v0.48.1", 1)
    page = page.replace("</style>", CLOSET_CLEANUP_CSS + "\n</style>", 1)
    return page


personal_base.render_personal_page = render_personal_page_v481
closet_v48.render_closet = render_closet_v481

core.app.version = "0.48.1"
