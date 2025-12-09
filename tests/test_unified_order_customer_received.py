"""Legacy placeholder module.

The original tests in this file directly invoked aiogram callback
handlers and tried to emulate Telegram updates, which made them
very brittle. The real behaviour of the "✅ Получил" buttons is now
covered more robustly by `tests/test_unified_order_patterns.py` and
service-level tests.

This file is kept intentionally empty (no tests) to avoid pytest
import errors while preserving history.
"""

