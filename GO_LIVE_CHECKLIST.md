# Go-Live Checklist (Staging) — Data Correctness & UX Consistency
Date: 2026-01-23

## Environment & Data
- [ ] Confirm DB migration applied and `orders` schema matches expected columns.
- [ ] Verify sample data: 2 stores, 10 offers (mixed categories, one out_of_stock), 3 customers.
- [ ] Confirm store delivery settings per store (delivery_enabled, delivery_price, min_order_amount).
- [ ] Confirm payment providers configured (Click/Payme) for at least one store.

## Customer (Telegram Bot)
### Onboarding
- [ ] /start language selection works (ru/uz) and saves language.
- [ ] Phone registration saves to `users.phone` and is displayed in profile.
- [ ] City selection saves normalized city; profile shows same city label.

### Browse & Offer Details
- [ ] Hot offers list shows correct price/discount and store name.
- [ ] Offer detail card shows correct stock and expiry date formatting.
- [ ] Low stock warning appears when appropriate.

### Booking / Pickup
- [ ] Create pickup order (single item) and confirm pickup code.
- [ ] Order appears in “My orders” with correct total and status.
- [ ] Seller receives new order notification with correct item/qty/total.

### Cart / Delivery
- [ ] Add multiple items (quantities >1) to cart; cart total matches expected.
- [ ] Delivery flow: min order enforcement matches store settings.
- [ ] Card payment details show correct amount and card number.
- [ ] Upload payment proof in bot; admin receives proof.

### Order Management
- [ ] “My orders” list shows delivery & pickup with correct status labels.
- [ ] Order detail shows correct totals and address/phone.
- [ ] Cancel order only allowed when status is pending.
- [ ] “Received” action completes order and prompts for rating.

## Customer (WebApp)
### Home / Offers
- [ ] HomePage shows offers for selected city/region.
- [ ] Filters (discount, price, category) return consistent results.
- [ ] Offer detail page shows same price/discount as bot.

### Cart / Checkout
- [ ] Cart total matches item prices.
- [ ] Delivery fee equals store delivery fee and min order enforced.
- [ ] Payment method availability matches store integrations.
- [ ] Order creation returns order_id and status pending.

### Orders
- [ ] OrderDetails shows correct payment status and totals.
- [ ] OrderTracking shows correct status timeline and QR (pickup).
- [ ] Payment proof upload link opens bot flow and updates status.

## Partner / Merchant
- [ ] Store settings: photo upload, geo setup, delivery settings updated.
- [ ] Payment integration fields validate and save correctly.
- [ ] Offer creation works with correct price/discount/expiry.
- [ ] Orders list shows new orders immediately (including proof_submitted if intended).
- [ ] Seller can confirm/reject/mark ready/delivered; customer notified.

## Admin / Support
- [ ] Admin receives payment proof with correct order details & phone.
- [ ] Confirm payment updates payment_status and notifies seller/customer.
- [ ] Reject payment updates payment_status and allows re-upload.

## Consistency & Regression Checks
- [ ] Offer price changes do not affect existing order item prices.
- [ ] Delivery fee changes do not affect existing order totals.
- [ ] Order quantities match sum of item quantities for cart orders.
- [ ] No duplicate admin confirmation handlers are active.

## Observability
- [ ] Logs include order_id, payment_status transition, and customer/seller notifications.
- [ ] Metrics dashboards show payment confirmations and rejected proofs.

