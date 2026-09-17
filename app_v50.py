from __future__ import annotations

import app_v49
import app_v05 as core
import environment_v50  # registers /my-hockey/environment and patches private navigation

core.app.version = "0.50.0"

app = core.app
