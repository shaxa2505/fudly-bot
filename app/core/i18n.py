"""
Internationalization (i18n) module for Fudly Bot.

Provides gettext-based translations with fallback to dictionary-based system.
Supports Russian (ru) and Uzbek (uz) languages.

Usage:
    from app.core.i18n import _, set_language, get_language

    # Set user's language
    set_language(user_id, 'uz')

    # Get translated string
    message = _('welcome', user_id)  # or _('welcome', lang='uz')

    # With formatting
    message = _('hello_user', user_id, name='John')
"""
from __future__ import annotations

import gettext
from functools import lru_cache
from pathlib import Path
from typing import Any

# User language preferences storage
_user_languages: dict[int, str] = {}

# Default language
DEFAULT_LANGUAGE = "ru"

# Supported languages
SUPPORTED_LANGUAGES = ("ru", "uz")

# Locale directory
LOCALE_DIR = Path(__file__).parent.parent.parent / "locales"


_MOJIBAKE_MARKERS = ("рџ", "вЂ", "Ð", "Ñ")
_MOJIBAKE_FOLLOWUP_CHARS = set(
    "°±²³´µ¶·ё№є»јЅѕїЃѓ‚„…†‡€‰Љ‹ЊЋЏђ‘’“”•–—™љ›њќћџЎўЈ¤Ґ¦§Ё©Є«¬®Ї"
)


def _looks_like_mojibake(text: str) -> bool:
    if any(marker in text for marker in _MOJIBAKE_MARKERS):
        return True
    for idx in range(len(text) - 1):
        if text[idx] in {"Р", "С"} and text[idx + 1] in _MOJIBAKE_FOLLOWUP_CHARS:
            return True
    return False


def _fix_mojibake_text(text: str) -> str:
    if not text:
        return text

    current = text
    for _ in range(3):
        if not _looks_like_mojibake(current):
            break
        fixed = None
        for encoding in ("cp1251", "cp1252", "latin1", "cp866"):
            try:
                candidate = current.encode(encoding).decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            if candidate and candidate != current:
                fixed = candidate
                break
        if fixed is None:
            fixed = _decode_utf8_from_mixed_cp1251(current)
        if fixed is None:
            break
        current = fixed
    return current


def _decode_utf8_from_mixed_cp1251(text: str) -> str | None:
    raw = bytearray()
    for ch in text:
        code = ord(ch)
        if code <= 0xFF:
            raw.append(code)
            continue
        try:
            raw.extend(ch.encode("cp1251"))
        except UnicodeEncodeError:
            return None
    try:
        candidate = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if not candidate or candidate == text:
        return None
    return candidate


