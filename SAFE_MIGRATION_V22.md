# 🔒 БЕЗОПАСНАЯ МИГРАЦИЯ v22.0 - Backend Integration

## ✅ Хорошие новости!

**Бот НЕ сломается!** Таблица `offers` уже имеет все необходимые поля:
- ✅ `category` (уже есть)
- ✅ `unit` (уже есть)
- ✅ `expiry_date` (уже есть)
- ✅ `original_price` (уже есть)
- ✅ `discount_price` (уже есть)

Нужно добавить только **2 новых поля** для улучшений v22.0:
- `stock_quantity` (количество в наличии)
- Для заказов: `cancel_reason`, `cancel_comment`

---

## 🚀 План миграции (3 шага)

### Шаг 1: Добавить недостающие поля (5 минут)

```sql
-- 1. Добавить stock_quantity в offers
ALTER TABLE offers ADD COLUMN IF NOT EXISTS stock_quantity INTEGER DEFAULT 0;

-- 2. Обновить существующие записи (quantity → stock_quantity)
UPDATE offers 
SET stock_quantity = COALESCE(quantity, 0)
WHERE stock_quantity = 0;

-- 3. Добавить поля для причины отмены
ALTER TABLE orders ADD COLUMN IF NOT EXISTS cancel_reason VARCHAR(50);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS cancel_comment TEXT;

-- 4. Создать индексы для быстрой фильтрации
CREATE INDEX IF NOT EXISTS idx_offers_category ON offers(category);
CREATE INDEX IF NOT EXISTS idx_offers_unit ON offers(unit);
CREATE INDEX IF NOT EXISTS idx_offers_stock ON offers(stock_quantity);
CREATE INDEX IF NOT EXISTS idx_orders_cancel_reason ON orders(cancel_reason);

-- Готово! ✅
```

### Шаг 2: Обновить API endpoints (15 минут)

Файл: `app/api/__init__.py` или где находятся API routes для партнёров

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import date

router = APIRouter(prefix="/api/partner", tags=["partner"])

# ============================================
# MODELS
# ============================================

class ProductCreate(BaseModel):
    """Request model for creating/updating product."""
    category: str
    title: str
    description: Optional[str] = None
    original_price: int  # в копейках/тийинах
    discount_price: int  # в копейках/тийинах  
    unit: str = "шт"
    stock_quantity: int = 0
    expiry_date: Optional[date] = None
    photo_id: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "category": "fruits",
                "title": "Яблоки красные",
                "description": "Свежие импортные яблоки",
                "original_price": 20000,
                "discount_price": 17000,
                "unit": "кг",
                "stock_quantity": 50,
                "expiry_date": "2024-12-25",
                "photo_id": "AgACAgIAAxkBAAI..."
            }
        }


class CancelOrderRequest(BaseModel):
    """Request model for canceling order."""
    reason: str  # out_of_stock, cant_fulfill, customer_request, technical_issue, other
    comment: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "reason": "out_of_stock",
                "comment": "Товар закончился утром"
            }
        }


# ============================================
# ENDPOINTS
# ============================================

@router.post("/products")
async def create_product(product: ProductCreate, user_id: int):
    """Create new product (offer)."""
    
    # Валидация категории
    valid_categories = ['bakery', 'dairy', 'meat', 'fruits', 'vegetables', 
                       'drinks', 'snacks', 'frozen', 'other']
    if product.category not in valid_categories:
        raise HTTPException(400, f"Invalid category. Must be one of: {', '.join(valid_categories)}")
    
    # Валидация единицы измерения
    valid_units = ['шт', 'кг', 'л', 'г', 'мл', 'упак']
    if product.unit not in valid_units:
        raise HTTPException(400, f"Invalid unit. Must be one of: {', '.join(valid_units)}")
    
    # Валидация цен
    if product.original_price <= 0:
        raise HTTPException(400, "Original price must be > 0")
    if product.discount_price < 0 or product.discount_price > product.original_price:
        raise HTTPException(400, "Discount price must be between 0 and original price")
    
    # Получить магазин пользователя
    from database import db
    stores = db.get_user_accessible_stores(user_id)
    if not stores:
        raise HTTPException(404, "No stores found for user")
    
    store_id = stores[0].get('store_id')
    
    # Создать товар
    try:
        offer_id = db.add_offer(
            store_id=store_id,
            title=product.title,
            description=product.description,
            original_price=product.original_price,
            discount_price=product.discount_price,
            quantity=product.stock_quantity,  # temporary mapping
            expiry_date=str(product.expiry_date) if product.expiry_date else None,
            photo_id=product.photo_id,
            unit=product.unit,
            category=product.category
        )
        
        # Обновить stock_quantity отдельно
        db.execute(
            "UPDATE offers SET stock_quantity = %s WHERE offer_id = %s",
            (product.stock_quantity, offer_id)
        )
        
        return {
            "success": True,
            "offer_id": offer_id,
            "message": "Product created successfully"
        }
    except Exception as e:
        logger.error(f"Error creating product: {e}")
        raise HTTPException(500, "Failed to create product")


