# UX Fixes: Cancel Button Logic

## Issue
Users reported that pressing the "Cancel" button (❌ Отмена / ❌ Bekor qilish) during numeric input steps (e.g., entering quantity) resulted in a validation error ("Введите число!") instead of cancelling the action.

## Fixes Applied

### 1. Order Delivery (`handlers/orders.py`)
- **Handler**: `order_delivery_quantity`
- **Change**: Added a check for cancellation strings (`/cancel`, "❌ Отмена", "❌ Bekor qilish") *before* attempting to convert the input to an integer.
- **Result**: Pressing cancel now correctly clears the state and returns the user to the main menu.

### 2. Booking Offer (`handlers/bookings.py`)
- **Handler**: `book_offer_quantity`
- **Change**: Added the same cancellation check logic.
- **Result**: Consistent behavior across both ordering and booking flows.

## Verification
- Ran `pytest` suite (114 tests passed).
- Verified that the logic handles both Russian and Uzbek cancellation texts.

## Deployment
- Changes committed and pushed to `main` branch.
- Ready for deployment to Railway.
