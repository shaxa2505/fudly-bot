-- ============================================
-- Migration v24: Migrate bookings to orders
-- ============================================
-- Date: 2025-12-18
-- Purpose: Consolidate bookings table into orders table
--          All pickup orders will be in orders table with order_type='pickup'
--          Bookings table will be archived for history
-- ============================================

-- Step 1: Add missing fields to orders table for bookings data
ALTER TABLE orders ADD COLUMN IF NOT EXISTS pickup_code VARCHAR(20);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS pickup_time TIMESTAMP;

-- Step 2: Migrate bookings to orders table
INSERT INTO orders (
    user_id,
    store_id,
    offer_id,
    quantity,
    order_type,
    order_status,
    total_price,
    pickup_code,
    pickup_time,
    created_at,
    updated_at
)
SELECT 
    b.user_id,
    COALESCE(b.store_id, o.store_id) as store_id,  -- Use bookings.store_id if exists, else from offers
    b.offer_id,
    b.quantity,
    'pickup' as order_type,
    b.status as order_status,
    (o.discount_price * b.quantity) as total_price,
    b.booking_code as pickup_code,
    CASE 
        WHEN b.pickup_time IS NOT NULL AND b.pickup_time != '' 
        THEN b.pickup_time::TIMESTAMP 
        ELSE NULL 
    END as pickup_time,
    b.created_at,
    COALESCE(b.updated_at, CURRENT_TIMESTAMP) as updated_at
FROM bookings b
JOIN offers o ON b.offer_id = o.offer_id
WHERE NOT EXISTS (
    -- Prevent duplicates if migration run multiple times
    SELECT 1 FROM orders ord
    WHERE ord.user_id = b.user_id
    AND ord.offer_id = b.offer_id
    AND ord.pickup_code = b.booking_code
);

-- Step 3: Archive bookings table (rename, don't delete)
ALTER TABLE bookings RENAME TO bookings_archive;

-- Step 4: Add index for pickup orders
CREATE INDEX IF NOT EXISTS idx_orders_pickup_code 
ON orders(pickup_code) 
WHERE pickup_code IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_orders_pickup_time 
ON orders(pickup_time) 
WHERE pickup_time IS NOT NULL;

-- Step 5: Update sequence if needed (orders table ID might need adjustment)
SELECT setval(pg_get_serial_sequence('orders', 'order_id'), 
    COALESCE((SELECT MAX(order_id) FROM orders), 1), true);

-- Verification queries
-- SELECT COUNT(*) as bookings_migrated FROM bookings_archive;
-- SELECT COUNT(*) as pickup_orders FROM orders WHERE order_type = 'pickup';
-- SELECT order_type, COUNT(*) FROM orders GROUP BY order_type;