@router.put("/products/{offer_id}")
async def update_product(offer_id: int, product: ProductCreate, user_id: int):
    """Update existing product."""
    
    # Проверка прав доступа
    from database import db
    offer = db.get_offer(offer_id)
    if not offer:
        raise HTTPException(404, "Product not found")
    
    stores = db.get_user_accessible_stores(user_id)
    store_ids = [s.get('store_id') for s in stores]
    
    if offer.get('store_id') not in store_ids:
        raise HTTPException(403, "Access denied")
    
    # Валидация (как в create_product)
    valid_categories = ['bakery', 'dairy', 'meat', 'fruits', 'vegetables', 
                       'drinks', 'snacks', 'frozen', 'other']
    if product.category not in valid_categories:
        raise HTTPException(400, f"Invalid category")
    
    valid_units = ['шт', 'кг', 'л', 'г', 'мл', 'упак']
    if product.unit not in valid_units:
        raise HTTPException(400, f"Invalid unit")
    
    # Обновить товар
    try:
        db.execute(
            """
            UPDATE offers 
            SET title = %s,
                description = %s,
                original_price = %s,
                discount_price = %s,
                quantity = %s,
                stock_quantity = %s,
                expiry_date = %s,
                photo_id = %s,
                unit = %s,
                category = %s
            WHERE offer_id = %s
            """,
            (
                product.title,
                product.description,
                product.original_price,
                product.discount_price,
                product.stock_quantity,  # также обновить quantity для совместимости
                product.stock_quantity,
                str(product.expiry_date) if product.expiry_date else None,
                product.photo_id,
                product.unit,
                product.category,
                offer_id
            )
        )
        
        return {
            "success": True,
            "message": "Product updated successfully"
        }
    except Exception as e:
        logger.error(f"Error updating product: {e}")
        raise HTTPException(500, "Failed to update product")


@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: int, cancel_data: CancelOrderRequest, user_id: int):
    """Cancel order with reason."""
    
    from database import db
    
    # Валидация причины
    valid_reasons = ['out_of_stock', 'cant_fulfill', 'customer_request', 
                    'technical_issue', 'other']
    if cancel_data.reason not in valid_reasons:
        raise HTTPException(400, f"Invalid reason. Must be one of: {', '.join(valid_reasons)}")
    
    # Проверка заказа
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    
    # Проверка прав
    stores = db.get_user_accessible_stores(user_id)
    store_ids = [s.get('store_id') for s in stores]
    
    if order.get('store_id') not in store_ids:
        raise HTTPException(403, "Access denied")
    
    # Проверка статуса
    if order.get('order_status') not in ['pending', 'new']:
        raise HTTPException(400, "Order cannot be cancelled at this stage")
    
    # Отменить заказ
    try:
        db.execute(
            """
            UPDATE orders 
            SET order_status = 'cancelled',
                cancel_reason = %s,
                cancel_comment = %s
            WHERE order_id = %s
            """,
            (cancel_data.reason, cancel_data.comment, order_id)
        )
        
        # Отправить уведомление клиенту
        customer_id = order.get('user_id')
        if customer_id:
            reason_text = {
                'out_of_stock': 'Товар закончился',
                'cant_fulfill': 'Не успеваем выполнить',
                'customer_request': 'По вашей просьбе',
                'technical_issue': 'Технические неполадки',
                'other': 'Другая причина'
            }
            
            message = f"❌ Заказ #{order_id} отменён\\n"
            message += f"Причина: {reason_text.get(cancel_data.reason, 'Не указана')}\\n"
            if cancel_data.comment:
                message += f"Комментарий: {cancel_data.comment}"
            
            try:
                from bot import bot
                await bot.send_message(customer_id, message)
            except Exception as e:
                logger.warning(f"Failed to notify customer: {e}")
        
        return {
            "success": True,
            "message": "Order cancelled successfully"
        }
    except Exception as e:
        logger.error(f"Error cancelling order: {e}")
        raise HTTPException(500, "Failed to cancel order")


@router.get("/products")
async def get_products(user_id: int):
    """Get all products for user's stores."""
    from database import db
    
    stores = db.get_user_accessible_stores(user_id)
    if not stores:
        return []
    
    store_ids = [s.get('store_id') for s in stores]
    
    # Получить все товары
    products = []
    for store_id in store_ids:
        offers = db.get_store_offers(store_id)
        products.extend(offers)
    
    # Добавить вычисляемые поля для фронтенда
    for product in products:
        # Рассчитать процент скидки
        original = product.get('original_price', 0)
        discount = product.get('discount_price', 0)
        if original > 0:
            product['discount'] = round((1 - discount / original) * 100)
        else:
            product['discount'] = 0
        
        # Добавить stock_quantity если нет
        if 'stock_quantity' not in product:
            product['stock_quantity'] = product.get('quantity', 0)
    
    return products
```

### Шаг 3: Тестирование (10 минут)

```bash
# 1. Проверить миграцию БД
psql -d fudly_db -c "\\d offers"
# Должны увидеть: stock_quantity, category, unit, expiry_date

