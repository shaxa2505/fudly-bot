"""Tests for keyboard modules."""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup


class TestUserKeyboards:
    """Test user keyboard functions."""

    def test_main_menu_customer_russian(self) -> None:
        """Test main menu keyboard for Russian."""
        from app.keyboards.user import main_menu_customer

        keyboard = main_menu_customer("ru")

        assert isinstance(keyboard, ReplyKeyboardMarkup)
        assert keyboard.resize_keyboard is True
        assert len(keyboard.keyboard) > 0

    def test_main_menu_customer_uzbek(self) -> None:
        """Test main menu keyboard for Uzbek."""
        from app.keyboards.user import main_menu_customer

        keyboard = main_menu_customer("uz")

        assert isinstance(keyboard, ReplyKeyboardMarkup)
        assert len(keyboard.keyboard) > 0

    def test_search_cancel_keyboard(self) -> None:
        """Test search cancel keyboard."""
        from app.keyboards.user import search_cancel_keyboard

        keyboard = search_cancel_keyboard("ru")

        assert isinstance(keyboard, ReplyKeyboardMarkup)
        assert len(keyboard.keyboard) == 1

    def test_settings_keyboard_customer(self) -> None:
        """Test settings keyboard for customer."""
        from app.keyboards.user import settings_keyboard

        keyboard = settings_keyboard(
            notifications_enabled=True, lang="ru", role="customer", current_mode="customer"
        )

        assert isinstance(keyboard, InlineKeyboardMarkup)
        assert len(keyboard.inline_keyboard) > 0

    def test_settings_keyboard_seller_mode(self) -> None:
        """Test settings keyboard for seller in seller mode."""
        from app.keyboards.user import settings_keyboard

        keyboard = settings_keyboard(
            notifications_enabled=False, lang="ru", role="seller", current_mode="seller"
        )

        assert isinstance(keyboard, InlineKeyboardMarkup)
        # Should have switch to customer button
        buttons = [btn.text for row in keyboard.inline_keyboard for btn in row]
        assert any("покупателя" in btn.lower() or "xaridor" in btn.lower() for btn in buttons)

    def test_settings_keyboard_seller_customer_mode(self) -> None:
        """Test settings keyboard for seller in customer mode."""
        from app.keyboards.user import settings_keyboard

        keyboard = settings_keyboard(
            notifications_enabled=True, lang="uz", role="seller", current_mode="customer"
        )

        assert isinstance(keyboard, InlineKeyboardMarkup)
        # Should have switch to seller button
        buttons = [btn.text for row in keyboard.inline_keyboard for btn in row]
        assert any("hamkor" in btn.lower() or "партнера" in btn.lower() for btn in buttons)


class TestMainMenuSeller:
    """Test seller menu keyboards."""

    def test_main_menu_seller_russian(self) -> None:
        """Test main menu for seller in Russian."""
        from app.keyboards.seller import main_menu_seller

        keyboard = main_menu_seller("ru")

        assert isinstance(keyboard, ReplyKeyboardMarkup)
        assert keyboard.resize_keyboard is True

    def test_main_menu_seller_uzbek(self) -> None:
        """Test main menu for seller in Uzbek."""
        from app.keyboards.seller import main_menu_seller

        keyboard = main_menu_seller("uz")

        assert isinstance(keyboard, ReplyKeyboardMarkup)


class TestCommonKeyboards:
    """Test common keyboard functions."""

    def test_language_keyboard(self) -> None:
        """Test language selection keyboard."""
        from app.keyboards.common import language_keyboard

        keyboard = language_keyboard()

        assert isinstance(keyboard, InlineKeyboardMarkup)
        # Should have 2 language options
        buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        assert len(buttons) >= 2

    def test_cancel_keyboard_russian(self) -> None:
        """Test cancel keyboard in Russian."""
        from app.keyboards.common import cancel_keyboard

        keyboard = cancel_keyboard("ru")

        assert isinstance(keyboard, ReplyKeyboardMarkup)
        # Should have cancel button
        texts = [btn.text for row in keyboard.keyboard for btn in row]
        assert any("отмена" in t.lower() for t in texts)

    def test_cancel_keyboard_uzbek(self) -> None:
        """Test cancel keyboard in Uzbek."""
        from app.keyboards.common import cancel_keyboard

        keyboard = cancel_keyboard("uz")

        assert isinstance(keyboard, ReplyKeyboardMarkup)

    def test_phone_request_keyboard(self) -> None:
        """Test phone request keyboard."""
        from app.keyboards.common import phone_request_keyboard

        keyboard = phone_request_keyboard("ru")

        assert isinstance(keyboard, ReplyKeyboardMarkup)
        # Should have contact request button
        buttons = [btn for row in keyboard.keyboard for btn in row]
        assert any(getattr(btn, "request_contact", False) for btn in buttons)


