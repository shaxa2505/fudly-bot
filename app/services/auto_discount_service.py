"""
Auto Discount Service - автоматическое управление скидками по сроку годности.

Этот сервис:
1. Анализирует товары по сроку годности
2. Автоматически устанавливает скидки
3. Может импортировать товары из внешних систем (1C, Excel, API)
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Protocol

from logging_config import logger


class DiscountTier(Enum):
    """Уровни скидок в зависимости от срока годности."""

    FRESH = 0  # > 7 дней - без скидки
    WEEK = 15  # 4-7 дней - 15%
    SOON = 30  # 2-3 дня - 30%
    URGENT = 50  # 1 день - 50%
    LAST_DAY = 70  # Сегодня истекает - 70%


@dataclass
class ProductImport:
    """Данные импортируемого товара."""

    name: str
    original_price: int
    quantity: int
    expiry_date: datetime
    category: str = "other"
    photo_url: str | None = None
    barcode: str | None = None
    description: str | None = None


@dataclass
class DiscountResult:
    """Результат расчёта скидки."""

    discount_percent: int
    discount_price: int
    days_until_expiry: int
    tier: DiscountTier
    urgency_message: str


class ExternalSystemProtocol(Protocol):
    """Протокол для внешних систем (1C, iiko, etc.)."""

    async def fetch_products(self, store_id: int) -> list[dict[str, Any]]:
        """Получить список товаров из внешней системы."""
        ...

    async def sync_stock(self, store_id: int, product_id: str, quantity: int) -> bool:
        """Синхронизировать остатки."""
        ...


class AutoDiscountService:
    """Сервис автоматического управления скидками."""

    # Настройки скидок по умолчанию (дни до истечения -> процент скидки)
    DEFAULT_DISCOUNT_RULES: dict[int, int] = {
        7: 15,  # 7 дней - 15%
        5: 20,  # 5 дней - 20%
        3: 30,  # 3 дня - 30%
        2: 40,  # 2 дня - 40%
        1: 50,  # 1 день - 50%
        0: 70,  # Сегодня - 70%
    }

    def __init__(self, db: Any, bot: Any | None = None):
        self.db = db
        self.bot = bot
        self.discount_rules = self.DEFAULT_DISCOUNT_RULES.copy()

    def calculate_discount(self, expiry_date: datetime, original_price: int) -> DiscountResult:
        """
        Рассчитать скидку на основе срока годности.

        Args:
            expiry_date: Дата истечения срока годности
            original_price: Оригинальная цена

        Returns:
            DiscountResult с информацией о скидке
        """
        now = datetime.now()
        days_left = (expiry_date.date() - now.date()).days

        # Определяем процент скидки
        discount_percent = 0
        tier = DiscountTier.FRESH

        if days_left <= 0:
            discount_percent = self.discount_rules.get(0, 70)
            tier = DiscountTier.LAST_DAY
            urgency = "🔴 Последний день!"
        elif days_left == 1:
            discount_percent = self.discount_rules.get(1, 50)
            tier = DiscountTier.URGENT
            urgency = "🟠 Истекает завтра!"
        elif days_left <= 3:
            discount_percent = self.discount_rules.get(3, 30)
            tier = DiscountTier.SOON
            urgency = f"🟡 Осталось {days_left} дня"
        elif days_left <= 7:
            discount_percent = self.discount_rules.get(7, 15)
            tier = DiscountTier.WEEK
            urgency = f"🟢 Осталось {days_left} дней"
        else:
            urgency = f"✅ Свежий товар ({days_left} дней)"

        # Рассчитываем цену со скидкой
        discount_price = int(original_price * (100 - discount_percent) / 100)

        return DiscountResult(
            discount_percent=discount_percent,
            discount_price=discount_price,
            days_until_expiry=days_left,
            tier=tier,
            urgency_message=urgency,
        )

    def set_custom_rules(self, rules: dict[int, int]) -> None:
        """
        Установить кастомные правила скидок.

        Args:
            rules: Словарь {дни_до_истечения: процент_скидки}
        """
        self.discount_rules = rules
        logger.info(f"Custom discount rules set: {rules}")

    async def import_from_csv(
        self, store_id: int, csv_content: str | bytes, owner_id: int
    ) -> dict[str, Any]:
        """
        Импортировать товары из CSV файла.

        Ожидаемые колонки:
        - name: Название товара
        - price: Цена
        - quantity: Количество
        - expiry_date: Дата истечения (YYYY-MM-DD или DD.MM.YYYY)
        - category: Категория (опционально)
        - barcode: Штрихкод (опционально)

        Returns:
            Статистика импорта
        """
        if isinstance(csv_content, bytes):
            csv_content = csv_content.decode("utf-8-sig")

        reader = csv.DictReader(io.StringIO(csv_content), delimiter=";")

        imported = 0
        skipped = 0
        errors: list[str] = []

        for row_num, row in enumerate(reader, start=2):
            try:
                # Парсим данные
                name = row.get("name", "").strip()
                price_str = row.get("price", "0").replace(" ", "").replace(",", "")
                quantity_str = row.get("quantity", "1").replace(" ", "")
                expiry_str = row.get("expiry_date", "").strip()
                category = row.get("category", "other").strip().lower()

                if not name or not expiry_str:
                    skipped += 1
                    continue

                # Парсим цену
                try:
                    original_price = int(float(price_str))
                except ValueError:
                    errors.append(f"Строка {row_num}: неверная цена '{price_str}'")
                    continue

                # Парсим количество
                try:
                    quantity = int(float(quantity_str))
                except ValueError:
                    quantity = 1

                # Парсим дату
                expiry_date = self._parse_date(expiry_str)
                if not expiry_date:
                    errors.append(f"Строка {row_num}: неверная дата '{expiry_str}'")
                    continue

                # Рассчитываем скидку
                discount = self.calculate_discount(expiry_date, original_price)

                # Пропускаем товары без скидки (слишком свежие)
                if discount.discount_percent == 0:
                    skipped += 1
                    continue

                # Создаём предложение
                offer_id = self.db.create_offer(
                    store_id=store_id,
                    title=name,
                    description=discount.urgency_message,
                    original_price=original_price,
                    discount_price=discount.discount_price,
                    quantity=quantity,
                    category=category,
                    expiry_date=expiry_date.strftime("%Y-%m-%d"),
                )

                if offer_id:
                    imported += 1
                    logger.info(
                        f"Imported: {name}, price: {original_price} -> {discount.discount_price} "
                        f"(-{discount.discount_percent}%), expires: {expiry_date.date()}"
                    )
                else:
                    errors.append(f"Строка {row_num}: не удалось создать предложение")

            except Exception as e:
                errors.append(f"Строка {row_num}: {str(e)}")

        result = {
            "imported": imported,
            "skipped": skipped,
            "errors": errors[:10],  # Ограничиваем количество ошибок
            "total_errors": len(errors),
        }

        logger.info(f"CSV import complete: {result}")
        return result

    async def import_from_json(
        self, store_id: int, json_content: str | dict, owner_id: int
    ) -> dict[str, Any]:
        """
        Импортировать товары из JSON (для API интеграций).

        Формат:
        {
            "products": [
                {
                    "name": "Молоко",
                    "price": 15000,
                    "quantity": 10,
                    "expiry_date": "2025-12-01",
                    "category": "dairy",
                    "barcode": "4601234567890"
                }
            ]
        }
        """
        if isinstance(json_content, str):
            data = json.loads(json_content)
        else:
            data = json_content

        products = data.get("products", [])
        imported = 0
        skipped = 0
        errors: list[str] = []

        for idx, product in enumerate(products):
            try:
                name = product.get("name", "").strip()
                original_price = int(product.get("price", 0))
                quantity = int(product.get("quantity", 1))
                expiry_str = product.get("expiry_date", "")
                category = product.get("category", "other")

                if not name or not expiry_str or original_price <= 0:
                    skipped += 1
                    continue

                expiry_date = self._parse_date(expiry_str)
                if not expiry_date:
                    errors.append(f"Товар {idx + 1}: неверная дата")
                    continue

                discount = self.calculate_discount(expiry_date, original_price)

                if discount.discount_percent == 0:
                    skipped += 1
                    continue

                offer_id = self.db.create_offer(
                    store_id=store_id,
                    title=name,
                    description=discount.urgency_message,
                    original_price=original_price,
                    discount_price=discount.discount_price,
                    quantity=quantity,
                    category=category,
                    expiry_date=expiry_date.strftime("%Y-%m-%d"),
                )

                if offer_id:
                    imported += 1

            except Exception as e:
                errors.append(f"Товар {idx + 1}: {str(e)}")

        return {
            "imported": imported,
            "skipped": skipped,
            "errors": errors[:10],
            "total_errors": len(errors),
        }

    async def update_existing_offers_discounts(self, store_id: int | None = None) -> dict[str, int]:
        """
        Обновить скидки для существующих предложений на основе срока годности.

        Запускается по расписанию (например, каждый день в 6:00).
        """
        updated = 0
        deactivated = 0
        notified_owners: set[int] = set()

        # Получаем все активные предложения
        if store_id:
            offers = self.db.get_store_offers(store_id, status="active")
        else:
            offers = self.db.get_all_active_offers()

        for offer in offers:
            try:
                offer_id = offer.get("offer_id") if isinstance(offer, dict) else offer[0]
                expiry_str = offer.get("expiry_date") if isinstance(offer, dict) else offer[7]
                original_price = (
                    offer.get("original_price") if isinstance(offer, dict) else offer[4]
                )
                current_discount = (
                    offer.get("discount_price") if isinstance(offer, dict) else offer[5]
                )
                store_id_offer = offer.get("store_id") if isinstance(offer, dict) else offer[1]

                if not expiry_str:
                    continue

                expiry_date = self._parse_date(str(expiry_str))
                if not expiry_date:
                    continue

                discount = self.calculate_discount(expiry_date, original_price)

                # Если товар просрочен - деактивируем
                if discount.days_until_expiry < 0:
                    self.db.update_offer_status(offer_id, "expired")
                    deactivated += 1
                    continue

                # Если скидка изменилась - обновляем
                if discount.discount_price != current_discount:
                    self.db.update_offer(
                        offer_id,
                        discount_price=discount.discount_price,
                        description=discount.urgency_message,
                    )
                    updated += 1

                    # Уведомляем владельца о критичных изменениях
                    if discount.tier in [DiscountTier.URGENT, DiscountTier.LAST_DAY]:
                        if self.bot and store_id_offer not in notified_owners:
                            await self._notify_owner_urgent(store_id_offer, offer, discount)
                            notified_owners.add(store_id_offer)

            except Exception as e:
                logger.error(f"Error updating offer discount: {e}")

        result = {"updated": updated, "deactivated": deactivated}
        logger.info(f"Auto-discount update complete: {result}")
        return result

    async def _notify_owner_urgent(
        self, store_id: int, offer: Any, discount: DiscountResult
    ) -> None:
        """Уведомить владельца о срочных товарах."""
        if not self.bot:
            return

        store = self.db.get_store(store_id)
        if not store:
            return

        owner_id = store.get("owner_id") if isinstance(store, dict) else store[1]
        offer_title = offer.get("title") if isinstance(offer, dict) else offer[2]

        try:
            await self.bot.send_message(
                owner_id,
                f"⚠️ <b>Срочное уведомление!</b>\n\n"
                f"📦 Товар: {offer_title}\n"
                f"{discount.urgency_message}\n"
                f"💰 Новая цена: <b>{discount.discount_price:,} сум</b> "
                f"(-{discount.discount_percent}%)\n\n"
                f"💡 Рекомендуем продвинуть этот товар или увеличить скидку!",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Failed to notify owner {owner_id}: {e}")

    def _parse_date(self, date_str: str) -> datetime | None:
        """Парсит дату из различных форматов."""
        formats = [
            "%Y-%m-%d",
            "%d.%m.%Y",
            "%d/%m/%Y",
            "%Y/%m/%d",
            "%d-%m-%Y",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue

        return None

    def generate_sample_csv(self) -> str:
        """Генерирует пример CSV файла для импорта."""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")
        three_days = (datetime.now() + timedelta(days=3)).strftime("%d.%m.%Y")
        week = (datetime.now() + timedelta(days=7)).strftime("%d.%m.%Y")

        return f"""name;price;quantity;expiry_date;category
