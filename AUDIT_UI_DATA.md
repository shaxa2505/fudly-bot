# Fudly Bot: Data Correctness & UX Consistency Audit
Date: 2026-01-23
Scope: Telegram bot (aiogram handlers), WebApp (React), API (FastAPI), DB schema

## Executive Summary
- P0 (2): Payment proof confirmations can be blocked or processed inconsistently because admin callbacks are duplicated and one path checks `order_status` instead of `payment_status`. This can leave paid orders stuck and customers without fulfillment confirmation.
- P1 (8): Order line items and totals can drift from what the user actually paid due to missing price snapshots for single‑item orders, cart `quantity` stored as number of distinct items, and delivery fees recomputed from current store settings instead of the order’s stored values.
- P2 (10+): UI consistency issues (rounding, missing payment status in order tracking, inconsistent currency labels, stale cached stock) can mislead users without necessarily blocking fulfillment.

Systemic themes:
- Order vs payment state are modeled in multiple layers with inconsistent fields and transitions.
- Order data snapshots are incomplete (price/title, delivery fee), causing historical mismatch.
- Multiple code paths render the same UI with slightly different formatting and data sources.

## Personas & User Journey Map
### Customer
1) Onboarding: /start -> language -> phone -> city/region/district -> main menu
2) Browse: hot offers / stores / search / categories -> offer details
3) Reserve/Order: pickup or delivery; quantity selection; confirm
4) Cart (bot): add -> view -> checkout -> pickup/delivery -> payment proof (card)
5) WebApp: home -> product detail -> cart -> checkout -> payment
6) Order management: “My orders” list -> detail -> cancel/received/rate -> payment proof upload (if needed)
7) Support: help FAQ, report issue

### Partner/Merchant
1) Registration: store application (city/category/name/address/description/phone)
2) Store settings: photo, geo, payment integrations, admins
3) Offer management: create/edit/delete/duplicate, stock updates
4) Order management: view orders, confirm/reject, mark ready/delivering/completed
5) Analytics: stats and revenue summaries

### Admin/Support
1) Store moderation (approve/reject)
2) Payment proof review (confirm/reject)
3) Delivery order oversight
4) System stats

## Data Dictionary
### Users (table: `users`)
| Field | Meaning | Source/Population | Displayed in | Notes |
|---|---|---|---|---|
| `user_id` | Telegram user id | Telegram init/update | Many | Primary key |
| `first_name` | User display name | Telegram profile | Profile screens | Used in notifications |
| `username` | Telegram username | Telegram profile | Partner contact | Optional |
| `phone` | Canonical phone | Bot registration | Profile, order notifications | `phone_number` is not a stored field |
| `language` | `ru`/`uz` | Language selection | All localized UI | `localization.py` |
| `city` | Normalized city | Registration/Profile | Offer filters, order flows | `normalize_city()` used in some flows |
| `region`/`district` | Location granularity | Registration/Profile | Offer filters | Used in search scopes |
| `role` | customer/seller/admin | Store approval flow | Profile, access control | Some flows infer from approved store |
| `notifications_enabled` | user prefs | Settings toggle | Used by UnifiedOrderService | Defaults to true |

Sources: `database_pg_module/schema.py`, `handlers/common/registration.py`, `handlers/customer/profile.py`

### Stores (table: `stores`)
| Field | Meaning | Source/Population | Displayed in | Notes |
|---|---|---|---|---|
| `store_id`, `owner_id` | Store identity | Partner registration | Store settings, orders | Used for permissions |
| `name`, `description`, `address`, `city` | Store profile | Partner registration/settings | Offer cards, order details | Address formatting varies |
| `phone` | Store phone | Partner registration | Order details, store info | Optional |
| `business_type` | Category | Partner registration | Store list filters | Mapping in `OfferService._map_business_type()` |
| `photo` | Store photo (file_id/url) | Partner settings | Store settings, webapp | Photo URL conversion may be missing |
| `delivery_enabled`, `delivery_price`, `min_order_amount` | Delivery config | Store settings | Offer details, cart, checkout | **Not stored on orders** |
| `status` | pending/active/rejected | Admin approval | Partner access | Affects visibility |
| ratings (computed) | Avg rating, counts | `ratings` table | Offer/store lists | Calculated in `OfferService._to_store_summary()` |

Sources: `database_pg_module/schema.py`, `app/services/offer_service.py`, `handlers/seller/store_settings.py`