def _normalize_mojibake(value: Any) -> Any:
    if isinstance(value, str):
        return _fix_mojibake_text(value)
    if isinstance(value, dict):
        normalized: dict[Any, Any] = {}
        for k, v in value.items():
            key = _fix_mojibake_text(k) if isinstance(k, str) else k
            normalized[key] = _normalize_mojibake(v)
        return normalized
    if isinstance(value, list):
        return [_normalize_mojibake(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_normalize_mojibake(v) for v in value)
    return value


def get_language(user_id: int | None = None) -> str:
    """Get language for user or default."""
    if user_id is None:
        return DEFAULT_LANGUAGE
    return _user_languages.get(user_id, DEFAULT_LANGUAGE)


def set_language(user_id: int, language: str) -> None:
    """Set language for user."""
    if language in SUPPORTED_LANGUAGES:
        _user_languages[user_id] = language


def clear_language(user_id: int) -> None:
    """Clear language preference for user."""
    _user_languages.pop(user_id, None)


@lru_cache(maxsize=10)
def _get_translator(language: str) -> gettext.GNUTranslations | gettext.NullTranslations:
    """Get cached translator for language."""
    try:
        return gettext.translation(
            "messages", localedir=str(LOCALE_DIR), languages=[language], fallback=True
        )
    except Exception:
        return gettext.NullTranslations()


def translate(key: str, user_id: int | None = None, lang: str | None = None, **kwargs: Any) -> str:
    """
    Translate a message key to the appropriate language.

    Args:
        key: Translation key or message string
        user_id: Optional user ID to get their language preference
        lang: Optional explicit language code ('ru' or 'uz')
        **kwargs: Formatting arguments for the translated string

    Returns:
        Translated and formatted string
    """
    # Determine language
    language = lang or get_language(user_id)
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE

    # Try gettext first
    translator = _get_translator(language)
    translated = _fix_mojibake_text(translator.gettext(key))

    # If gettext didn't find translation (returned same key),
    # fall back to dictionary-based localization
    if translated == key:
        try:
            from localization import get_text

            translated = _fix_mojibake_text(get_text(language, key))
        except (ImportError, KeyError):
            pass

    # Format if kwargs provided
    if kwargs and translated:
        try:
            translated = translated.format(**kwargs)
        except (KeyError, ValueError):
            pass

    return _fix_mojibake_text(translated or key)


# Shorthand alias
_ = translate


def ngettext(
    singular: str,
    plural: str,
    n: int,
    user_id: int | None = None,
    lang: str | None = None,
    **kwargs: Any,
) -> str:
    """
    Translate with plural forms.

    Args:
        singular: Singular form of the message
        plural: Plural form of the message
        n: Number to determine which form to use
        user_id: Optional user ID
        lang: Optional explicit language code
        **kwargs: Formatting arguments

    Returns:
        Translated string with correct plural form
    """
    language = lang or get_language(user_id)
    translator = _get_translator(language)

    translated = _fix_mojibake_text(translator.ngettext(singular, plural, n))

    if kwargs:
        kwargs["n"] = n
        try:
            translated = translated.format(**kwargs)
        except (KeyError, ValueError):
            pass

    return _fix_mojibake_text(translated)


def get_available_languages() -> list[dict[str, str]]:
    """Get list of available languages with their names."""
    return _normalize_mojibake([
        {"code": "ru", "name": "Русский", "flag": "🇷🇺"},
        {"code": "uz", "name": "O'zbek", "flag": "🇺🇿"},
    ])


def format_number(n: int | float, lang: str | None = None) -> str:
    """Format number according to locale."""
    if lang == "uz":
        # Uzbek uses space as thousands separator
        return f"{n:,}".replace(",", " ")
    else:
        # Russian uses space as thousands separator
        return f"{n:,}".replace(",", " ")


def format_currency(amount: int | float, lang: str | None = None) -> str:
    """Format currency amount."""
    formatted = format_number(amount, lang)
    if lang == "uz":
        return f"{formatted} so'm"
    else:
        return _fix_mojibake_text(f"{formatted} сум")


class LazyString:
    """
    Lazy string that translates on access.
    Useful for module-level constants that need translation.
    """

    def __init__(self, key: str, **kwargs: Any):
        self.key = key
        self.kwargs = kwargs

    def __str__(self) -> str:
        return translate(self.key, **self.kwargs)

    def __repr__(self) -> str:
        return f"LazyString({self.key!r})"

    def format(self, **kwargs: Any) -> str:
        merged = {**self.kwargs, **kwargs}
        return translate(self.key, **merged)


def lazy_(key: str, **kwargs: Any) -> LazyString:
    """Create a lazy translated string."""
    return LazyString(key, **kwargs)


# Language-specific date/time formats
DATE_FORMATS = {
    "ru": {
        "short": "%d.%m.%Y",
        "long": "%d %B %Y г.",
        "time": "%H:%M",
        "datetime": "%d.%m.%Y %H:%M",
    },
    "uz": {
        "short": "%d.%m.%Y",
        "long": "%d %B %Y y.",
        "time": "%H:%M",
        "datetime": "%d.%m.%Y %H:%M",
    },
}


def get_date_format(format_type: str = "short", lang: str | None = None) -> str:
    """Get date format string for language."""
    language = lang or DEFAULT_LANGUAGE
    return DATE_FORMATS.get(language, DATE_FORMATS["ru"]).get(format_type, "%Y-%m-%d")


# Month names for formatting
MONTH_NAMES = {
    "ru": [
        "",
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    ],
    "uz": [
        "",
        "yanvar",
        "fevral",
        "mart",
        "aprel",
        "may",
        "iyun",
        "iyul",
        "avgust",
        "sentyabr",
        "oktyabr",
        "noyabr",
        "dekabr",
    ],
}

# Normalize static locale constants once at import time.
DATE_FORMATS = _normalize_mojibake(DATE_FORMATS)
MONTH_NAMES = _normalize_mojibake(MONTH_NAMES)


def format_date(date, format_type: str = "short", lang: str | None = None) -> str:
    """Format date according to locale."""
    from datetime import datetime

    if isinstance(date, str):
        try:
            date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return date

    language = lang or DEFAULT_LANGUAGE

    if format_type == "long":
        month = MONTH_NAMES.get(language, MONTH_NAMES["ru"])[date.month]
        if language == "uz":
            return f"{date.day} {month} {date.year} y."
        else:
            return f"{date.day} {month} {date.year} г."

    fmt = get_date_format(format_type, language)
    return date.strftime(fmt)
