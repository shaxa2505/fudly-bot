# Establishments Button Fix

## Issue
The "Establishments" (Заведения) button was showing an empty list even when stores existed in the database.
This was because the database query filtered out stores that had 0 active offers.

## Fix
Modified `database_pg.py`:
- Removed `HAVING COUNT(o.offer_id) > 0` from `get_stores_by_business_type`.
- This allows stores to be listed even if they don't have any active offers yet.

## Verification
- The UI templates (`app/templates/offers.py`) correctly handle `offers_count = 0`.
- The store card allows viewing details even without offers.