### Offers (table: `offers`)
| Field | Meaning | Source/Population | Displayed in | Notes |
|---|---|---|---|---|
| `offer_id`, `store_id` | Offer identity | Partner create offer | Everywhere | Key for cart/order |
| `title`, `description`, `category` | Offer content | Partner create/edit | Offer cards, PDP | Category mapping via `normalize_category()` |
| `original_price`, `discount_price`, `discount_percent` | Pricing | Partner create | Offer lists/PDP | Discount % recomputed in multiple layers |
| `quantity`, `stock_quantity` | Stock | Partner manage / orders | Offer cards, cart | Both used inconsistently |
| `unit` | Unit label | Partner create | Offer cards/PDP | Default “шт”/“dona” |
| `expiry_date` | Offer expiry | Partner create | Offer cards/PDP | Different date formats |
| `photo`/`photo_id` | Offer image | Partner upload | Offer cards/PDP | URL conversion in webapp utilities |
| `status` | active/out_of_stock | Stock logic | Offer availability | Excluded in API if not active |

Sources: `database_pg_module/schema.py`, `app/services/offer_service.py`, `app/api/webapp/routes_offers.py`

### Orders (table: `orders` – unified)
| Field | Meaning | Source/Population | Displayed in | Notes |
|---|---|---|---|---|
| `order_id` | Order identifier | Order creation | Orders list/detail | Primary key |
| `user_id`, `store_id`, `offer_id` | Identity | Order creation | Orders list/detail | Offer snapshot is **not stored** |
| `quantity` | Item count | Order creation | Orders list/detail | **Cart orders store `len(cart_items)`** |
| `total_price` | Total incl. delivery | Order creation | Orders list/detail | Used for payment amount |
| `order_status` | Fulfillment status | UnifiedOrderService | My orders, partner/admin | “pending/preparing/ready/delivering/…” |
| `order_type` | pickup/delivery | Order creation | UI & notifications | Often inferred from delivery address |
| `delivery_address` | Delivery location | User input | Order details | For delivery orders only |
| `pickup_code` | Pickup code | Order creation | Pickup flows | Used for QR code |
| `payment_method` | cash/card/click/payme | Order creation | Order details | Normalized in PaymentStatus |
| `payment_status` | payment lifecycle | Payment flows | Order details | Not present in `OrderStatus` API model |
| `payment_proof_photo_id` | Receipt | Payment proof upload | Admin review | Used for manual verification |
| `cart_items`, `is_cart_order` | Cart snapshot | Cart order creation | WebApp detail | Items include price snapshot |
| `created_at`, `updated_at` | Timestamps | DB default | UI timestamps | Timezone not normalized |

Sources: `database_pg_module/schema.py`, `app/services/unified_order_service.py`, `app/api/webapp/routes_orders.py`

### Bookings (table: `bookings` + `bookings_archive`)
| Field | Meaning | Source/Population | Displayed in | Notes |
|---|---|---|---|---|
| `booking_id` | Booking ID | Legacy pickup flow | My bookings/history | Still used in some flows |
| `booking_code` | Pickup code | Legacy booking | Order tracking | Also stored as `pickup_code` in orders |
| `status` | Booking status | Legacy flows | My bookings | Mapped to unified statuses |
| `total_price` | Stored total | Legacy DB | WebApp orders | Some flows recompute from offer |

Sources: `database_pg_module/schema.py`, `handlers/bookings/customer.py`, `app/api/webapp/routes_orders.py`

### Payments
| Table/Field | Meaning | Used in | Notes |
|---|---|---|
| `payment_settings` | Platform card for manual transfers | Telegram cart delivery | Fallbacks to platform card if store card missing |
| `store_payment_integrations` | Click/Payme merchant ids | WebApp payment | In `handlers/seller/store_settings.py` |
| `click_transactions`, `uzum_transactions` | Provider callbacks | Payment reconciliation | Used in integrations, not in UI |

## UI / Messages Catalogue (Representative Screens)

