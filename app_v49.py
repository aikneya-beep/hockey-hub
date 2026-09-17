from __future__ import annotations

import app_v481
import app_v05 as core
import auth_v49  # registers login/setup/logout routes and private-area middleware

core.app.version = "0.49.0"

app = core.app