psql -d fudly_db -c "\\d orders"
# Должны увидеть: cancel_reason, cancel_comment

# 2. Запустить бота
python bot.py
# Проверить, что бот стартует без ошибок

# 3. Создать тестовый товар через бота
# Проверить, что все 8 шагов работают

# 4. Открыть веб-панель
# http://localhost:8000/partner-panel/

# 5. Добавить товар через панель
# Проверить, что все поля сохраняются

# 6. Проверить в БД
psql -d fudly_db -c "SELECT offer_id, category, unit, stock_quantity FROM offers ORDER BY offer_id DESC LIMIT 5;"
```

---

## 🔄 Обратная совместимость

### ✅ Бот продолжит работать:
- Функция `db.add_offer()` уже принимает `category`, `unit`, `expiry_date`
- Старые товары получат `stock_quantity = 0` (default)
- Веб-панель будет использовать те же поля

### ✅ Данные сохраняются:
- `quantity` и `stock_quantity` синхронизируются
- Старые записи без категории получат `'other'`
- Все существующие товары останутся видимыми

### ✅ API совместим:
- GET `/api/partner/products` вернёт все поля
- Старые клиенты получат данные как раньше
- Новые клиенты получат дополнительные поля

---

## 📊 Проверка после миграции

```sql
-- 1. Проверить структуру offers
SELECT column_name, data_type, column_default 
FROM information_schema.columns 
WHERE table_name = 'offers';

-- 2. Проверить данные
SELECT 
    offer_id,
    title,
    category,
    unit,
    original_price,
    discount_price,
    stock_quantity,
    expiry_date
FROM offers 
ORDER BY offer_id DESC 
LIMIT 10;

-- 3. Проверить индексы
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'offers';

-- 4. Проверить заказы
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'orders' 
  AND column_name IN ('cancel_reason', 'cancel_comment');
```

---

## 🎯 Что получим после миграции

### Frontend (уже готово ✅):
- Полная форма с 6 полями
- Фильтры по категориям
- Отмена с причиной
- Keyboard navigation

### Backend (после миграции ✅):
- API принимает все новые поля
- Валидация данных
- Обратная совместимость
- Аналитика причин отмен

### Database (после SQL ✅):
- Новые поля в offers
- Индексы для быстрой фильтрации
- История отмен заказов

---

## ⚠️ Риски и решения

### Риск 1: Существующие товары без категории
**Решение:** Default значение `'other'`
```sql
UPDATE offers SET category = 'other' WHERE category IS NULL;
```

### Риск 2: stock_quantity vs quantity
**Решение:** Синхронизировать оба поля
```sql
UPDATE offers SET stock_quantity = quantity WHERE stock_quantity IS NULL;
```

### Риск 3: Старые API клиенты
**Решение:** Поля опциональные, старые клиенты игнорируют
```python
# В API ответе всегда включать и старые, и новые поля
{
    "quantity": 10,           # Для старых клиентов
    "stock_quantity": 10,     # Для новых клиентов
    "category": "fruits"      # Новое поле (опционально для старых)
}
```

---

## 🚀 Порядок развёртывания

1. **Backup БД** (обязательно!)
   ```bash
   pg_dump fudly_db > backup_before_v22_$(date +%Y%m%d_%H%M%S).sql
   ```

2. **Применить SQL миграцию**
   ```bash
   psql -d fudly_db -f migrations/v22_add_fields.sql
   ```

3. **Обновить код бота** (уже готов, ничего менять не нужно)
   
4. **Добавить API endpoints** (код выше)

5. **Перезапустить сервисы**
   ```bash
   systemctl restart fudly-bot
   systemctl restart fudly-api
   ```

6. **Проверить работу**
   - Бот создаёт товары ✅
   - Панель создаёт товары ✅
   - Фильтры работают ✅
   - Отмена с причиной работает ✅

---

## ✅ Checklist развёртывания

- [ ] Создан backup БД
- [ ] Применена SQL миграция
- [ ] Проверены индексы
- [ ] Добавлены API endpoints
- [ ] Обновлены Pydantic модели
- [ ] Перезапущен бот
- [ ] Перезапущен API сервер
- [ ] Протестирован бот (создание товара)
- [ ] Протестирована панель (создание товара)
- [ ] Протестированы фильтры
- [ ] Протестирована отмена заказа
- [ ] Проверены логи на ошибки

---

## 📞 Поддержка

**Если что-то пошло не так:**

1. **Откатить БД:**
   ```bash
   psql -d fudly_db < backup_before_v22_*.sql
   ```

2. **Проверить логи:**
   ```bash
   tail -f /var/log/fudly-bot.log
   tail -f /var/log/fudly-api.log
   ```

3. **Проверить БД:**
   ```bash
   psql -d fudly_db -c "SELECT * FROM offers LIMIT 1;"
   ```

---

**Версия:** v22.0  
**Дата:** 18 декабря 2024  
**Время миграции:** ~30 минут  
**Риск:** 🟢 Низкий (обратно совместимо)  
**Статус:** ✅ Готово к развёртыванию