### Telegram Bot (Customer)
| Screen / Message | Button Labels | Data Shown | Source-of-truth | Transformations |
|---|---|---|---|---|
| Language selection | `choose_language` | Language list | `localization.py` | None |
| Phone request | `share_phone` | Phone hint | `handlers/common/registration.py` | `sanitize_phone()` |
| City selection | `choose_city` | City list | `localization.get_cities()` | `normalize_city()` |
| Main menu | `hot_offers`, `browse_places`, `my_cart`, `my_orders`, `profile` | User city/name | `handlers/common/commands.py` | i18n |
| Hot offers list | “Hot offers” list | Title, price, store name | `OfferService.list_hot_offers()` | price formatting (`_format_money`) |
| Offer details | Offer card | Title, prices, discount %, stock, store, address | `OfferService.get_offer_details()` | discount % calc, date formatting |
| Booking flow | Qty + method | Price, qty, delivery fee | `handlers/bookings/customer.py` | total = price*qty + delivery fee |
| Cart view | Cart summary | Items, total, delivery | `handlers/customer/cart/*` | formatted sums |
| Cart delivery address | Address prompt | Address | FSM state | min length validation |
| Cart payment (card) | Card details | Card number/holder, total | `db.get_payment_card()` | currency formatting |
| My Orders list | Active orders | Order id, status, total, code | `db.get_user_orders()` + `OrderStatus.normalize()` | status labels |
| Order detail | Detail view | Items, total, address, phone, pickup code | `handlers/customer/orders/my_orders.py` | formatting, truncation |
| Payment proof upload | “upload_proof” | order id, amount | `handlers/customer/payment_proof.py` | none |

### Telegram Bot (Partner)
| Screen / Message | Button Labels | Data Shown | Source-of-truth | Transformations |
|---|---|---|---|---|
| Partner menu | `add_item`, `my_items`, `orders`, `store_settings` | store name | `db.get_user_accessible_stores()` | i18n |
| Create offer | prompts | title/desc/price/qty/time/expiry | FSM state + DB | validation (price/qty) |
| Orders list | Filters + order lines | order id, title, qty, status | `handlers/seller/management/orders.py` | status mapping |
| Order detail | Confirm/reject/etc | order total, customer phone | `db.get_order()` + offer | currency formatting |
| Store settings | photo/location/payment | store info | `handlers/seller/store_settings.py` | masking of merchant id |

### WebApp (Customer)
| Page | Data Shown | Source-of-truth | Transformations |
|---|---|---|---|
| HomePage | offers grid, discount %, stock, location | `/api/webapp/offers` | client filters, rounding |
| ProductDetailPage | price, discount, stock, delivery fee | `/api/webapp/offers/{id}`, `/stores/{id}` | local stock badges, expiry calc |
| CartPage | item list, totals, delivery, payment | cart context + `/orders` + `/payment/providers` | rounding, service fee (0) |
| OrderDetailsPage | items, delivery, payment status | `/api/webapp/orders` | delivery fee = total - items |
| OrderTrackingPage | status timeline, QR, store info | `/api/v1/orders/{id}` | status mapping, no payment status |
| StoresPage / ExplorePage / CategoryProductsPage | offer lists | `/api/webapp/offers` | filters, sorting |
| FavoritesPage | favorites list | `/api/webapp/favorites` | local cache |

## Flow Tables (Step-by-Step)

### Customer Onboarding (Telegram)
| Step | Message / Button | Data Fields | Source-of-truth | Transformations | Possible Mismatch | Repro | Proposed Fix |
|---|---|---|---|---|---|---|---|
| Language | `choose_language` | language | `localization.py` | none | none | /start | n/a |
| Phone | `share_phone` | phone | `handlers/common/registration.py` | sanitize/validate | phone mismatch if user sends other contact | send contact | ensure `contact.user_id` check (already) |
| City | `choose_city` | city list | `localization.get_cities()` | normalize city/region | user can see city label but DB stores normalized value | select city | show normalized value in profile |
| District | district buttons | region/district | `app/core/location_data.py` | normalize | inconsistent if city text not in list | choose city not in list | fallback to free text or show mapping |
| Completion | `registration_complete_personal` | name, city | db | html formatting | none | complete flow | n/a |

### Customer Browse & Offer Detail (Telegram)
| Step | Message / Button | Data Fields | Source-of-truth | Transformations | Possible Mismatch | Repro | Proposed Fix |
|---|---|---|---|---|---|---|---|
| Hot offers list | `hot_offers_title` | title, price, store | `OfferService.list_hot_offers()` | discount %, `int` formatting | rounding differences vs webapp | compare in bot vs webapp | unify price format helper |
| Offer details | offer card | price, original, qty, expiry | `OfferService.get_offer_details()` | discount % calc, date formatting | expiry date formatting differs by flow | view offer in bot vs webapp | centralize date formatting |
| Booking start | `book_offer_start` | qty, delivery | `handlers/bookings/customer.py` | total calc | delivery fee from store current value | change delivery price then view old order | snapshot delivery fee in orders |

