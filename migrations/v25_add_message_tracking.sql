-- ============================================
-- Migration v25: Add message tracking fields
-- ============================================
-- Date: 2025-12-21
-- Purpose: Add fields to track customer and seller notification message IDs
--          for live message editing (reduces spam, improves UX)
-- ============================================

-- Add customer_message_id to orders table
ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_message_id BIGINT;

-- Add seller_message_id to orders table
ALTER TABLE orders ADD COLUMN IF NOT EXISTS seller_message_id BIGINT;

-- Add customer_message_id to bookings_archive (if bookings still exist)
ALTER TABLE IF EXISTS bookings ADD COLUMN IF NOT EXISTS customer_message_id BIGINT;
ALTER TABLE IF EXISTS bookings ADD COLUMN IF NOT EXISTS seller_message_id BIGINT;

-- Add to archived bookings too for consistency
ALTER TABLE IF EXISTS bookings_archive ADD COLUMN IF NOT EXISTS customer_message_id BIGINT;
ALTER TABLE IF EXISTS bookings_archive ADD COLUMN IF NOT EXISTS seller_message_id BIGINT;

-- Add indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_orders_customer_msg 
ON orders(customer_message_id) 
WHERE customer_message_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_orders_seller_msg 
ON orders(seller_message_id) 
WHERE seller_message_id IS NOT NULL;

-- Verification
-- SELECT 
--   COUNT(*) as total_orders,
--   COUNT(customer_message_id) as with_customer_msg,
--   COUNT(seller_message_id) as with_seller_msg
-- FROM orders;
