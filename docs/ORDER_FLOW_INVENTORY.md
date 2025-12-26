# Order Flow Inventory (Creation + Status Updates)

This document lists every known entry point for creating or updating orders,
and a file-by-file migration plan to make UnifiedOrderService the only path.

## Canonical Path (Selected)

- Source of truth: `app/services/unified_order_service.py`
- DB entrypoints: `database_pg_module/mixins/orders.py:create_cart_order*`
- Callbacks: `handlers/common/unified_order_handlers.py` (seller + customer)

## Order Creation Entry Points (Runtime)

| File | Function / Endpoint | Flow | Current Call | Notes |
| --- | --- | --- | --- | --- |
| `handlers/bookings/customer.py` | `create_booking()` | Bot, pickup (single) | `db.create_cart_order(...)` | Bypasses UnifiedOrderService, sends partner notification manually. Also emits both `order_confirm_` and `booking_confirm_` callbacks. |
| `handlers/customer/cart/checkout.py` | `cart_checkout()` | Bot, pickup (cart) | `UnifiedOrderService.create_order(...)` | Canonical, ok. |
| `handlers/customer/cart/payment.py` | `payment_proof` flow | Bot, delivery (cart) | `UnifiedOrderService.create_order(...)` + `db.update_payment_status(...)` | Canonical creation, payment proof stored after. |
| `handlers/customer/orders/delivery.py` | `dlv_payment_proof()` | Bot, delivery (single) | `UnifiedOrderService.create_order(...)` + `db.update_payment_status(...)` | Canonical creation, payment proof stored after. |
| `app/api/webapp/routes_orders.py` | `POST /orders` | Webapp, pickup + delivery | `UnifiedOrderService.create_order(...)` | Canonical, no fallback. |
| `app/core/webhook_server.py` | `POST /api/v1/orders` | Webhook API, pickup + delivery | `UnifiedOrderService.create_order(...)` | Duplicates `app/api/webapp/routes_orders.py`. |

## Order Creation Entry Points (Legacy / Deprecated)

| File | Function / Endpoint | Flow | Current Call | Notes |
| --- | --- | --- | --- | --- |
| `app/services/order_service.py` | `OrderService.create_order()` | Service | `db.create_cart_order(...)` | Deprecated wrapper, should be removed or moved to compat. |
| `app/services/booking_service.py` | `BookingService.create_booking_with_limit()` | Service | `db.create_booking_atomic(...)` | Deprecated wrapper for bookings table. |
| `database_pg_module/mixins/orders.py` | `create_order()` | DB | direct insert | Non-atomic fallback. Should be removed or blocked. |

## Status Update Entry Points (Runtime)

| File | Function / Callback | Entity | Current Call | Notes |
| --- | --- | --- | --- | --- |
| `handlers/common/unified_order/seller.py` | `booking_confirm_*`, `order_confirm_*`, legacy patterns | order + booking | UnifiedOrderService + direct DB fallback | Accepts many legacy patterns and supports bookings table. |
| `handlers/common/unified_order/seller.py` | `booking_reject_*`, `order_reject_*`, legacy patterns | order + booking | UnifiedOrderService + direct DB fallback | Same issue as above. |
| `handlers/common/unified_order/customer.py` | `customer_received_*` | order | UnifiedOrderService + direct DB fallback | Ok for orders. |
| `handlers/common/unified_order/customer.py` | `booking_received_*` | booking | UnifiedOrderService + direct DB fallback | Legacy bookings path. |
| `handlers/seller/order_management.py` | `confirm_order_`, `cancel_order_`, `confirm_payment_`, `reject_payment_` | order | UnifiedOrderService | Duplicates logic with `handlers/common/unified_order/seller.py`. |
| `handlers/seller/management/orders.py` | booking/order actions | order + booking | UnifiedOrderService | Another seller path with overlapping callbacks. |
| `handlers/admin/delivery_orders.py` | admin confirm/reject | order | UnifiedOrderService | Uses service but depends on init path. |
| `app/api/partner_panel_simple.py` | `/orders/{id}/confirm`, `/orders/{id}/status` | order | UnifiedOrderService | OK, but depends on consistent callbacks in bot. |
| `bot.py` | `order_accept:...` / `order_reject:...` | booking | `db.update_booking_status(...)` | Legacy Mini App callbacks, should be removed once old messages expire. |

## Migration Plan by File (Order of Work)

1) `handlers/bookings/customer.py`
   - Replace direct `db.create_cart_order(...)` with `UnifiedOrderService.create_order(...)`.
   - Remove or gate `booking_confirm_` / `booking_reject_` buttons; emit only `order_confirm_` / `order_reject_`.
   - Remove `notify_partner_new_pickup_order(...)` if UnifiedOrderService already notifies.

2) `handlers/common/unified_order/seller.py`
   - Drop booking patterns from regex and `PREFIX_TO_TYPE`.
   - Remove direct DB fallbacks (`update_order_status`, `update_booking_status`) or keep only under a temporary feature flag.
   - Enforce `entity_type="order"` only.

3) `handlers/common/unified_order/customer.py`
   - Remove `booking_received_*` handler once pickup orders are fully in `orders`.
   - Keep only `customer_received_*` for delivery orders.

4) `bot.py`
   - Remove `order_accept:` / `order_reject:` legacy callbacks or move to compat module.
   - Confirm there are no active messages relying on this pattern.

5) `app/core/webhook_server.py`
   - Decide: deprecate this API in favor of `app/api/webapp/routes_orders.py`, or make it a thin proxy.
   - Remove any remaining fallback to non-unified creation.

6) `handlers/seller/order_management.py`
   - Merge with `handlers/common/unified_order/seller.py` or retire one path to avoid double handling.
   - Keep only one callback router for `order_confirm_` / `order_reject_`.

7) `handlers/seller/management/orders.py`
   - Remove booking-specific actions after pickup orders are fully in `orders`.
   - Consolidate callbacks with the chosen seller handler module.

8) `app/services/order_service.py` and `app/services/booking_service.py`
   - Remove or move to `legacy/` with explicit deprecation warnings.

9) `database_pg_module/mixins/orders.py`
   - Remove or block `create_order()` (non-atomic).
   - Keep only `create_cart_order*()` and ensure it is transactional.

10) Tests and guards
   - Update `tests/test_status_update_guards.py` allowlist to the new callbacks.
   - Add integration tests that create pickup and delivery orders through UnifiedOrderService only.
