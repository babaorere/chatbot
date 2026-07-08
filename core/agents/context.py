from __future__ import annotations

import contextvars

current_session_id_var = contextvars.ContextVar("current_session_id", default=None)
