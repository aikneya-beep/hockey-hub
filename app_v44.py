from __future__ import annotations

import app_v43
import app_v05 as core
import home_v44

core.app.version = "0.44.0"
core.render_page = home_v44.render_home_v44
home_v44.register_routes(core.app)

app = core.app
