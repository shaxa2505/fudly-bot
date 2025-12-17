# 🔍 Полный Анализ Системы Товаров - Критические Проблемы

## 📋 Executive Summary

**Статус:** 🔴 КРИТИЧЕСКИЕ ПРОБЛЕМЫ ОБНАРУЖЕНЫ

Системы создания товаров в обычном боте и партнерской панели работают **по разной логике**, что приводит к:
- Несовместимости данных
- Невозможности редактирования товаров созданных через панель
- Разным полям в базе данных
- Отсутствию единой валидации

---

## 1️⃣ Текущее Состояние

### 🤖 Обычный Бот (handlers/seller/create_offer.py)

**Процесс создания товара:**
```python
# Шаги FSM:
1. Выбор категории (CreateOffer.category)
2. Название (CreateOffer.title)
3. Оригинальная цена (CreateOffer.original_price)
4. Скидка (CreateOffer.discount_price)
5. Единица измерения (CreateOffer.unit_type)
6. Количество (CreateOffer.quantity)
7. Срок годности (CreateOffer.expiry_date)
8. Фото (CreateOffer.photo) - optional

# Вызов базы:
offer_id = db.add_offer(
    store_id=data["store_id"],
    title=data["title"],
    description=data["title"],          # ⚠️ = title
    original_price=data["original_price"],
    discount_price=data["discount_price"],
    quantity=quantity,
    available_from="08:00",             # ⚠️ hardcoded
    available_until="23:00",            # ⚠️ hardcoded
    photo=data.get("photo"),            # ⚠️ photo (не photo_id)
    expiry_date=data["expiry_date"],
    unit=unit,
    category=data.get("category", "other"),
)
```

**Проблемы:**
- ❌ `description` всегда = `title` (нет отдельного поля)
- ❌ `available_from/until` захардкожены ("08:00", "23:00")
- ❌ Использует `photo` вместо `photo_id` (inconsistent naming)
- ❌ Нет валидации дат
- ❌ Нет возможности пропустить original_price (обязательное поле)

### 💻 Партнерская Панель (app/api/partner_panel_simple.py)

**Процесс создания товара:**
```python
# API endpoint: POST /products
@router.post("/products")
async def create_product(
    title: str = Form(...),
    category: str = Form("other"),
    original_price: int = Form(0),        # ⚠️ default 0
    discount_price: int = Form(...),
    quantity: int = Form(...),
    unit: str = Form("шт"),
    expiry_date: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    photo_id: Optional[str] = Form(None),  # ⚠️ photo_id (правильно)
)

# Вызов базы:
offer_id = db.add_offer(
    store_id=store["store_id"],
    title=title,
    description=description or title,      # ⚠️ fallback to title
    original_price=original_price if original_price > 0 else None,  # ⚠️ conditional
    discount_price=discount_price,
    quantity=quantity,
    available_from=now,                    # ⚠️ ISO timestamp
    available_until=until,                 # ⚠️ now + 7 days
    expiry_date=expiry.isoformat() if expiry else None,
    unit=unit,
    category=category,
    photo_id=photo_id,                     # ⚠️ photo_id (правильно)
)
```

**Проблемы:**
- ❌ `available_from/until` = ISO timestamps (бот использует "08:00")
- ❌ `original_price` может быть None (бот всегда передает значение)
- ❌ Использует `photo_id` (бот использует `photo`)
- ❌ Разная обработка expiry_date (ISO vs string)

### 🗄️ База Данных (offers table)

```sql
CREATE TABLE offers (
    offer_id SERIAL PRIMARY KEY,
    store_id INTEGER,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    original_price FLOAT,              -- ⚠️ nullable
    discount_price FLOAT,              -- ⚠️ nullable
    quantity INTEGER DEFAULT 1,
    available_from VARCHAR(50),        -- ⚠️ VARCHAR (не TIME/TIMESTAMP)
    available_until VARCHAR(50),       -- ⚠️ VARCHAR
    expiry_date VARCHAR(50),           -- ⚠️ VARCHAR (не DATE)
    photo_id VARCHAR(255),             -- ⚠️ но бот использует "photo"
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    unit VARCHAR(20) DEFAULT 'шт',
    category VARCHAR(50) DEFAULT 'other'
)
```

**Проблемы схемы:**
- ❌ `available_from/until` = VARCHAR вместо TIME или TIMESTAMP
- ❌ `expiry_date` = VARCHAR вместо DATE
- ❌ `original_price/discount_price` = FLOAT (должно быть INTEGER для сумов)
- ❌ Нет валидации на уровне базы
- ❌ Нет CHECK constraints

