from __future__ import annotations

import app_v51  # load v0.51 cleanup first
import app_v05 as core
import home_v44


_previous_big = home_v44.render_big_hockey_v44


def render_big_v511() -> str:
    page = _previous_big()
    css = r"""
/* v0.51.1: Big Hockey owns the red -> ultramarine active underline. */
.hub-nav a.active:after{
  background:linear-gradient(90deg,#e51d3e,#315cff)!important;
  box-shadow:0 0 10px rgba(49,92,255,.08);
}
"""
    page = page.replace("</style>", css + "\n</style>", 1)
    return page.replace("v0.51", "v0.51.1", 1)


home_v44.render_big_hockey_v44 = render_big_v511
core.app.version = "0.51.1"

app = core.app
