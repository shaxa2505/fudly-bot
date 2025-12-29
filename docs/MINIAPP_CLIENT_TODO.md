# Mini App Client Performance TODO

## Critical (fixed)
- [x] Fix city transliteration maps across client and backend to keep filters consistent.
- [x] Normalize city defaults for WebApp routes and API client calls.
- [x] Align city enums and normalize-city helpers to real Cyrillic values.

## Next (high impact)
- [x] Deduplicate in-flight GET requests and use LRU cache in `webapp/src/api/client.js`.
- [ ] Add pagination + `updated_since` (or ETag) for `/orders` in `app/api/webapp/routes_orders.py`.
- [x] Push `/offers` filtering/sorting into DB and add pagination for store/category/hot offers.
- [ ] Add indexes for city/category/price/discount to support `/offers` queries.
- [ ] Add `/stores` pagination and trim response payloads.
- [ ] Use `OptimizedImage` in orders list to reduce layout shifts.

## UX niceties
- [ ] Skeletons for orders list and empty-state polishing.
- [ ] Persist filters/search state per user.
- [ ] Prefetch next offers page on idle.
