# Orders TZ (Mini App + Bot Parity)

## Problem Statement
- The web app blocks orders outside store working hours, but the bot still allows ordering.
- In the web app, delivery fee is not included in totals for Click or cash payments. The bot includes delivery in the total and Click invoice.

## Goals
- Enforce store working hours consistently across Mini App and Bot.
- Include delivery fee in totals and payment amounts for delivery orders in the web app.

## Scope
- Backend validation for order creation (all entry points).
- Web app checkout totals and payment link amount.
- API response totals for delivery orders.

## Non-goals
- Redesigning checkout UX or changing payment providers.
- Altering store schedule configuration UI.

## Requirements
1. Store working hours gating
   - Source of truth is backend validation. Any order creation flow must reject if the store is closed.
   - Applies to all entry points: web app API, bot handlers, and any DB fallback paths.
   - Error response:
     - Web app API returns 409 with a human message that includes working hours when available.
     - Bot shows localized message (`store_closed` / `store_closed_order_time`).
   - Web app UI may also disable checkout when closed, but backend check is mandatory.

2. Delivery fee in totals and payments
   - For delivery orders, `grand_total = items_total + delivery_fee`.
   - Click payment amount must use `grand_total` (not items-only subtotal).
   - Cash orders must display and store totals including delivery fee.
   - Web app UI summary must show delivery fee line item and a grand total.

3. Data consistency
   - Orders table must persist:
     - `total_price` = items subtotal
     - `delivery_price` = delivery fee
     - `grand_total` (or equivalent response fields) = subtotal + delivery fee
   - API response `OrderResponse.total` should reflect the grand total for delivery orders.

## Acceptance Criteria
1. Store closed
   - Attempt order from web app: rejected with 409 and working hours in message.
   - Attempt order from bot: rejected with localized "store closed" message.
2. Store open
   - Orders can be placed from both web app and bot.
3. Delivery totals
   - Example: items subtotal 100000, delivery 10000.
   - Web app shows total 110000.
   - Click invoice amount is 110000.
   - Order record stores delivery fee and total with delivery.

## Implementation Notes (Suggested Touchpoints)
- Web app: `webapp/src/pages/CartPage.jsx` totals and Click amount.
- Web app API: `app/api/webapp/routes_orders.py` response total for delivery.
- Backend: ensure all order creation paths use store-open validation (including any fallbacks).

