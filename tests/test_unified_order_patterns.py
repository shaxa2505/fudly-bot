"""Tests for unified order customer callback patterns.

These tests ensure that the public regex patterns used for
customer "✅ Получил" buttons actually match simple ids and
reject invalid data. This helps catch accidental double-escaping
or typos in callback patterns.
"""
from __future__ import annotations

import re

from handlers.common.unified_order import customer


def test_customer_received_pattern_matches_valid_id() -> None:
    pattern = re.compile(customer.CUSTOMER_RECEIVED_PATTERN)
    assert pattern.match("customer_received_123") is not None


def test_customer_received_pattern_rejects_invalid() -> None:
    pattern = re.compile(customer.CUSTOMER_RECEIVED_PATTERN)
    assert pattern.match("customer_received_123_extra") is None
    assert pattern.match("customer_received_") is None
    assert pattern.match("customer_received_abc") is None