### 🔧 Реализация add_offer (database_pg_module/mixins/offers.py)

```python
def add_offer(
    self,
    store_id: int,
    title: str,
    description: str = None,
    original_price: float = None,      # ⚠️ optional
    discount_price: float = None,      # ⚠️ optional
    quantity: int = 1,
    available_from: str = None,
    available_until: str = None,
    photo_id: str = None,
    expiry_date: str = None,
    unit: str = "шт",
    category: str = "other",
    photo: str = None,                 # ⚠️ LEGACY PARAMETER
):
    """Add new offer."""
    actual_photo_id = photo if photo is not None else photo_id  # ⚠️ HACK

    # Normalize expiry_date format
    if expiry_date and "." in expiry_date:
        try:
            from datetime import datetime
            dt = datetime.strptime(expiry_date, "%d.%m.%Y")
            expiry_date = dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
```

**Проблемы:**
- ❌ Принимает и `photo` и `photo_id` (confusion)
- ❌ `actual_photo_id = photo if photo is not None else photo_id` - грязный хак
- ❌ Нормализация expiry_date происходит здесь (должна быть на уровне API)
- ❌ Нет валидации входных данных
- ❌ Молча игнорирует невалидные даты

---

## 2️⃣ Критические Различия

| Аспект | Обычный Бот | Партнерская Панель | База Данных |
|--------|-------------|-------------------|-------------|
| **photo param** | `photo` (file_id) | `photo_id` (file_id) | `photo_id` (column) |
| **description** | = title | optional или = title | TEXT nullable |
| **original_price** | обязателен | default 0 или None | FLOAT nullable |
| **available_from** | "08:00" | ISO timestamp | VARCHAR(50) |
| **available_until** | "23:00" | ISO + 7 days | VARCHAR(50) |
| **expiry_date** | "DD.MM.YYYY" | ISO format | VARCHAR(50) |
| **unit** | выбор из списка | свободный текст | VARCHAR(20) |
| **category** | выбор из FSM | свободный текст | VARCHAR(50) |

---

## 3️⃣ Проблемы Совместимости

### 🔴 Проблема #1: Невозможность редактирования

**Симптом:** Товары созданные через панель нельзя редактировать в боте

**Причина:**
1. Панель использует ISO timestamps в available_from/until
2. Бот ожидает "HH:MM" формат
3. При парсинге времени в боте происходит ошибка

```python
# Бот пытается парсить:
time_str = "2025-12-17T10:30:00"  # От панели
# Ожидает:
time_str = "10:30"  # Формат бота
```

### 🔴 Проблема #2: Фото не отображаются

**Симптом:** Товары созданные через панель без fix имеют photo=None

**Причина:**
1. Панель отправляла raw file (исправлено в последнем коммите)
2. Бот использует параметр `photo`, панель - `photo_id`
3. Функция `add_offer` имеет хак для совместимости

### 🔴 Проблема #3: Некорректные цены

**Симптом:** В базе original_price может быть 0 или None

**Причина:**
1. Панель передает `original_price=0` по умолчанию
2. API конвертирует 0 в None
3. В боте нет проверки на None при отображении

### 🔴 Проблема #4: Разные типы данных

**База:** `FLOAT` для цен (неправильно для валюты)
**Бот/Панель:** Работают с integers

---

## 4️⃣ Идеальная Архитектура

### ✅ Единая Схема Базы Данных (ИСПРАВЛЕННАЯ)

