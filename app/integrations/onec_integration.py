"""
1C Integration Module - интеграция с 1С для автоматического импорта товаров с истекающим сроком.

Поддерживаемые варианты подключения:
1. OData REST API (1С 8.3+)
2. HTTP-сервис 1С (кастомный endpoint)
3. Выгрузка в файл (CSV/JSON) по расписанию

Логика:
- Запрашиваем только товары с сроком годности <= N дней
- Автоматически рассчитываем скидку
- Создаём предложения в боте
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urljoin

from logging_config import logger

# Optional dependencies
try:
    import aiohttp

    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    aiohttp = None  # type: ignore


@dataclass
class OneCConfig:
    """Конфигурация подключения к 1С."""

    # Базовый URL 1С (например: http://192.168.1.100/base1c/odata/standard.odata/)
    base_url: str

    # Авторизация
    username: str
    password: str

    # Настройки фильтрации
    days_until_expiry: int = 7  # Импортировать товары с сроком <= 7 дней
    min_quantity: int = 1  # Минимальное количество для импорта

    # Маппинг категорий 1С -> категории бота
    category_mapping: dict[str, str] = field(default_factory=dict)

    # Фильтр по складам/магазинам (опционально)
    warehouse_filter: list[str] = field(default_factory=list)

    # Интервал синхронизации (минуты)
    sync_interval_minutes: int = 60

    # Включить автосинхронизацию
    auto_sync_enabled: bool = False


@dataclass
class OneCProduct:
    """Товар из 1С."""

    code: str  # Код товара в 1С
    name: str
    price: int  # Цена в тийинах/копейках
    quantity: int
    expiry_date: datetime
    category: str = "other"
    unit: str = "шт"
    barcode: str | None = None
    photo_url: str | None = None

    # Дополнительные поля 1С
    warehouse: str | None = None
    supplier: str | None = None

    def days_until_expiry(self) -> int:
        """Дней до истечения срока."""
        return (self.expiry_date.date() - datetime.now().date()).days


class OneCIntegration:
    """
    Интеграция с 1С через OData API.

    Пример использования:
    ```python
    config = OneCConfig(
        base_url="http://server:8080/base/odata/standard.odata/",
        username="api_user",
        password="secret",
        days_until_expiry=5,
    )

    integration = OneCIntegration(config)
    products = await integration.fetch_expiring_products()

    for product in products:
        print(f"{product.name}: expires in {product.days_until_expiry()} days")
    ```
    """

    def __init__(self, config: OneCConfig):
        self.config = config
        self._session: aiohttp.ClientSession | None = None
        self._last_sync: datetime | None = None
        self._sync_task: asyncio.Task | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Получить или создать HTTP сессию."""
        if not AIOHTTP_AVAILABLE:
            raise ImportError(
                "aiohttp is required for 1C integration. Install: pip install aiohttp"
            )

        if self._session is None or self._session.closed:
            auth = aiohttp.BasicAuth(self.config.username, self.config.password)
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(auth=auth, timeout=timeout)

        return self._session

    async def close(self) -> None:
        """Закрыть соединение."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def test_connection(self) -> tuple[bool, str]:
        """
        Проверить подключение к 1С.

        Returns:
            (success, message)
        """
        try:
            session = await self._get_session()
            url = urljoin(self.config.base_url, "$metadata")

            async with session.get(url) as response:
                if response.status == 200:
                    return True, "✅ Подключение успешно"
                elif response.status == 401:
                    return False, "❌ Ошибка авторизации (неверный логин/пароль)"
                elif response.status == 404:
                    return False, "❌ OData сервис не найден"
                else:
                    return False, f"❌ Ошибка: HTTP {response.status}"

        except asyncio.TimeoutError:
            return False, "❌ Таймаут подключения"
        except Exception as e:
            return False, f"❌ Ошибка: {e}"

    async def fetch_expiring_products(
        self,
        days_limit: int | None = None,
        warehouse: str | None = None,
    ) -> list[OneCProduct]:
        """
        Получить товары с истекающим сроком годности.

        Args:
            days_limit: Максимум дней до истечения (по умолчанию из конфига)
            warehouse: Фильтр по складу

        Returns:
            Список товаров
        """
        days = days_limit or self.config.days_until_expiry
        expiry_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")

        # OData фильтр: срок годности <= today + N дней И количество > 0
        odata_filter = (
            f"СрокГодности le datetime'{expiry_date}' "
            f"and Количество ge {self.config.min_quantity}"
        )

        if warehouse:
            odata_filter += f" and Склад eq '{warehouse}'"

        # Формируем URL запроса
        # Типичный путь в 1С: Catalog_Номенклатура или AccumulationRegister_ОстаткиТоваров
        params = {
            "$filter": odata_filter,
            "$format": "json",
            "$select": "Код,Наименование,Цена,Количество,СрокГодности,Категория,Штрихкод",
            "$top": 100,  # Лимит
        }

        try:
            session = await self._get_session()

            # Пробуем разные endpoints (зависит от конфигурации 1С)
            endpoints = [
                "InformationRegister_ОстаткиСоСрокомГодности",
                "AccumulationRegister_ТоварыНаСкладах",
                "Catalog_Номенклатура",
            ]

            products: list[OneCProduct] = []

            for endpoint in endpoints:
                url = urljoin(self.config.base_url, endpoint)

                try:
                    async with session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            products = self._parse_odata_response(data)
                            if products:
                                break
                except Exception as e:
                    logger.debug(f"1C endpoint {endpoint} failed: {e}")
                    continue

            logger.info(f"1C: Fetched {len(products)} products with expiry <= {days} days")
            return products

        except Exception as e:
            logger.error(f"1C fetch_expiring_products error: {e}")
            return []

    def _parse_odata_response(self, data: dict) -> list[OneCProduct]:
        """Парсинг ответа OData."""
        products = []

        items = data.get("value", [])
        if not items:
            items = data.get("d", {}).get("results", [])

        for item in items:
            try:
                # Маппинг полей (может отличаться в разных конфигурациях 1С)
                code = item.get("Код") or item.get("Code") or item.get("Ref_Key", "")
                name = item.get("Наименование") or item.get("Description") or ""
                price = self._parse_price(item.get("Цена") or item.get("Price") or 0)
                quantity = int(item.get("Количество") or item.get("Quantity") or 0)

                expiry_str = item.get("СрокГодности") or item.get("ExpiryDate") or ""
                expiry_date = self._parse_date(expiry_str)

                if not name or not expiry_date or quantity <= 0:
                    continue

                category_1c = item.get("Категория") or item.get("Category") or ""
                category = self.config.category_mapping.get(category_1c, "other")

                product = OneCProduct(
                    code=str(code),
                    name=name,
                    price=price,
                    quantity=quantity,
                    expiry_date=expiry_date,
                    category=category,
                    barcode=item.get("Штрихкод") or item.get("Barcode"),
                    warehouse=item.get("Склад") or item.get("Warehouse"),
                )
                products.append(product)

            except Exception as e:
                logger.debug(f"1C parse error for item: {e}")
                continue

        return products

    def _parse_price(self, value: Any) -> int:
        """Парсинг цены в тийины."""
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            # Убираем пробелы и запятые
            clean = value.replace(" ", "").replace(",", ".")
            try:
                return int(float(clean))
            except ValueError:
                return 0
        return 0

    def _parse_date(self, value: Any) -> datetime | None:
        """Парсинг даты из 1С."""
        if isinstance(value, datetime):
            return value

        if not value:
            return None

        date_str = str(value)

        # Форматы дат 1С
        formats = [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%d.%m.%Y",
            "%Y%m%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str[:19], fmt)
            except ValueError:
                continue

        return None

    async def sync_to_store(
        self,
        store_id: int,
        db: Any,
        auto_discount_service: Any,
    ) -> dict[str, int]:
        """
        Синхронизировать товары из 1С в магазин.

        Args:
            store_id: ID магазина в боте
            db: Database instance
            auto_discount_service: AutoDiscountService для расчёта скидок

        Returns:
            Статистика: {"imported": N, "updated": N, "skipped": N}
        """
        stats = {"imported": 0, "updated": 0, "skipped": 0, "errors": 0}

        try:
            products = await self.fetch_expiring_products()

            for product in products:
                try:
                    # Рассчитываем скидку
                    discount = auto_discount_service.calculate_discount(
                        product.expiry_date, product.price
                    )

                    # Пропускаем товары без скидки
                    if discount.discount_percent == 0:
                        stats["skipped"] += 1
                        continue

                    # Проверяем, есть ли уже такой товар (по коду 1С)
                    existing = self._find_existing_offer(db, store_id, product.code)

                    if existing:
                        # Обновляем существующий
                        offer_id = existing.get("offer_id") or existing[0]
                        db.update_offer(
                            offer_id,
                            quantity=product.quantity,
                            discount_price=discount.discount_price,
                            description=discount.urgency_message,
                        )
                        stats["updated"] += 1
                    else:
                        # Создаём новый
                        db.create_offer(
                            store_id=store_id,
                            title=product.name,
                            description=discount.urgency_message,
                            original_price=product.price,
                            discount_price=discount.discount_price,
                            quantity=product.quantity,
                            category=product.category,
                            expiry_date=product.expiry_date.strftime("%Y-%m-%d"),
                        )
                        stats["imported"] += 1

                except Exception as e:
                    logger.error(f"1C sync error for product {product.code}: {e}")
                    stats["errors"] += 1

            self._last_sync = datetime.now()
            logger.info(f"1C sync complete: {stats}")

        except Exception as e:
            logger.error(f"1C sync_to_store error: {e}")
            stats["errors"] += 1

        return stats

    def _find_existing_offer(self, db: Any, store_id: int, code_1c: str) -> Any:
        """Найти существующее предложение по коду 1С."""
        # Ищем в описании или создаём отдельное поле
        # Пока простой поиск по названию (можно улучшить)
        offers = db.get_store_offers(store_id, status="active")
        for offer in offers:
            # Проверяем есть ли код в описании
            desc = offer.get("description", "") if isinstance(offer, dict) else ""
            if f"[1C:{code_1c}]" in desc:
                return offer
        return None

    async def start_auto_sync(
        self,
        store_id: int,
        db: Any,
        auto_discount_service: Any,
    ) -> None:
        """Запустить автоматическую синхронизацию."""
        if not self.config.auto_sync_enabled:
            return

        async def sync_loop():
            while True:
                try:
                    await self.sync_to_store(store_id, db, auto_discount_service)
                except Exception as e:
                    logger.error(f"1C auto-sync error: {e}")

                await asyncio.sleep(self.config.sync_interval_minutes * 60)

        self._sync_task = asyncio.create_task(sync_loop())
        logger.info(f"1C auto-sync started (every {self.config.sync_interval_minutes} min)")

    def stop_auto_sync(self) -> None:
        """Остановить автоматическую синхронизацию."""
        if self._sync_task:
            self._sync_task.cancel()
            self._sync_task = None
            logger.info("1C auto-sync stopped")


# =============================================================================
# Альтернатива: HTTP-сервис 1С (более простой вариант)
# =============================================================================


class OneCHttpService:
    """
    Интеграция через кастомный HTTP-сервис 1С.

    На стороне 1С создаётся простой HTTP-сервис который возвращает JSON:

    ```bsl
    // 1C код HTTP-сервиса
    Функция ПолучитьТоварыССрокомГодности(Запрос)
        ДнейДоИстечения = Число(Запрос.ПараметрыURL.Получить("days"));
        Если ДнейДоИстечения = 0 Тогда
            ДнейДоИстечения = 7;
        КонецЕсли;

        ДатаГраница = ТекущаяДата() + ДнейДоИстечения * 86400;

        Запрос = Новый Запрос;
        Запрос.Текст = "ВЫБРАТЬ
            |   Товары.Код,
            |   Товары.Наименование,
            |   Остатки.Количество,
            |   Товары.Цена,
            |   Партии.СрокГодности
            |ИЗ РегистрНакопления.ОстаткиТоваров.Остатки КАК Остатки
            |   ЛЕВОЕ СОЕДИНЕНИЕ Справочник.Номенклатура КАК Товары
            |   ПО Остатки.Номенклатура = Товары.Ссылка
            |ГДЕ Партии.СрокГодности <= &ДатаГраница
            |   И Остатки.Количество > 0";
        Запрос.УстановитьПараметр("ДатаГраница", ДатаГраница);

        Результат = Запрос.Выполнить().Выгрузить();

        // Формируем JSON
        ЗаписьJSON = Новый ЗаписьJSON;
        // ... сериализация в JSON

        Ответ = Новый HTTPСервисОтвет(200);
        Ответ.УстановитьТелоИзСтроки(СтрокаJSON);
        Возврат Ответ;
    КонецФункции
    ```
    """

    def __init__(self, service_url: str, api_key: str | None = None):
        """
        Args:
            service_url: URL HTTP-сервиса 1С (например: http://server/base/hs/fudly/)
            api_key: API ключ (если настроена авторизация)
        """
        self.service_url = service_url.rstrip("/")
        self.api_key = api_key

    async def fetch_expiring_products(self, days: int = 7) -> list[OneCProduct]:
        """Получить товары с истекающим сроком."""
        if not AIOHTTP_AVAILABLE:
            raise ImportError("aiohttp required")

        url = f"{self.service_url}/products"
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        params = {"days": days}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status != 200:
                        logger.error(f"1C HTTP service error: {response.status}")
                        return []

                    data = await response.json()
                    return self._parse_response(data)

        except Exception as e:
            logger.error(f"1C HTTP service error: {e}")
            return []

    def _parse_response(self, data: dict | list) -> list[OneCProduct]:
        """Парсинг ответа."""
        products = []

        items = data if isinstance(data, list) else data.get("products", [])

        for item in items:
            try:
                expiry_date = datetime.strptime(item["expiry_date"], "%Y-%m-%d")

                product = OneCProduct(
                    code=item["code"],
                    name=item["name"],
                    price=int(item["price"]),
                    quantity=int(item["quantity"]),
                    expiry_date=expiry_date,
                    category=item.get("category", "other"),
                    barcode=item.get("barcode"),
                )
                products.append(product)
            except Exception as e:
                logger.debug(f"Parse error: {e}")

        return products


# =============================================================================
# Хелперы для настройки интеграции
# =============================================================================


def create_1c_config_from_env() -> OneCConfig | None:
    """Создать конфигурацию из переменных окружения."""
    import os

    base_url = os.getenv("ONEC_BASE_URL")
    username = os.getenv("ONEC_USERNAME")
    password = os.getenv("ONEC_PASSWORD")

    if not all([base_url, username, password]):
        return None

    return OneCConfig(
        base_url=base_url,
        username=username,
        password=password,
        days_until_expiry=int(os.getenv("ONEC_DAYS_LIMIT", "7")),
        sync_interval_minutes=int(os.getenv("ONEC_SYNC_INTERVAL", "60")),
        auto_sync_enabled=os.getenv("ONEC_AUTO_SYNC", "false").lower() == "true",
    )


# =============================================================================
# Пример JSON формата для простой интеграции
# =============================================================================

SAMPLE_JSON_FORMAT = """
{
    "products": [
        {
            "code": "00001234",
            "name": "Молоко 3.2% Parmalat 1л",
            "price": 15000,
            "quantity": 25,
            "expiry_date": "2025-11-30",
            "category": "dairy",
            "barcode": "4601662000012"
        },
        {
            "code": "00001235",
            "name": "Йогурт клубничный Danone 125г",
            "price": 8500,
            "quantity": 40,
            "expiry_date": "2025-11-29",
            "category": "dairy"
        }
    ]
}
"""
