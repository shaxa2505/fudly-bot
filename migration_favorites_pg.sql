-- Migration script for PostgreSQL: Change favorites table from offer_id to store_id
-- Run this ONLY if your existing PostgreSQL database has favorites(offer_id).
-- If starting fresh, the database_pg.py already creates it correctly.

-- WARNING: This migration will DELETE existing favorites data!
-- If you need to preserve data, first backup favorites table.

BEGIN;

-- Option 1: Drop and recreate (simplest, loses data)
DROP TABLE IF EXISTS favorites CASCADE;

CREATE TABLE favorites (
    favorite_id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    store_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (store_id) REFERENCES stores(store_id),
    UNIQUE(user_id, store_id)
);

CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id);
CREATE INDEX IF NOT EXISTS idx_favorites_store ON favorites(store_id);

COMMIT;

-- Option 2: If you want to TRY migrating data (offer -> store mapping)
-- Uncomment below and adjust logic if needed:
-- BEGIN;
-- ALTER TABLE favorites RENAME COLUMN offer_id TO store_id_temp;
-- ALTER TABLE favorites ADD COLUMN store_id INTEGER;
-- 
-- -- Attempt to populate store_id from offers table
-- UPDATE favorites f
-- SET store_id = (SELECT o.store_id FROM offers o WHERE o.offer_id = f.store_id_temp LIMIT 1);
-- 
-- -- Drop old column and constraint
-- ALTER TABLE favorites DROP COLUMN store_id_temp;
-- ALTER TABLE favorites ALTER COLUMN store_id SET NOT NULL;
-- 
-- -- Recreate unique constraint
-- ALTER TABLE favorites DROP CONSTRAINT IF EXISTS favorites_user_id_offer_id_key;
-- ALTER TABLE favorites ADD CONSTRAINT favorites_user_id_store_id_key UNIQUE(user_id, store_id);
-- 
-- CREATE INDEX IF NOT EXISTS idx_favorites_store ON favorites(store_id);
-- COMMIT;