```sql
CREATE TABLE offers (
    offer_id SERIAL PRIMARY KEY,
    store_id INTEGER NOT NULL REFERENCES stores(store_id) ON DELETE CASCADE,
    
    -- Product info
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,           -- NOT NULL, требуется
    category VARCHAR(50) NOT NULL,       -- NOT NULL, ENUM?
    
    -- Pricing (в тийинах для точности)
    original_price INTEGER NOT NULL,     -- INT NOT NULL, обязателен
    discount_price INTEGER NOT NULL,     -- INT NOT NULL, обязателен
    discount_percent SMALLINT GENERATED ALWAYS AS (
        ROUND((1 - discount_price::FLOAT / original_price) * 100)
    ) STORED,                            -- AUTO-CALCULATED
    
    -- Stock
    quantity DECIMAL(10, 3) NOT NULL DEFAULT 1,  -- Поддержка дробных (0.5кг)
    unit VARCHAR(20) NOT NULL DEFAULT 'шт',
    
    -- Timing
    available_from TIME,                 -- TIME type, nullable
    available_until TIME,                -- TIME type, nullable
    expiry_date DATE,                    -- DATE type, nullable
    
    -- Media
    photo_id VARCHAR(255),               -- Telegram file_id
    
    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    
    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT positive_prices CHECK (
        original_price > 0 AND 
        discount_price > 0 AND 
        discount_price <= original_price
    ),
    CONSTRAINT positive_quantity CHECK (quantity >= 0),
    CONSTRAINT valid_status CHECK (status IN ('active', 'hidden', 'out_of_stock', 'expired')),
    CONSTRAINT valid_category CHECK (category IN (
        'bakery', 'dairy', 'meat', 'vegetables', 
        'fruits', 'drinks', 'other'
    ))
);

-- Indexes
CREATE INDEX idx_offers_store_status ON offers(store_id, status);
CREATE INDEX idx_offers_category ON offers(category);
CREATE INDEX idx_offers_expiry ON offers(expiry_date) WHERE expiry_date IS NOT NULL;

-- Triggers
CREATE TRIGGER update_offers_updated_at
    BEFORE UPDATE ON offers
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

### ✅ Единый API Layer

```python
# app/domain/models.py
from pydantic import BaseModel, Field, validator
from datetime import date, time
from typing import Optional
from enum import Enum

class Category(str, Enum):
    BAKERY = "bakery"
    DAIRY = "dairy"
    MEAT = "meat"
    VEGETABLES = "vegetables"
    FRUITS = "fruits"
    DRINKS = "drinks"
    OTHER = "other"

class Unit(str, Enum):
    PIECE = "шт"
    KG = "кг"
    LITER = "л"
    PACK = "уп"

class OfferStatus(str, Enum):
    ACTIVE = "active"
    HIDDEN = "hidden"
    OUT_OF_STOCK = "out_of_stock"
    EXPIRED = "expired"

class CreateOfferRequest(BaseModel):
    """Unified offer creation schema"""
    store_id: int
    title: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    category: Category
    
    # Pricing in tiyin (1 sum = 100 tiyin) for precision
    original_price: int = Field(..., gt=0)
    discount_price: int = Field(..., gt=0)
    
    # Stock
    quantity: float = Field(..., ge=0)
    unit: Unit
    
    # Timing (all optional)
    available_from: Optional[time] = None
    available_until: Optional[time] = None
    expiry_date: Optional[date] = None
    
    # Media
    photo_id: Optional[str] = None
    
    @validator('discount_price')
    def discount_must_be_less_than_original(cls, v, values):
        if 'original_price' in values and v > values['original_price']:
            raise ValueError('discount_price must be <= original_price')
        return v
    
    @validator('description', always=True)
    def description_default_to_title(cls, v, values):
        """If no description, use title"""
        if not v and 'title' in values:
            return values['title']
        return v

class OfferResponse(BaseModel):
    """Unified offer response"""
    offer_id: int
    store_id: int
    title: str
    description: str
    category: str
    original_price: int
    discount_price: int
    discount_percent: int
    quantity: float
    unit: str
    available_from: Optional[time]
    available_until: Optional[time]
    expiry_date: Optional[date]
    photo_id: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
