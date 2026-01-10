-- v27: Scale prices from sums to kopeks where they were stored without *100.
-- Safe-guard: multiply only values that look like "sums" (< 1,000,000).
-- Idempotent: rows already in kopeks (>= 1,000,000) stay unchanged.

BEGIN;

-- Offers prices
UPDATE offers
SET
    original_price = CASE
        WHEN original_price IS NOT NULL AND original_price < 1000000 THEN original_price * 100
        ELSE original_price
    END,
    discount_price = CASE
        WHEN discount_price IS NOT NULL AND discount_price < 1000000 THEN discount_price * 100
        ELSE discount_price
    END;

-- Store delivery/min order prices
UPDATE stores
SET
    delivery_price = CASE
        WHEN delivery_price IS NOT NULL AND delivery_price < 1000000 THEN delivery_price * 100
        ELSE delivery_price
    END,
    min_order_amount = CASE
        WHEN min_order_amount IS NOT NULL AND min_order_amount < 1000000 THEN min_order_amount * 100
        ELSE min_order_amount
    END;

COMMIT;
