-- Migration: Add CASCADE DELETE to foreign keys
-- This allows deleting stores without manually deleting offers/orders first
--
-- IMPORTANT: таблицы и ключи приведены в соответствие с текущей
-- схемой проекта, где используется stores.store_id и offers.offer_id.

-- 1. offers.store_id -> stores.store_id
ALTER TABLE offers DROP CONSTRAINT IF EXISTS offers_store_id_fkey;
ALTER TABLE offers ADD CONSTRAINT offers_store_id_fkey
    FOREIGN KEY (store_id) REFERENCES stores(store_id) ON DELETE CASCADE;

-- 2. orders.store_id -> stores.store_id
ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_store_id_fkey;
ALTER TABLE orders ADD CONSTRAINT orders_store_id_fkey
    FOREIGN KEY (store_id) REFERENCES stores(store_id) ON DELETE CASCADE;

-- 3. orders.offer_id -> offers.offer_id
ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_offer_id_fkey;
ALTER TABLE orders ADD CONSTRAINT orders_offer_id_fkey
    FOREIGN KEY (offer_id) REFERENCES offers(offer_id) ON DELETE SET NULL;

-- 4. bookings.store_id -> stores.store_id
ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_store_id_fkey;
ALTER TABLE bookings ADD CONSTRAINT bookings_store_id_fkey
    FOREIGN KEY (store_id) REFERENCES stores(store_id) ON DELETE CASCADE;

-- 5. bookings.offer_id -> offers.offer_id
ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_offer_id_fkey;
ALTER TABLE bookings ADD CONSTRAINT bookings_offer_id_fkey
    FOREIGN KEY (offer_id) REFERENCES offers(offer_id) ON DELETE SET NULL;

-- 6. favorites.store_id -> stores.store_id
ALTER TABLE favorites DROP CONSTRAINT IF EXISTS favorites_store_id_fkey;
ALTER TABLE favorites ADD CONSTRAINT favorites_store_id_fkey
    FOREIGN KEY (store_id) REFERENCES stores(store_id) ON DELETE CASCADE;

-- NOTE:
--   В проекте нет таблиц cart_items, store_ratings, payment_cards
--   с согласованной схемой, поэтому они исключены из миграции,
--   чтобы не ломать существующую базу. Если такие таблицы появятся
--   в будущем, для них нужно будет сделать отдельную Alembic-миграцию.

SELECT 'CASCADE DELETE constraints (offers/orders/bookings/favorites) added successfully' AS result;
