-- Migration: Add CASCADE DELETE to foreign keys
-- This allows deleting stores without manually deleting offers/orders first

-- 1. Drop existing foreign key constraints and recreate with CASCADE
-- offers.store_id -> stores.id
ALTER TABLE offers DROP CONSTRAINT IF EXISTS offers_store_id_fkey;
ALTER TABLE offers ADD CONSTRAINT offers_store_id_fkey 
    FOREIGN KEY (store_id) REFERENCES stores(id) ON DELETE CASCADE;

-- 2. orders.store_id -> stores.id  
ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_store_id_fkey;
ALTER TABLE orders ADD CONSTRAINT orders_store_id_fkey 
    FOREIGN KEY (store_id) REFERENCES stores(id) ON DELETE CASCADE;

-- 3. orders.offer_id -> offers.id
ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_offer_id_fkey;
ALTER TABLE orders ADD CONSTRAINT orders_offer_id_fkey 
    FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE SET NULL;

-- 4. bookings.store_id -> stores.id
ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_store_id_fkey;
ALTER TABLE bookings ADD CONSTRAINT bookings_store_id_fkey 
    FOREIGN KEY (store_id) REFERENCES stores(id) ON DELETE CASCADE;

-- 5. bookings.offer_id -> offers.id
ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_offer_id_fkey;
ALTER TABLE bookings ADD CONSTRAINT bookings_offer_id_fkey 
    FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE SET NULL;

-- 6. cart_items.offer_id -> offers.id
ALTER TABLE cart_items DROP CONSTRAINT IF EXISTS cart_items_offer_id_fkey;
ALTER TABLE cart_items ADD CONSTRAINT cart_items_offer_id_fkey 
    FOREIGN KEY (offer_id) REFERENCES offers(id) ON DELETE CASCADE;

-- 7. favorites -> stores
ALTER TABLE favorites DROP CONSTRAINT IF EXISTS favorites_store_id_fkey;
ALTER TABLE favorites ADD CONSTRAINT favorites_store_id_fkey 
    FOREIGN KEY (store_id) REFERENCES stores(id) ON DELETE CASCADE;

-- 8. store_ratings -> stores
ALTER TABLE store_ratings DROP CONSTRAINT IF EXISTS store_ratings_store_id_fkey;
ALTER TABLE store_ratings ADD CONSTRAINT store_ratings_store_id_fkey 
    FOREIGN KEY (store_id) REFERENCES stores(id) ON DELETE CASCADE;

-- 9. payment_cards -> stores (if exists)
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'payment_cards') THEN
        ALTER TABLE payment_cards DROP CONSTRAINT IF EXISTS payment_cards_store_id_fkey;
        ALTER TABLE payment_cards ADD CONSTRAINT payment_cards_store_id_fkey 
            FOREIGN KEY (store_id) REFERENCES stores(id) ON DELETE CASCADE;
    END IF;
END $$;

SELECT 'CASCADE DELETE constraints added successfully' AS result;
