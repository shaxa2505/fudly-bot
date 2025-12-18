-- ================================================
-- МИГРАЦИЯ v23.1 - Дополнительные индексы производительности  
-- Дата: 18 декабря 2024
-- Риск: НИЗКИЙ (только композитные индексы)
-- ================================================

BEGIN;

-- Composite index for partner panel
CREATE INDEX IF NOT EXISTS idx_bookings_store_status_time 
ON bookings(store_id, status, created_at DESC);

-- Rating lookups
CREATE INDEX IF NOT EXISTS idx_ratings_user_booking_unique 
ON ratings(user_id, booking_id);

CREATE INDEX IF NOT EXISTS idx_ratings_store_date 
ON ratings(store_id, created_at DESC);

-- Search history with time window
CREATE INDEX IF NOT EXISTS idx_search_history_user_time 
ON search_history(user_id, created_at DESC);

-- Pickup slots availability
CREATE INDEX IF NOT EXISTS idx_pickup_slots_store_date_available 
ON pickup_slots(store_id, date_iso);

-- Orders analytics
CREATE INDEX IF NOT EXISTS idx_orders_completed_date 
ON orders(created_at DESC)
WHERE status = 'completed';

CREATE INDEX IF NOT EXISTS idx_orders_store_status 
ON orders(store_id, status, created_at DESC);

-- Store admins
CREATE INDEX IF NOT EXISTS idx_store_admins_user_store 
ON store_admins(user_id, store_id);

-- Store payment integrations
CREATE INDEX IF NOT EXISTS idx_store_payment_integrations_lookup 
ON store_payment_integrations(store_id, provider);

-- Analyze tables
ANALYZE bookings;
ANALYZE orders;
ANALYZE ratings;
ANALYZE search_history;
ANALYZE pickup_slots;
ANALYZE store_admins;
ANALYZE store_payment_integrations;

COMMIT;
