"""Security utilities for safe user input handling."""
from __future__ import annotations

import html
import re
from typing import Any


def escape_html(text: str | None) -> str:
    """Escape HTML special characters to prevent XSS attacks.

    Args:
        text: User input text to escape

    Returns:
        Escaped text safe for HTML output

    Example:
        >>> escape_html("<script>alert('xss')</script>")
        "&lt;script&gt;alert('xss')&lt;/script&gt;"
    """
    if text is None:
        return ""
    return html.escape(str(text), quote=True)


def sanitize_phone(phone: str | None) -> str:
    """Sanitize phone number - allow only digits, +, spaces, dashes.

    Args:
        phone: Phone number to sanitize

    Returns:
        Sanitized phone number

    Example:
        >>> sanitize_phone("+998 90 123-45-67")
        "+998 90 123-45-67"
        >>> sanitize_phone("+998<script>alert(1)</script>")
        "+998"
    """
    if not phone:
        return ""
    # Allow only digits, +, spaces, dashes, parentheses
    return re.sub(r"[^0-9+\-\s()]", "", str(phone))[:20]  # Max 20 chars


def sanitize_price(price: Any) -> int:
    """Sanitize price - ensure it's a valid positive integer.

    Args:
        price: Price value to sanitize

    Returns:
        Valid price as positive integer

    Raises:
        ValueError: If price is invalid
    """
    try:
        price_int = int(price)
        if price_int < 0:
            raise ValueError("Price cannot be negative")
        if price_int > 100_000_000:  # 100M max
            raise ValueError("Price too high")
        return price_int
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid price: {e}")


def sanitize_quantity(quantity: Any) -> int:
    """Sanitize quantity - ensure it's a valid positive integer.

    Args:
        quantity: Quantity value to sanitize

    Returns:
        Valid quantity as positive integer

    Raises:
        ValueError: If quantity is invalid
    """
    try:
        qty_int = int(quantity)
        if qty_int < 1:
            raise ValueError("Quantity must be at least 1")
        if qty_int > 10000:  # 10K max
            raise ValueError("Quantity too high")
        return qty_int
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid quantity: {e}")


def sanitize_text_input(text: str | None, max_length: int = 1000) -> str:
    """Sanitize general text input - remove dangerous content.

    Args:
        text: Text to sanitize
        max_length: Maximum allowed length

    Returns:
        Sanitized text safe for storage and display
    """
    if not text:
        return ""

    text = str(text).strip()

    # Remove null bytes and other control characters
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Limit length
    if len(text) > max_length:
        text = text[:max_length]

    return text


def format_user_data_for_display(
    name: str | None = None,
    description: str | None = None,
    address: str | None = None,
    **kwargs: Any,
) -> dict[str, str]:
    """Format user-provided data for safe HTML display.

    Escapes HTML and sanitizes all fields before display.

    Args:
        name: Store/product name
        description: Store/product description
        address: Store address
        **kwargs: Additional fields to sanitize

    Returns:
        Dictionary with escaped fields ready for HTML display
    """
    result = {}

    if name is not None:
        result["name"] = escape_html(sanitize_text_input(name, max_length=200))

    if description is not None:
        result["description"] = escape_html(sanitize_text_input(description, max_length=2000))

    if address is not None:
        result["address"] = escape_html(sanitize_text_input(address, max_length=500))

    for key, value in kwargs.items():
        if isinstance(value, str):
            result[key] = escape_html(sanitize_text_input(value))
        else:
            result[key] = escape_html(str(value))

    return result
