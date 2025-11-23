-- Migration: add pickup fields to bookings table
-- SQLite
-- Run when using SQLite (simple ALTER ADD COLUMN supported)
ALTER TABLE bookings ADD COLUMN pickup_time TEXT;
ALTER TABLE bookings ADD COLUMN pickup_address TEXT;
ALTER TABLE bookings ADD COLUMN pickup_code TEXT;

-- Postgres
-- Run when using Postgres
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS pickup_time TIMESTAMP NULL;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS pickup_address TEXT NULL;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS pickup_code VARCHAR(32) NULL;

-- Notes:
-- - For SQLite, ALTER TABLE ADD COLUMN is limited to adding a column with a default NULL.
-- - If bookings table needs schema transformations, consider creating a new table and copying data.