### Customer Cart Checkout (Telegram)
| Step | Message / Button | Data Fields | Source-of-truth | Transformations | Possible Mismatch | Repro | Proposed Fix |
|---|---|---|---|---|---|---|---|
| Cart summary | `cart_checkout` | items, total | cart storage + offers | formatted sums | price changes update cart (expected) | change offer price | show “price updated” notice (exists) |
| Delivery selection | `cart_confirm_delivery` | total, delivery fee | store settings | total+delivery | delivery fee not stored on order | create order, change store fee | add `delivery_price` column and store snapshot |
| Payment (card) | card details | card number, total | `payment_settings` | currency formatting | card info missing if store not configured | missing card in DB | show explicit “no card configured” |
| Proof upload | photo | receipt photo id | Telegram file_id | none | admin flow mismatch (see P0) | upload receipt | unify admin handler |

### Customer WebApp Checkout
| Step | Page | Data Fields | Source-of-truth | Transformations | Possible Mismatch | Repro | Proposed Fix |
|---|---|---|---|---|---|---|---|
| Cart | `CartPage` | cart items, totals | local cart + `/stores/{id}` | rounding | stock stale vs server | stock changes | revalidate on submit |
| Delivery | checkout | delivery fee, min order | `/stores/{id}` | min order check client side | API `/orders/calculate-delivery` uses hardcoded values | compare webapp vs API | align delivery calculation with store settings |
| Payment | payment method | providers | `/payment/providers` | none | payment method default differs by channel | choose delivery, no provider | disallow checkout without provider |
| Create order | POST `/orders` | total, items | server | server computes total | missing idempotency key in webapp | double tap | add idempotency key in client |

### Customer Orders & Support
| Step | Screen | Data Fields | Source-of-truth | Transformations | Possible Mismatch | Repro | Proposed Fix |
|---|---|---|---|---|---|---|---|
| Orders list (bot) | `my_orders_handler` | status, total | `db.get_user_orders()` | status labels | cart order quantity uses `len(cart_items)` | cart order qty >1 | store sum of quantities |
| Order details (webapp) | `OrderDetailsPage` | item price, delivery fee | `/api/webapp/orders` | fallback delivery fee = total - items | item price for non-cart orders uses current offer price | change offer price after order | snapshot item price in orders |
| Order tracking | `/api/v1/orders` | status timeline, QR | `format_booking_to_order_status()` | status mapping | payment status missing | order awaiting proof | include payment_status in model |
| Payment proof upload | `upload_proof_*` | proof photo | bot flow | none | phone field uses `phone_number` (missing) | upload proof | use `phone` field |

### Partner Store & Offer Management
| Step | Screen | Data Fields | Source-of-truth | Transformations | Possible Mismatch | Repro | Proposed Fix |
|---|---|---|---|---|---|---|---|
| Store settings | `store_settings.py` | photo, geo, delivery settings | `stores` table | none | payment integrations shown but not validated | add invalid merchant id | validate format and test connection |
| Offer create | `create_offer.py` | prices/qty/time | offers table | discounts computed | different rounding in webapp | compare | centralize price calc |

### Partner Order Management
| Step | Screen | Data Fields | Source-of-truth | Transformations | Possible Mismatch | Repro | Proposed Fix |
|---|---|---|---|---|---|---|---|
| Orders list | `seller/management/orders.py` | order id, status, qty | `orders` table | status mapping | orders hidden until payment cleared | submit proof | decide business rule; if want visibility on `proof_submitted`, allow |
| Order detail | `seller_view_order` | total, delivery fee, customer phone | `orders` + offers | currency formatting | delivery fee uses store current value | change store fee | store delivery fee on order |

### Admin Payment Review
| Step | Screen | Data Fields | Source-of-truth | Transformations | Possible Mismatch | Repro | Proposed Fix |
|---|---|---|---|---|---|---|---|
| Payment proof view | admin callback | order id, amount, items | `orders`, `cart_items` | formatted sums | duplicate handlers; status check uses `order_status` not `payment_status` | upload proof | unify handler, check payment_status |

