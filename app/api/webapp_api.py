"""Compatibility wrapper for legacy webapp API module.

Historically, all Mini App REST endpoints lived in this file.
To reduce the size and responsibility of a single monolithic
module, the implementation has been moved to the structured
package :mod:`app.api.webapp`.

This module now simply re-exports the public FastAPI router and
database binding helper used by the rest of the application.
"""
from __future__ import annotations

from app.api.webapp import router, set_db_instance

__all__ = ["router", "set_db_instance"]