Молоко 3.2%;15000;20;{tomorrow};dairy
Йогурт клубничный;12000;15;{three_days};dairy
Хлеб белый;8000;30;{tomorrow};bakery
Сыр Российский;45000;10;{week};dairy
Колбаса вареная;35000;8;{three_days};meat
Торт Наполеон;85000;5;{tomorrow};bakery
"""


# =============================================================================
# Интеграции с внешними системами
# =============================================================================


class OneCIntegration:
    """Интеграция с 1С (пример)."""

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url
        self.auth = (username, password)

    async def fetch_products(self, store_id: int) -> list[dict[str, Any]]:
        """
        Получить товары из 1С.

        В реальной интеграции здесь будет HTTP запрос к OData API 1С.
        """
        # Пример структуры данных из 1С
        # В реальности: async with aiohttp.ClientSession() as session: ...
        return []

    async def sync_stock(self, store_id: int, product_id: str, quantity: int) -> bool:
        """Синхронизировать остатки с 1С."""
        return True


class IikoIntegration:
    """Интеграция с iiko (для ресторанов)."""

    def __init__(self, api_key: str, organization_id: str):
        self.api_key = api_key
        self.organization_id = organization_id

    async def fetch_products(self, store_id: int) -> list[dict[str, Any]]:
        """Получить меню из iiko."""
        return []


class PosterIntegration:
    """Интеграция с Poster POS."""

    def __init__(self, api_token: str):
        self.api_token = api_token

    async def fetch_products(self, store_id: int) -> list[dict[str, Any]]:
        """Получить товары из Poster."""
        return []