## Source-of-Truth Integrity Pass
- **Computed vs stored**: Single‑item orders do not store price/title snapshots. UI and notifications read current offer values (mutable) from `offers`. This can diverge from `total_price` (stored). Fix by storing `item_price`, `item_title`, `item_unit`, `original_price`, `discount_percent` on `orders` at creation.
- **Delivery fee**: `delivery_price` is not stored on `orders`. Several UIs compute it from current store settings or from `total_price - items_total`, which is unreliable if price changes or if order has service fee later. Add `delivery_price` column and write snapshot.
- **Quantity**: `orders.quantity` for cart orders is `len(cart_items)` in `create_cart_order_atomic` but some UI treats it as total units. Change to sum of item quantities.
- **Status mapping**: `OrderStatus.normalize()` + multiple local maps in webapp and bot result in inconsistent labels. Centralize in one mapping module.
- **Currency formatting**: Mix of `int`, `round`, `format` across layers. Centralize to avoid rounding discrepancies.
- **Location normalization**: Some flows use `normalize_city`, others use raw city (webapp manual location). This can cause “no offers” in one channel.

## State Machine & Mapping
### Fulfillment Order Status (Unified)
`pending` -> `preparing` -> `ready` -> `delivering` -> `completed`
`pending` -> `rejected` (seller)
`pending` -> `cancelled` (customer)

Sources: `app/services/unified_order_service.py` (OrderStatus), `handlers/common/unified_order/*`

### Payment Status
`not_required` (cash)
`awaiting_payment` (click/payme)
`awaiting_proof` (manual card transfer)
`proof_submitted`
`confirmed`
`rejected`

Sources: `app/services/unified_order_service.py` (PaymentStatus)

### Mapping to UI
- Bot “My orders” uses fulfillment status only (`handlers/customer/orders/my_orders.py`). Payment status is not surfaced.
- WebApp OrderDetails merges fulfillment + payment status into a single display (`OrderDetailsPage.jsx`).
- WebApp OrderTracking uses `/api/v1/orders` and doesn’t include payment status (invisible).

Recommendation: include payment status in OrderStatus API and display consistently in both bot and webapp.

## UI/Data Bug Catalogue (P0/P1/P2)

| ID | Severity | Issue | Impact | Location | Repro | Fix Suggestion |
|---|---|---|---|---|---|---|
| P0-1 | P0 | Admin payment confirmation checks `order_status` instead of `payment_status` and can refuse valid proofs | Paid orders stuck; customers wait indefinitely | `handlers/admin/delivery_orders.py` → `admin_confirm_payment`, `admin_reject_payment` | Upload proof; confirm; see “already processed” | Guard on `payment_status in ('proof_submitted','awaiting_proof')`, not `order_status` |
| P0-2 | P0 | Duplicate admin handlers for `admin_confirm_payment_*` callbacks in two routers | Non-deterministic payment processing, double notifications | `handlers/admin/delivery_orders.py` and `handlers/customer/orders/delivery_admin.py` | Trigger admin confirm; observe handler differences | Consolidate into single handler and route; remove duplicate |
| P1-1 | P1 | Single‑item orders read current offer price/title instead of snapshot | Order details show wrong item price and name | `app/api/webapp/routes_orders.py` (SQL join uses `offers.discount_price`), `handlers/seller/management/orders.py`, `handlers/customer/orders/my_orders.py` | Change offer price/title after order; view order detail | Store `item_price`, `item_title` in `orders` at creation; use it in UI |
| P1-2 | P1 | Cart orders store `quantity = len(cart_items)` not total units | “Quantity” shown in UI is wrong | `database_pg_module/mixins/orders.py` → `create_cart_order_atomic` | Cart with items qty>1; view order | Store `quantity = sum(item.quantity)` |
| P1-3 | P1 | Delivery fee not stored on orders; UIs use current store fee | Historical orders show wrong delivery cost | `handlers/customer/orders/my_orders.py`, `handlers/seller/management/orders.py`, `app/api/orders.py` | Change store delivery fee after order | Add `delivery_price` column to orders; snapshot on create |
| P1-4 | P1 | Seller orders list hides all orders unless payment is cleared | Sellers may not see orders in `proof_submitted` | `handlers/seller/management/orders.py` → `_get_all_orders` | Create card payment order; seller list empty | Decide business rule; optionally show `proof_submitted` orders with badge |
| P1-5 | P1 | WebApp delivery calculation uses hardcoded costs/min order | Mismatch vs store settings and bot | `app/api/orders.py` → `calculate_delivery_cost` | Compare delivery fee in webapp vs bot | Use store `delivery_price`/`min_order_amount` |
| P1-6 | P1 | Customer payment proof admin message uses `phone_number` (not stored) | Admin lacks customer phone for verification | `handlers/customer/payment_proof.py` → `receive_payment_proof` | Upload proof; admin sees empty phone | Use `phone` field consistently |
| P1-7 | P1 | `OrderTrackingPage` expects payment status but API doesn’t provide it | Payment pending not shown in tracking | `webapp/src/pages/OrderTrackingPage.jsx`, `app/api/orders.py` | Delivery order awaiting proof | Add `payment_status` to `OrderStatus` model & endpoint |
| P1-8 | P1 | `delivery_price` in seller order detail derived from store current settings | Seller sees wrong delivery fee for historical orders | `handlers/seller/management/orders.py` → `seller_view_order` | Update store fee after order | Use order snapshot `delivery_price` |
| P2-1 | P2 | Price rounding differs across layers (`int`, `round`, `toLocaleString`) | Minor display inconsistencies | `handlers/customer/offers/browse_hot.py`, `webapp/*` | Compare bot vs webapp | Centralize formatting helper |
| P2-2 | P2 | Currency labels inconsistent (`sum`, `so'm`, `сум`) | UX inconsistency | multiple files | Compare screens | Standardize via localization helper |
| P2-3 | P2 | Order tracking header uses `booking_code` for delivery orders | UI shows empty order number | `webapp/src/pages/OrderTrackingPage.jsx` | Open delivery order tracking | Use `order_id` fallback |
| P2-4 | P2 | Cached offers/stores (TTL) can show stale stock/prices | Users see outdated availability | `app/core/cache.py`, `webapp/src/api/client.js` | Update stock quickly | Add cache bust on mutations |