class TestOfferKeyboards:
    """Test offer-related keyboards."""

    def test_hot_offers_pagination_keyboard(self) -> None:
        """Test hot offers pagination keyboard."""
        from app.keyboards.offers import hot_offers_pagination_keyboard

        keyboard = hot_offers_pagination_keyboard(lang="ru", has_more=True, next_offset=10)

        assert keyboard is None or isinstance(keyboard, InlineKeyboardMarkup)

    def test_store_card_keyboard(self) -> None:
        """Test store card keyboard."""
        from app.keyboards.offers import store_card_keyboard

        keyboard = store_card_keyboard(lang="ru", store_id=123, offers_count=5, ratings_count=10)

        assert isinstance(keyboard, InlineKeyboardMarkup)

    def test_offer_details_keyboard(self) -> None:
        """Test offer details keyboard."""
        from app.keyboards.offers import offer_details_keyboard

        keyboard = offer_details_keyboard(
            lang="ru", offer_id=456, store_id=789, delivery_enabled=True
        )

        assert isinstance(keyboard, InlineKeyboardMarkup)
        buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        # Should have book button
        assert any("book" in (btn.callback_data or "") for btn in buttons)


class TestAdminKeyboards:
    """Test admin keyboard functions."""

    def test_admin_menu(self) -> None:
        """Test admin menu keyboard."""
        from app.keyboards.admin import admin_menu

        keyboard = admin_menu("ru")

        assert isinstance(keyboard, ReplyKeyboardMarkup)
        assert keyboard.resize_keyboard is True

    def test_admin_users_keyboard(self) -> None:
        """Test admin users keyboard."""
        from app.keyboards.admin import admin_users_keyboard

        keyboard = admin_users_keyboard()

        assert isinstance(keyboard, InlineKeyboardMarkup)

    def test_admin_stores_keyboard(self) -> None:
        """Test admin stores keyboard."""
        from app.keyboards.admin import admin_stores_keyboard

        keyboard = admin_stores_keyboard(pending=5)

        assert isinstance(keyboard, InlineKeyboardMarkup)
        buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        # Should have moderation button with count
        texts = [btn.text for btn in buttons]
        assert any("5" in t for t in texts)


class TestSellerKeyboards:
    """Test seller keyboard functions."""

    def test_offer_manage_keyboard(self) -> None:
        """Test offer manage keyboard."""
        from app.keyboards.seller import offer_manage_keyboard

        keyboard = offer_manage_keyboard(offer_id=789, lang="ru")

        assert isinstance(keyboard, InlineKeyboardMarkup)

    def test_moderation_keyboard(self) -> None:
        """Test moderation keyboard."""
        from app.keyboards.seller import moderation_keyboard

        keyboard = moderation_keyboard(store_id=123)

        assert isinstance(keyboard, InlineKeyboardMarkup)
        buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        # Should have approve and reject buttons
        callback_data = [btn.callback_data or "" for btn in buttons]
        assert any("approve" in cd for cd in callback_data)
        assert any("reject" in cd for cd in callback_data)


class TestInlineKeyboards:
    """Test inline keyboard helpers."""

    def test_offer_keyboard(self) -> None:
        """Test offer keyboard."""
        from app.keyboards.inline import offer_keyboard

        keyboard = offer_keyboard(offer_id=123, lang="ru")

        assert isinstance(keyboard, InlineKeyboardMarkup)
        buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        callback_data = [btn.callback_data or "" for btn in buttons]
        assert any("book" in cd for cd in callback_data)

    def test_filters_keyboard(self) -> None:
        """Test filters keyboard."""
        from app.keyboards.inline import filters_keyboard

        keyboard = filters_keyboard(lang="ru")

        assert isinstance(keyboard, InlineKeyboardMarkup)
        buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        assert len(buttons) >= 3

    def test_rating_filter_keyboard(self) -> None:
        """Test rating filter keyboard."""
        from app.keyboards.inline import rating_filter_keyboard

        keyboard = rating_filter_keyboard()

        assert isinstance(keyboard, InlineKeyboardMarkup)
        buttons = [btn for row in keyboard.inline_keyboard for btn in row]
        assert len(buttons) >= 4
