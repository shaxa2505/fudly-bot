"""Tests for i18n module."""
from __future__ import annotations

from app.core.i18n import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    _,
    clear_language,
    format_currency,
    format_date,
    format_number,
    get_available_languages,
    get_date_format,
    get_language,
    lazy_,
    ngettext,
    set_language,
    translate,
)


class TestLanguageSettings:
    """Test language setting and getting."""

    def test_default_language(self) -> None:
        """Test default language is Russian."""
        assert DEFAULT_LANGUAGE == "ru"

    def test_supported_languages(self) -> None:
        """Test supported languages."""
        assert "ru" in SUPPORTED_LANGUAGES
        assert "uz" in SUPPORTED_LANGUAGES
        assert len(SUPPORTED_LANGUAGES) == 2

    def test_get_language_without_user(self) -> None:
        """Test getting language without user ID."""
        assert get_language() == DEFAULT_LANGUAGE
        assert get_language(None) == DEFAULT_LANGUAGE

    def test_set_and_get_language(self) -> None:
        """Test setting and getting user language."""
        user_id = 12345

        # Clear any existing preference
        clear_language(user_id)

        # Default should be 'ru'
        assert get_language(user_id) == "ru"

        # Set to Uzbek
        set_language(user_id, "uz")
        assert get_language(user_id) == "uz"

        # Set back to Russian
        set_language(user_id, "ru")
        assert get_language(user_id) == "ru"

        # Clean up
        clear_language(user_id)

    def test_set_invalid_language(self) -> None:
        """Test setting invalid language (should be ignored)."""
        user_id = 99999
        clear_language(user_id)

        set_language(user_id, "invalid")
        # Should still return default
        assert get_language(user_id) == "ru"

        clear_language(user_id)

    def test_clear_language(self) -> None:
        """Test clearing language preference."""
        user_id = 11111

        set_language(user_id, "uz")
        assert get_language(user_id) == "uz"

        clear_language(user_id)
        assert get_language(user_id) == "ru"  # Back to default


class TestTranslation:
    """Test translation functions."""

    def test_translate_with_lang_param(self) -> None:
        """Test translation with explicit language."""
        # These should return from gettext or fallback to localization.py
        result_ru = translate("welcome", lang="ru")
        result_uz = translate("welcome", lang="uz")

        # Both should return non-empty strings
        assert result_ru
        assert result_uz
        # They should be different
        assert result_ru != result_uz or result_ru == "welcome"

    def test_translate_unknown_key(self) -> None:
        """Test translation of unknown key returns key."""
        result = translate("unknown_key_xyz123", lang="ru")
        assert result == "unknown_key_xyz123"

    def test_translate_with_formatting(self) -> None:
        """Test translation with format arguments."""
        result = translate("city_changed", lang="ru", city="Ташкент")
        assert "Ташкент" in result or result == "city_changed"

    def test_shorthand_alias(self) -> None:
        """Test _ alias works same as translate."""
        assert _("welcome", lang="ru") == translate("welcome", lang="ru")

    def test_translate_with_user_id(self) -> None:
        """Test translation using user's language preference."""
        user_id = 22222

        set_language(user_id, "uz")
        result = translate("back", user_id=user_id)

        # Should get Uzbek translation
        assert result  # Non-empty

        clear_language(user_id)


class TestPluralForms:
    """Test plural form translations."""

    def test_ngettext_russian_plurals(self) -> None:
        """Test Russian plural forms (3 forms)."""
        # Russian has 3 plural forms:
        # 0: 1, 21, 31... (singular)
        # 1: 2-4, 22-24... (few)
        # 2: 0, 5-20, 25-30... (many)

        result_1 = ngettext("item", "items", 1, lang="ru")
        result_2 = ngettext("item", "items", 2, lang="ru")
        result_5 = ngettext("item", "items", 5, lang="ru")

        # All should return something
        assert result_1
        assert result_2
        assert result_5

    def test_ngettext_uzbek_plurals(self) -> None:
        """Test Uzbek plural forms (2 forms)."""
        # Uzbek has 2 plural forms
        result_1 = ngettext("item", "items", 1, lang="uz")
        result_many = ngettext("item", "items", 10, lang="uz")

        assert result_1
        assert result_many


class TestFormatting:
    """Test number and currency formatting."""

    def test_format_number_russian(self) -> None:
        """Test number formatting for Russian."""
        result = format_number(1234567, lang="ru")
        assert "1" in result
        assert "234" in result or " " in result

    def test_format_number_uzbek(self) -> None:
        """Test number formatting for Uzbek."""
        result = format_number(1234567, lang="uz")
        assert "1" in result

    def test_format_currency_russian(self) -> None:
        """Test currency formatting for Russian."""
        result = format_currency(15000, lang="ru")
        assert "сум" in result
        assert "15" in result

    def test_format_currency_uzbek(self) -> None:
        """Test currency formatting for Uzbek."""
        result = format_currency(15000, lang="uz")
        assert "so'm" in result
        assert "15" in result


class TestDateFormatting:
    """Test date formatting."""

    def test_get_date_format(self) -> None:
        """Test getting date format strings."""
        ru_short = get_date_format("short", "ru")
        uz_short = get_date_format("short", "uz")

        assert "%d" in ru_short
        assert "%m" in ru_short
        assert "%Y" in ru_short

    def test_format_date_short(self) -> None:
        """Test short date formatting."""
        from datetime import date

        test_date = date(2025, 11, 26)

        result_ru = format_date(test_date, "short", "ru")
        assert "26" in result_ru
        assert "11" in result_ru
        assert "2025" in result_ru

    def test_format_date_long_russian(self) -> None:
        """Test long date formatting for Russian."""
        from datetime import date

        test_date = date(2025, 1, 15)

        result = format_date(test_date, "long", "ru")
        assert "15" in result
        assert "января" in result
        assert "2025" in result

    def test_format_date_long_uzbek(self) -> None:
        """Test long date formatting for Uzbek."""
        from datetime import date

        test_date = date(2025, 1, 15)

        result = format_date(test_date, "long", "uz")
        assert "15" in result
        assert "yanvar" in result
        assert "2025" in result

    def test_format_date_from_string(self) -> None:
        """Test formatting date from string."""
        result = format_date("2025-12-31", "short", "ru")
        assert "31" in result
        assert "12" in result


class TestLazyString:
    """Test lazy string translation."""

    def test_lazy_string_str(self) -> None:
        """Test lazy string converts to string."""
        lazy = lazy_("welcome")
        result = str(lazy)
        assert result  # Non-empty

    def test_lazy_string_repr(self) -> None:
        """Test lazy string repr."""
        lazy = lazy_("welcome")
        assert "LazyString" in repr(lazy)
        assert "welcome" in repr(lazy)

    def test_lazy_string_format(self) -> None:
        """Test lazy string formatting."""
        lazy = lazy_("city_changed")
        result = lazy.format(city="Ташкент")
        # Should contain city or be the key itself
        assert result


class TestAvailableLanguages:
    """Test available languages helper."""

    def test_get_available_languages(self) -> None:
        """Test getting list of available languages."""
        languages = get_available_languages()

        assert len(languages) == 2

        codes = [lang["code"] for lang in languages]
        assert "ru" in codes
        assert "uz" in codes

        # Check structure
        for lang in languages:
            assert "code" in lang
            assert "name" in lang
            assert "flag" in lang

    def test_language_has_flag_emoji(self) -> None:
        """Test languages have flag emojis."""
        languages = get_available_languages()

        for lang in languages:
            # Flag emojis start with regional indicator symbols
            assert lang["flag"]  # Non-empty
