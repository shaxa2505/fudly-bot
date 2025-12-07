-- Migration: Add partner_reminder_sent column to bookings table
-- Description: Track if partner has received reminder about pending booking (30+ min)
-- Date: 2025-12-08

ALTER TABLE bookings
ADD COLUMN IF NOT EXISTS partner_reminder_sent INTEGER DEFAULT 0;

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_bookings_partner_reminder
ON bookings(status, partner_reminder_sent, created_at)
WHERE status = 'pending' AND partner_reminder_sent = 0;

COMMENT ON COLUMN bookings.partner_reminder_sent IS 'Flag indicating if partner received reminder about pending booking (0=not sent, 1=sent)';
