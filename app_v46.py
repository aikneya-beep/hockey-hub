from __future__ import annotations

import app_v45
import app_v05 as core
import personal_hockey_v46  # patches the existing /my-hockey renderer

core.app.version = "0.46.0"

app = core.app
