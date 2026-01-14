"""Tests for app/templates/ - text rendering for offers and admin dashboards."""
from __future__ import annotations

import pytest

from app.services.admin_service import BookingStats, OfferStats, StoreStats, UserStats
from app.services.offer_service import OfferDetails, OfferListItem, StoreDetails, StoreSummary
from app.templates.admin import (
    render_booking_stats,
    render_offer_stats,
    render_store_stats,
    render_user_stats,
)
from app.templates.offers import (
    render_business_type_store_list,
    render_hot_offers_empty,
    render_hot_offers_list,
    render_offer_card,
    render_offer_details,
    render_store_card,
    render_store_offers_list,
    render_store_reviews,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_offer_item() -> OfferListItem:
    """Create a sample OfferListItem for testing."""
    return OfferListItem(
        id=1,
        store_id=10,
        title="Хлеб белый",
        original_price=10000.0,
        discount_price=5000.0,
        discount_percent=50.0,
        store_name="Супермаркет Тест",
        store_address="ул. Пушкина 1",
        store_category="bakery",
        quantity=10,
        unit="шт",
        expiry_date="2025-12-31",
        delivery_enabled=True,
        delivery_price=5000.0,
        min_order_amount=20000.0,
    )


@pytest.fixture
def sample_offer_high_discount() -> OfferListItem:
    """Create a sample OfferListItem with high discount (70%+)."""
    return OfferListItem(
        id=2,
        store_id=10,
        title="Молоко 1л",
        original_price=20000.0,
        discount_price=6000.0,
        discount_percent=70.0,
        store_name="Молочный дом",
        store_address="ул. Лермонтова 5",
        store_category="dairy",
        quantity=5,
        unit="шт",
    )


@pytest.fixture
def sample_store_summary() -> StoreSummary:
    """Create a sample StoreSummary for testing."""
    return StoreSummary(
        id=10,
        name="Тестовый магазин",
        city="Ташкент",
        address="ул. Навои 10",
        business_type="supermarket",
        offers_count=15,
        rating=4.5,
        ratings_count=120,
    )


@pytest.fixture
def sample_store_details() -> StoreDetails:
    """Create a sample StoreDetails for testing."""
    return StoreDetails(
        id=10,
        name="Тестовый магазин",
        city="Ташкент",
        address="ул. Навои 10",
        business_type="supermarket",
        offers_count=15,
        rating=4.5,
        ratings_count=120,
        description="Лучший магазин в городе!",
        phone="+998901234567",
        delivery_enabled=True,
        delivery_price=10000.0,
        min_order_amount=50000.0,
    )


@pytest.fixture
def sample_offer_details() -> OfferDetails:
    """Create a sample OfferDetails for testing."""
    return OfferDetails(
        id=1,
        store_id=10,
        title="Хлеб белый",
        original_price=10000.0,
        discount_price=5000.0,
        discount_percent=50.0,
        store_name="Супермаркет Тест",
        store_address="ул. Пушкина 1",
        quantity=10,
        unit="шт",
        expiry_date="2025-12-31",
        description="Свежий белый хлеб",
        store_city="Ташкент",
    )


# =============================================================================
# Tests for render_hot_offers_list
# =============================================================================


class TestRenderHotOffersList:
    """Tests for render_hot_offers_list function."""

    def test_render_with_offers_ru(self, sample_offer_item: OfferListItem) -> None:
        """Test rendering hot offers list in Russian."""
        result = render_hot_offers_list(
            lang="ru",
            city="Ташкент",
            offers=[sample_offer_item],
            total_count=1,
            select_hint="Выберите товар",
            offset=0,
        )

        assert "Акции" in result
        assert "Город: Ташкент" in result
        assert "Хлеб белый" in result
        assert "Показано: 1 из 1" in result
        assert "Цена: 5 000 сум (-50%)" in result
        assert "Магазин: Супермаркет Тест" in result
        assert "Выберите товар" in result

    def test_render_with_offers_uz(self, sample_offer_item: OfferListItem) -> None:
        """Test rendering hot offers list in Uzbek."""
        result = render_hot_offers_list(
            lang="uz",
            city="Toshkent",
            offers=[sample_offer_item],
            total_count=1,
            select_hint="Mahsulotni tanlang",
            offset=0,
        )

        assert "Aksiyalar" in result
        assert "Shahar: Toshkent" in result
        assert "Ko'rsatilgan" in result
        assert "Narx: 5 000 so'm (-50%)" in result

    def test_render_with_offset(self, sample_offer_item: OfferListItem) -> None:
        """Test rendering with pagination offset."""
        result = render_hot_offers_list(
            lang="ru",
            city="Ташкент",
            offers=[sample_offer_item],
            total_count=10,
            select_hint="Выберите",
            offset=5,
        )

        assert "Показано: 6 из 10" in result

    def test_store_line_present(self, sample_offer_item: OfferListItem) -> None:
        """Test that store line is present in list."""
        result = render_hot_offers_list(
            lang="ru",
            city="Ташкент",
            offers=[sample_offer_item],
            total_count=1,
            select_hint="",
            offset=0,
        )

        assert "Магазин:" in result

    def test_high_discount_fire_emoji(self, sample_offer_high_discount: OfferListItem) -> None:
        """Test that high discounts show percent."""
        result = render_hot_offers_list(
            lang="ru",
            city="Ташкент",
            offers=[sample_offer_high_discount],
            total_count=1,
            select_hint="",
            offset=0,
        )

        assert "-70%" in result


class TestRenderHotOffersEmpty:
    """Tests for render_hot_offers_empty function."""

    def test_empty_ru(self) -> None:
        """Test empty offers message in Russian."""
        result = render_hot_offers_empty(lang="ru")
        assert "Акции" in result
        assert "Пока нет предложений" in result

    def test_empty_uz(self) -> None:
        """Test empty offers message in Uzbek."""
        result = render_hot_offers_empty(lang="uz")
        assert "Aksiyalar" in result
        assert "Hozircha takliflar yo'q" in result


# =============================================================================
# Tests for render_business_type_store_list
# =============================================================================


class TestRenderBusinessTypeStoreList:
    """Tests for render_business_type_store_list function."""

    def test_render_supermarket_list_ru(self, sample_store_summary: StoreSummary) -> None:
        """Test rendering supermarket list in Russian."""
        result = render_business_type_store_list(
            lang="ru",
            business_type="supermarket",
            city="Ташкент",
            stores=[sample_store_summary],
        )

        assert "Супермаркеты" in result
        assert "Город: Ташкент" in result
        assert "Тестовый магазин" in result
        assert "Рейтинг: 4.5/5" in result
        assert "Предложений: 15" in result

    def test_render_restaurant_list_uz(self, sample_store_summary: StoreSummary) -> None:
        """Test rendering restaurant list in Uzbek."""
        sample_store_summary.business_type = "restaurant"
        result = render_business_type_store_list(
            lang="uz",
            business_type="restaurant",
            city="Toshkent",
            stores=[sample_store_summary],
        )

        assert "Restoranlar" in result
        assert "Shahar: Toshkent" in result
        assert "Reyting: 4.5/5" in result
        assert "Takliflar: 15" in result

    def test_render_with_prompt_ru(self, sample_store_summary: StoreSummary) -> None:
        """Test that prompt is shown in Russian."""
        result = render_business_type_store_list(
            lang="ru",
            business_type="bakery",
            city="Ташкент",
            stores=[sample_store_summary],
        )

        assert "Выберите магазин ниже." in result


# =============================================================================
# Tests for render_store_card
# =============================================================================


class TestRenderStoreCard:
    """Tests for render_store_card function."""

    def test_render_full_store_card_ru(self, sample_store_details: StoreDetails) -> None:
        """Test rendering full store card in Russian."""
        result = render_store_card(lang="ru", store=sample_store_details)

        assert "Тестовый магазин" in result
        assert "Супермаркет" in result
        assert "Город: Ташкент" in result
        assert "Адрес: ул. Навои 10" in result
        assert "Телефон: +998901234567" in result
        assert "Описание: Лучший магазин" in result
        assert "Рейтинг: 4.5/5 (120 отзывов)" in result
        assert "Предложений: 15" in result
        assert "Доставка: доступна" in result
        assert "Стоимость: 10 000 сум" in result
        assert "Мин. заказ: 50 000 сум" in result

    def test_render_store_card_uz(self, sample_store_details: StoreDetails) -> None:
        """Test rendering store card in Uzbek."""
        result = render_store_card(lang="uz", store=sample_store_details)

        assert "Supermarket" in result
        assert "Shahar:" in result
        assert "Manzil:" in result
        assert "Telefon:" in result
        assert "Yetkazib berish: mavjud" in result

    def test_render_store_without_delivery(self, sample_store_details: StoreDetails) -> None:
        """Test store card without delivery."""
        sample_store_details.delivery_enabled = False
        result = render_store_card(lang="ru", store=sample_store_details)

        assert "Доставка: нет" in result


# =============================================================================
# Tests for render_offer_details
# =============================================================================


class TestRenderOfferDetails:
    """Tests for render_offer_details function."""

    def test_render_offer_details_ru(self, sample_offer_details: OfferDetails) -> None:
        """Test rendering offer details in Russian."""
        result = render_offer_details(lang="ru", offer=sample_offer_details)

        assert sample_offer_details.title in result
        assert "Цена: 5 000 сум" in result
        assert "Было: 10 000 сум (-50%)" in result
        assert "В наличии" in result
        assert f"Магазин: {sample_offer_details.store_name}" in result

    def test_render_offer_with_store(
        self, sample_offer_details: OfferDetails, sample_store_details: StoreDetails
    ) -> None:
        """Test rendering offer details with store info."""
        result = render_offer_details(
            lang="ru", offer=sample_offer_details, store=sample_store_details
        )

        assert sample_store_details.name in result
        assert "Доставка: 10 000 сум" in result

# =============================================================================
# Tests for render_store_offers_list
# =============================================================================


class TestRenderStoreOffersList:
    """Tests for render_store_offers_list function."""

    def test_render_store_offers_ru(self, sample_offer_item: OfferListItem) -> None:
        """Test rendering store offers list in Russian."""
        result = render_store_offers_list(
            lang="ru",
            store_name="Мой магазин",
            offers=[sample_offer_item],
            offset=0,
            total=1,
        )

        assert "Мой магазин" in result
        assert "Все товары" in result
        assert "Показано: 1 из 1" in result
        assert "Хлеб белый" in result
        assert "Выберите товар кнопкой или введите номер" in result

    def test_render_store_offers_uz(self, sample_offer_item: OfferListItem) -> None:
        """Test rendering store offers list in Uzbek."""
        result = render_store_offers_list(
            lang="uz",
            store_name="Mening do'konim",
            offers=[sample_offer_item],
            offset=0,
            total=1,
        )

        assert "Barcha mahsulotlar" in result
        assert "Ko'rsatilgan: 1 dan 1" in result
        assert "Mahsulotni tugma orqali tanlang yoki raqamini kiriting" in result


# =============================================================================
# Tests for render_store_reviews
# =============================================================================


class TestRenderStoreReviews:
    """Tests for render_store_reviews function."""

    def test_render_reviews_with_data_ru(self) -> None:
        """Test rendering reviews with data in Russian."""
        reviews = [
            (1, 1, 10, 5, "Отличный магазин!", "2025-01-15"),
            (2, 2, 10, 4, "Хорошо", "2025-01-14"),
        ]
        result = render_store_reviews(
            lang="ru",
            store_name="Тест магазин",
            avg_rating=4.5,
            reviews=reviews,
        )

        assert "Тест магазин" in result
        assert "Отзывы" in result
        assert "Средняя оценка: 4.5/5" in result
        assert "Отличный магазин!" in result
        assert "Оценка: 5/5" in result

    def test_render_reviews_empty_ru(self) -> None:
        """Test rendering empty reviews in Russian."""
        result = render_store_reviews(
            lang="ru",
            store_name="Тест",
            avg_rating=0.0,
            reviews=[],
        )

        assert "Отзывов пока нет" in result

    def test_render_reviews_empty_uz(self) -> None:
        """Test rendering empty reviews in Uzbek."""
        result = render_store_reviews(
            lang="uz",
            store_name="Test",
            avg_rating=0.0,
            reviews=[],
        )

        assert "Hali sharhlar yo'q" in result


# =============================================================================
# Tests for render_offer_card
# =============================================================================


class TestRenderOfferCard:
    """Tests for render_offer_card function."""

    def test_render_offer_card_ru(self, sample_offer_item: OfferListItem) -> None:
        """Test rendering offer card in Russian."""
        result = render_offer_card(lang="ru", offer=sample_offer_item)

        assert sample_offer_item.title in result
        assert "Цена: 5 000 сум" in result
        assert "Было: 10 000 сум (-50%)" in result
        assert "В наличии" in result
        assert f"Магазин: {sample_offer_item.store_name}" in result
        assert "Доставка" in result

    def test_render_offer_card_without_delivery(self) -> None:
        """Test rendering offer card without delivery."""
        offer = OfferListItem(
            id=1,
            store_id=10,
            title="Тест",
            original_price=10000.0,
            discount_price=5000.0,
            discount_percent=50.0,
            store_name="Магазин",
            delivery_enabled=False,
        )
        result = render_offer_card(lang="ru", offer=offer)

        assert "Только самовывоз" in result


# =============================================================================
# Tests for Admin Templates
# =============================================================================


class TestRenderUserStats:
    """Tests for render_user_stats function."""

    def test_render_user_stats(self) -> None:
        """Test rendering user statistics."""
        stats = UserStats(
            total=1000,
            sellers=50,
            customers=950,
            week_users=100,
            today_users=10,
        )
        result = render_user_stats(stats)

        assert "Пользователи" in result
        assert "Всего: 1000" in result
        assert "Партнёры: 50" in result
        assert "Покупатели: 950" in result
        assert "За неделю: +100" in result
        assert "Сегодня: +10" in result


class TestRenderStoreStats:
    """Tests for render_store_stats function."""

    def test_render_store_stats(self) -> None:
        """Test rendering store statistics."""
        stats = StoreStats(
            active=80,
            pending=10,
            rejected=5,
        )
        result = render_store_stats(stats)

        assert "Магазины" in result
        assert "Активные: 80" in result
        assert "На модерации: 10" in result
        assert "Отклонённые: 5" in result


class TestRenderOfferStats:
    """Tests for render_offer_stats function."""

    def test_render_offer_stats(self) -> None:
        """Test rendering offer statistics."""
        stats = OfferStats(
            active=500,
            inactive=100,
            deleted=50,
            top_categories=[("bakery", 200), ("dairy", 150)],
        )
        result = render_offer_stats(stats)

        assert "Товары" in result
        assert "Активные: 500" in result
        assert "Неактивные: 100" in result
        assert "Удалённые: 50" in result
        assert "Топ категорий" in result
        assert "bakery: 200" in result
        assert "dairy: 150" in result

    def test_render_offer_stats_no_categories(self) -> None:
        """Test rendering offer stats without categories."""
        stats = OfferStats(
            active=10,
            inactive=5,
            deleted=1,
            top_categories=[],
        )
        result = render_offer_stats(stats)

        assert "Топ категорий" not in result


class TestRenderBookingStats:
    """Tests for render_booking_stats function."""

    def test_render_booking_stats(self) -> None:
        """Test rendering booking statistics."""
        stats = BookingStats(
            total=1000,
            pending=50,
            completed=900,
            cancelled=50,
            today_bookings=25,
            today_revenue=5000000.0,
        )
        result = render_booking_stats(stats)

        assert "Бронирования" in result
        assert "Всего: 1000" in result
        assert "Активные: 50" in result
        assert "Завершённые: 900" in result
        assert "Отменённые: 50" in result
        assert "Сегодня: 25" in result
        assert "5,000,000" in result  # formatted revenue
