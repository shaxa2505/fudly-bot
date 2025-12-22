-- Add region/district fields for store-level location filtering
ALTER TABLE stores ADD COLUMN IF NOT EXISTS region TEXT;
ALTER TABLE stores ADD COLUMN IF NOT EXISTS district TEXT;

CREATE INDEX IF NOT EXISTS idx_stores_region ON stores(region);
CREATE INDEX IF NOT EXISTS idx_stores_district ON stores(district);
