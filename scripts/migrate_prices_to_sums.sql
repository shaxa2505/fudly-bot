-- Normalize stored prices to sums (major units).
-- Assumes offers were stored in kopeks previously.
BEGIN;

-- Offers: kopeks -> sums
UPDATE offers
SET original_price = CASE
        WHEN original_price IS NULL THEN NULL
        ELSE ROUND(original_price / 100.0)::int
    END,
    discount_price = CASE
        WHEN discount_price IS NULL THEN NULL
        ELSE ROUND(discount_price / 100.0)::int
    END;

-- Stores: only convert if values look like kopeks (>= 100000).
UPDATE stores
SET delivery_price = ROUND(delivery_price / 100.0)::int
WHERE delivery_price >= 100000;

UPDATE stores
SET min_order_amount = ROUND(min_order_amount / 100.0)::int
WHERE min_order_amount >= 100000;

-- Orders (single-offer): recompute totals in sums using updated offers/stores.
UPDATE orders o
SET total_price = calc.total_price
FROM (
    SELECT
        o2.order_id,
        (COALESCE(off.discount_price, 0) * COALESCE(o2.quantity, 1))
        + CASE
              WHEN COALESCE(o2.order_type, '') = 'delivery'
                   OR (o2.delivery_address IS NOT NULL AND o2.delivery_address <> '')
              THEN COALESCE(s.delivery_price, 0)
              ELSE 0
          END AS total_price
    FROM orders o2
    JOIN offers off ON off.offer_id = o2.offer_id
    LEFT JOIN stores s ON s.store_id = o2.store_id
    WHERE COALESCE(o2.is_cart_order, 0) = 0
) AS calc
WHERE o.order_id = calc.order_id;

-- Bookings: normalize delivery_cost if it looks like kopeks.
UPDATE bookings
SET delivery_cost = ROUND(delivery_cost / 100.0)::int
WHERE delivery_cost >= 100000;

COMMIT;