## Top 20 Likely Production Incidents (Data/UX)
1) Paid delivery order remains “awaiting proof” because admin confirm checks wrong field.
2) Admin confirm handled twice (two routers), leading to double notifications.
3) Customer sees wrong item price after merchant updates offer; disputes with receipts.
4) Seller sees wrong delivery fee after changing store settings.
5) Cart order shows quantity “2” when actual items total 6 (sum quantities).
6) WebApp tracking doesn’t show payment pending; customer pays twice.
7) Delivery min order shown in webapp differs from bot, causing confusion.
8) Order list uses current offer title, not what user bought (renamed offer).
9) Payment proof admin message missing customer phone.
10) Currency rounding differences cause small mismatches between bot/webapp totals.
11) Inconsistent status labels (“confirmed” vs “preparing”) across UIs.
12) Stale cache shows available stock while order fails at checkout.
13) Timezone differences show pickup time in different day.
14) Store address changed after order; order detail shows new address.
15) Delivery fee computed as total-items breaks if service fee added.
16) Offer “expired” in bot but still visible in webapp due to cache.
17) Orders list filters hide unpaid orders from seller, causing late fulfillment.
18) WebApp “order tracking” uses booking code for delivery, header blank.
19) Admin confirms payment but seller doesn’t receive updated order message due to missing `seller_message_id`.
20) WebApp order details show wrong payment method for legacy orders where `payment_method` is null.

## Observability Gaps & Recommendations
- Log structured “display payloads” for order summary sent to customer/seller with `order_id`, `total_price`, `delivery_price`, `items_count`.
- Add metrics for: `payment_status` transitions, admin proof confirmations, failed payment proof uploads.
- Add audit log for changes to store delivery fees and offer prices (used to explain historical mismatches).

## Assumptions / Missing Business Rules
- Whether sellers should see `proof_submitted` orders is unclear. Current logic hides them.
- Whether delivery fees are fixed per store or dynamic is not explicit; webapp uses store setting, API uses hardcoded values.

---

# Appendix: Exact Code Locations
- Payment proof confirm: `handlers/admin/delivery_orders.py` → `admin_confirm_payment()`
- Duplicate admin handlers: `handlers/customer/orders/delivery_admin.py` → `admin_confirm_payment()`
- Cart quantity bug: `database_pg_module/mixins/orders.py` → `create_cart_order_atomic()`
- WebApp order list price source: `app/api/webapp/routes_orders.py` → `get_orders()`
- Order tracking API model: `app/api/orders.py` → `OrderStatus` model