```

### ✅ Единый Database Layer

```python
# database_pg_module/mixins/offers.py
def add_offer(self, data: CreateOfferRequest) -> int:
    """
    Add offer using validated Pydantic model.
    Single source of truth for offer creation.
    """
    with self.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO offers (
                store_id, title, description, category,
                original_price, discount_price,
                quantity, unit,
                available_from, available_until, expiry_date,
                photo_id, status
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, 'active'
            )
            RETURNING offer_id
            """,
            (
                data.store_id,
                data.title,
                data.description,
                data.category.value,
                data.original_price,
                data.discount_price,
                data.quantity,
                data.unit.value,
                data.available_from,
                data.available_until,
                data.expiry_date,
                data.photo_id,
            )
        )
        result = cursor.fetchone()
        if not result:
            raise ValueError("Failed to create offer")
        offer_id = result[0]
        logger.info(f"✅ Offer {offer_id} created for store {data.store_id}")
        return offer_id
```

### ✅ Unified Bot Handler

```python
# handlers/seller/create_offer.py
async def _finalize_offer(target: types.Message, state: FSMContext, lang: str):
    """Create offer using unified API"""
    data = await state.get_data()
    
    # Create validated request
    try:
        request = CreateOfferRequest(
            store_id=data["store_id"],
            title=data["title"],
            description=data.get("description") or data["title"],
            category=Category(data.get("category", "other")),
            original_price=int(data["original_price"]),
            discount_price=int(data["discount_price"]),
            quantity=data["quantity"],
            unit=Unit(data.get("unit", "шт")),
            expiry_date=parse_date(data["expiry_date"]),  # Helper
            photo_id=data.get("photo"),
            # available_from/until can be added later
        )
        
        offer_id = db.add_offer(request)
        
    except ValidationError as e:
        await target.answer(f"❌ Ошибка валидации: {e}")
        return
```

### ✅ Unified API Endpoint

```python
# app/api/partner_panel_simple.py
@router.post("/products", response_model=OfferResponse)
async def create_product(
    request: CreateOfferRequest,  # Pydantic validation
    authorization: str = Header(None)
):
    """Create product using unified schema"""
    telegram_id = verify_telegram_webapp(authorization)
    user, store = get_partner_with_store(telegram_id)
    
    # Ensure correct store_id
    request.store_id = store["store_id"]
    
    # Create offer
    offer_id = db.add_offer(request)
    
    # Return full offer
    offer = db.get_offer(offer_id)
    return offer
```

---

## 5️⃣ План Миграции

### 📝 Step 1: Миграция Базы Данных

```sql
-- migration: 010_unified_offers_schema.sql

BEGIN;

-- 1. Add new columns with correct types
ALTER TABLE offers
    ADD COLUMN available_from_time TIME,
    ADD COLUMN available_until_time TIME,
    ADD COLUMN expiry_date_parsed DATE,
    ADD COLUMN original_price_int INTEGER,
    ADD COLUMN discount_price_int INTEGER;

-- 2. Migrate data
UPDATE offers SET
    -- Parse time from varchar
    available_from_time = CASE
        WHEN available_from ~ '^\d{2}:\d{2}$' 
        THEN available_from::TIME
        ELSE NULL
    END,
    available_until_time = CASE
        WHEN available_until ~ '^\d{2}:\d{2}$'
        THEN available_until::TIME
        ELSE NULL
    END,
    -- Parse date
    expiry_date_parsed = CASE
        WHEN expiry_date ~ '^\d{4}-\d{2}-\d{2}$'
        THEN expiry_date::DATE
        WHEN expiry_date ~ '^\d{2}\.\d{2}\.\d{4}$'
        THEN TO_DATE(expiry_date, 'DD.MM.YYYY')
        ELSE NULL
    END,
    -- Convert prices to integers (assuming they're already in sums)
    original_price_int = ROUND(original_price)::INTEGER,
    discount_price_int = ROUND(discount_price)::INTEGER;

-- 3. Drop old columns
ALTER TABLE offers
    DROP COLUMN available_from,
    DROP COLUMN available_until,
    DROP COLUMN expiry_date,
    DROP COLUMN original_price,
    DROP COLUMN discount_price;

-- 4. Rename new columns
ALTER TABLE offers
    RENAME COLUMN available_from_time TO available_from;
ALTER TABLE offers
    RENAME COLUMN available_until_time TO available_until;
ALTER TABLE offers
    RENAME COLUMN expiry_date_parsed TO expiry_date;
ALTER TABLE offers
    RENAME COLUMN original_price_int TO original_price;
ALTER TABLE offers
    RENAME COLUMN discount_price_int TO discount_price;

-- 5. Add constraints
ALTER TABLE offers
    ALTER COLUMN title SET NOT NULL,
    ALTER COLUMN description SET NOT NULL,
    ALTER COLUMN category SET NOT NULL,
    ALTER COLUMN original_price SET NOT NULL,
    ALTER COLUMN discount_price SET NOT NULL,
    ALTER COLUMN quantity SET NOT NULL,
    ALTER COLUMN unit SET NOT NULL,
    ADD CONSTRAINT check_positive_prices 
        CHECK (original_price > 0 AND discount_price > 0 AND discount_price <= original_price),
    ADD CONSTRAINT check_positive_quantity 
        CHECK (quantity >= 0),
    ADD CONSTRAINT check_valid_status 
        CHECK (status IN ('active', 'hidden', 'out_of_stock', 'expired')),
    ADD CONSTRAINT check_valid_category 
        CHECK (category IN ('bakery', 'dairy', 'meat', 'vegetables', 'fruits', 'drinks', 'other'));

-- 6. Add updated_at column and trigger
ALTER TABLE offers ADD COLUMN updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_offers_updated_at
    BEFORE UPDATE ON offers
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMIT;
```

### 📝 Step 2: Обновить Database Layer

1. Добавить Pydantic модели (см. выше)
2. Изменить сигнатуру `add_offer()` принимать Pydantic model
3. Удалить legacy параметры `photo` и хаки
4. Добавить валидацию

### 📝 Step 3: Обновить Bot Handlers

1. Изменить FSM states если нужно
2. Обновить финализацию создания товара
3. Добавить парсинг дат через helper functions
4. Использовать Pydantic модели

### 📝 Step 4: Обновить API

1. Изменить endpoints использовать Pydantic models
2. Убрать Form параметры, использовать Body
3. Добавить response models
4. Унифицировать обработку ошибок

### 📝 Step 5: Обновить Frontend

1. Партнерская панель - использовать новый API формат
2. Мини-приложение - обновить типы данных

---

## 6️⃣ Текущие Приоритеты

### 🔥 КРИТИЧНО (Сделать сейчас)

1. **Исправить photo/photo_id inconsistency**
   - ✅ DONE: Партнерская панель теперь загружает фото правильно
   - ⚠️ TODO: Убрать legacy параметр `photo` из `add_offer()`

2. **Фиксировать available_from/until формат**
   - Решить: ISO timestamps ИЛИ HH:MM
   - Рекомендация: Использовать TIME type в базе

3. **Добавить валидацию цен**
   - original_price НЕ ДОЛЖЕН быть 0 или None
   - discount_price <= original_price

### ⚠️ ВАЖНО (Следующий спринт)

4. **Миграция типов данных**
   - VARCHAR → TIME для времени
   - VARCHAR → DATE для дат
   - FLOAT → INTEGER для цен

5. **Pydantic models**
   - Создать единую схему
   - Использовать во всех местах

### 📋 ЖЕЛАТЕЛЬНО (Будущее)

6. **Рефакторинг database layer**
   - Убрать дублирование кода
   - Единая функция add_offer

7. **Unit tests**
   - Тестировать создание товаров
   - Валидация constraints

---

## 7️⃣ Рекомендации

### 💡 Best Practices

1. **Single Source of Truth**
   - Одна схема Pydantic для offers
   - Используется везде (бот, API, database)

2. **Type Safety**
   - TIME для времени
   - DATE для дат
   - INTEGER для денег (в тийинах если нужна точность)

3. **Validation at Edge**
   - Валидация в Pydantic models
   - Constraints в базе данных
   - НЕ в business logic

4. **Naming Consistency**
   - `photo_id` везде (не `photo`)
   - Единые имена полей

5. **Explicit is Better than Implicit**
   - НЕ использовать defaults для обязательных полей
   - НЕ делать автоматических fallbacks (description = title)

### 🚫 Anti-patterns to Avoid

1. ❌ Разные типы данных в разных местах
2. ❌ Hardcoded значения ("08:00", "23:00")
3. ❌ Хаки для совместимости (`photo if photo else photo_id`)
4. ❌ Молчаливые fallbacks (`description or title`)
5. ❌ VARCHAR для структурированных данных (dates, times)

---

## 8️⃣ Вывод

### 🎯 Ключевые Проблемы

1. **Несовместимые форматы** - бот и панель используют разные типы данных
2. **Отсутствие валидации** - нет проверок на уровне кода и базы
3. **Legacy code** - хаки для обратной совместимости
4. **Неправильные типы в базе** - VARCHAR вместо TIME/DATE, FLOAT вместо INTEGER

### ✅ Решение

Нужна **полная унификация**:
1. Единая Pydantic схема
2. Правильные типы в базе данных
3. Миграция существующих данных
4. Обновление всех интеграций

### ⏱️ Оценка

- **Миграция базы:** 2-3 часа (тестирование + rollback plan)
- **Обновление кода:** 4-6 часов
- **Тестирование:** 2-3 часа
- **ИТОГО:** ~1 рабочий день

### 🚀 Приоритет

**ВЫСОКИЙ** - Текущая система работает, но:
- Неконсистентная
- Сложна в поддержке
- Создает баги при взаимодействии бота и панели

Рекомендую начать миграцию в ближайшее время.
