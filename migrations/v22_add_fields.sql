-- ================================================
-- МИГРАЦИЯ v22.0 - Безопасное добавление полей
-- Дата: 18 декабря 2024
-- Риск: НИЗКИЙ (все поля с DEFAULT значениями)
-- ================================================

BEGIN;

-- ================================================
-- 1. OFFERS TABLE - Добавить stock_quantity
-- ================================================

-- Добавить поле stock_quantity
ALTER TABLE offers 
ADD COLUMN IF NOT EXISTS stock_quantity INTEGER DEFAULT 0;

-- Синхронизировать с quantity для существующих записей
UPDATE offers 
SET stock_quantity = COALESCE(quantity, 0)
WHERE stock_quantity = 0 OR stock_quantity IS NULL;

-- Комментарий для документации
COMMENT ON COLUMN offers.stock_quantity IS 'Количество товара в наличии (v22.0)';

-- ================================================
-- 2. ORDERS TABLE - Причина отмены
-- ================================================

-- Добавить поле причины отмены
ALTER TABLE orders 
ADD COLUMN IF NOT EXISTS cancel_reason VARCHAR(50);

-- Добавить поле комментария к отмене
ALTER TABLE orders 
ADD COLUMN IF NOT EXISTS cancel_comment TEXT;

-- Комментарии
COMMENT ON COLUMN orders.cancel_reason IS 'Причина отмены: out_of_stock, cant_fulfill, customer_request, technical_issue, other (v22.0)';
COMMENT ON COLUMN orders.cancel_comment IS 'Дополнительный комментарий к отмене (v22.0)';

-- ================================================
-- 3. ИНДЕКСЫ - Для быстрой фильтрации
-- ================================================

-- Индекс по категории (для фильтра категорий)
CREATE INDEX IF NOT EXISTS idx_offers_category 
ON offers(category);

-- Индекс по единице измерения
CREATE INDEX IF NOT EXISTS idx_offers_unit 
ON offers(unit);

-- Индекс по количеству в наличии (для фильтра "В наличии / Нет")
CREATE INDEX IF NOT EXISTS idx_offers_stock 
ON offers(stock_quantity);

-- Индекс по статусу (уже может быть)
CREATE INDEX IF NOT EXISTS idx_offers_status 
ON offers(status);

-- Индекс по причине отмены (для аналитики)
CREATE INDEX IF NOT EXISTS idx_orders_cancel_reason 
ON orders(cancel_reason);

-- Составной индекс для фильтрации по категории + статусу
CREATE INDEX IF NOT EXISTS idx_offers_category_status 
ON offers(category, status);

-- ================================================
-- 4. ПРОВЕРКА ЦЕЛОСТНОСТИ
-- ================================================

-- Проверить, что у всех товаров есть category
UPDATE offers 
SET category = 'other' 
WHERE category IS NULL OR category = '';

-- Проверить, что у всех товаров есть unit
UPDATE offers 
SET unit = 'шт' 
WHERE unit IS NULL OR unit = '';

-- Убедиться, что stock_quantity >= 0
UPDATE offers 
SET stock_quantity = 0 
WHERE stock_quantity < 0;

-- ================================================
-- 5. CONSTRAINTS - Валидация данных
-- ================================================

-- Проверка валидных категорий
ALTER TABLE offers 
DROP CONSTRAINT IF EXISTS check_valid_category;

ALTER TABLE offers 
ADD CONSTRAINT check_valid_category 
CHECK (category IN ('bakery', 'dairy', 'meat', 'fruits', 'vegetables', 'drinks', 'snacks', 'frozen', 'other'));

-- Проверка валидных единиц измерения
ALTER TABLE offers 
DROP CONSTRAINT IF EXISTS check_valid_unit;

ALTER TABLE offers 
ADD CONSTRAINT check_valid_unit 
CHECK (unit IN ('шт', 'кг', 'л', 'г', 'мл', 'упак'));

-- Проверка stock_quantity >= 0
ALTER TABLE offers 
DROP CONSTRAINT IF EXISTS check_stock_non_negative;

ALTER TABLE offers 
ADD CONSTRAINT check_stock_non_negative 
CHECK (stock_quantity >= 0);

-- Проверка валидных причин отмены
ALTER TABLE orders 
DROP CONSTRAINT IF EXISTS check_valid_cancel_reason;

ALTER TABLE orders 
ADD CONSTRAINT check_valid_cancel_reason 
CHECK (
    cancel_reason IS NULL 
    OR cancel_reason IN ('out_of_stock', 'cant_fulfill', 'customer_request', 'technical_issue', 'other')
);

-- ================================================
-- 6. СТАТИСТИКА И АНАЛИТИКА
-- ================================================

-- Обновить статистику для оптимизатора
ANALYZE offers;
ANALYZE orders;

-- ================================================
-- 7. ПРОВЕРКА РЕЗУЛЬТАТОВ
-- ================================================

-- Вывести структуру offers
DO $$
DECLARE
    rec RECORD;
BEGIN
    RAISE NOTICE '=== OFFERS TABLE STRUCTURE ===';
    FOR rec IN 
        SELECT column_name, data_type, column_default
        FROM information_schema.columns
        WHERE table_name = 'offers'
        ORDER BY ordinal_position
    LOOP
        RAISE NOTICE 'Column: % | Type: % | Default: %', rec.column_name, rec.data_type, rec.column_default;
    END LOOP;
END $$;

-- Вывести статистику товаров
DO $$
DECLARE
    total_offers INTEGER;
    with_category INTEGER;
    with_stock INTEGER;
BEGIN
    SELECT COUNT(*) INTO total_offers FROM offers;
    SELECT COUNT(*) INTO with_category FROM offers WHERE category IS NOT NULL;
    SELECT COUNT(*) INTO with_stock FROM offers WHERE stock_quantity > 0;
    
    RAISE NOTICE '=== OFFERS STATISTICS ===';
    RAISE NOTICE 'Total offers: %', total_offers;
    RAISE NOTICE 'With category: %', with_category;
    RAISE NOTICE 'With stock: %', with_stock;
END $$;

-- Вывести структуру orders
DO $$
DECLARE
    rec RECORD;
BEGIN
    RAISE NOTICE '=== ORDERS TABLE STRUCTURE ===';
    FOR rec IN 
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'orders' 
          AND column_name IN ('cancel_reason', 'cancel_comment')
    LOOP
        RAISE NOTICE 'Column: % | Type: %', rec.column_name, rec.data_type;
    END LOOP;
END $$;

-- Вывести индексы
DO $$
DECLARE
    rec RECORD;
BEGIN
    RAISE NOTICE '=== INDEXES ===';
    FOR rec IN 
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename IN ('offers', 'orders')
          AND indexname LIKE 'idx_%'
        ORDER BY tablename, indexname
    LOOP
        RAISE NOTICE 'Index: % | Definition: %', rec.indexname, rec.indexdef;
    END LOOP;
END $$;

COMMIT;

-- ================================================
-- ✅ МИГРАЦИЯ ЗАВЕРШЕНА
-- ================================================

SELECT 'v22.0 migration completed successfully! ✅' AS status;

-- Проверить результат:
-- SELECT offer_id, title, category, unit, stock_quantity FROM offers LIMIT 5;
-- SELECT order_id, order_status, cancel_reason, cancel_comment FROM orders WHERE cancel_reason IS NOT NULL LIMIT 5;
