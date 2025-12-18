-- ============================================
-- Migration v23: Unify order statuses
-- ============================================
-- Date: 2025-12-18
-- Purpose: Standardize status names across orders and bookings
--          Replace 'confirmed' with 'preparing' everywhere
--          Replace 'new' with 'pending' everywhere
-- ============================================

-- Update orders table
UPDATE orders 
SET order_status = 'preparing' 
WHERE order_status = 'confirmed';

UPDATE orders 
SET order_status = 'pending' 
WHERE order_status = 'new';

-- Update bookings table
UPDATE bookings 
SET status = 'preparing' 
WHERE status = 'confirmed';

UPDATE bookings 
SET status = 'pending' 
WHERE status = 'new';

-- Add check constraints to prevent old statuses
ALTER TABLE orders DROP CONSTRAINT IF EXISTS check_order_status;
ALTER TABLE orders ADD CONSTRAINT check_order_status 
CHECK (order_status IN ('pending', 'preparing', 'ready', 'delivering', 'completed', 'rejected', 'cancelled'));

ALTER TABLE bookings DROP CONSTRAINT IF EXISTS check_booking_status;
ALTER TABLE bookings ADD CONSTRAINT check_booking_status 
CHECK (status IN ('pending', 'preparing', 'ready', 'completed', 'rejected', 'cancelled'));

-- Create index for faster status filtering
CREATE INDEX IF NOT EXISTS idx_orders_status_created 
ON orders(order_status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_bookings_status_created 
ON bookings(status, created_at DESC);

-- Verification queries
-- SELECT order_status, COUNT(*) FROM orders GROUP BY order_status;
-- SELECT status, COUNT(*) FROM bookings GROUP BY status;
