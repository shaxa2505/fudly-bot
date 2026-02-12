# Frontend Audit (WebApp)

## Architecture Overview
- Framework/build: React + Vite with React Router. Evidence: `webapp/package.json:7-12`, `webapp/package.json:21`, `webapp/src/App.jsx:2`, `webapp/src/App.jsx:414-461`.
- State management: React local state plus Contexts for cart, favorites, and toast. Evidence: `webapp/src/context/CartContext.jsx:1`, `webapp/src/context/FavoritesContext.jsx:1`, `webapp/src/context/ToastContext.jsx:1`.
- API/data fetching: Axios client with custom LRU caching and retry logic. Evidence: `webapp/src/api/client.js:1-24`, `webapp/src/api/client.js:145-190`.
- Styling: Global CSS + per-component CSS with a design token layer. Evidence: `webapp/src/styles/design-tokens.css:1`, `webapp/src/App.css:1-22`, `webapp/src/index.css:1`.
- Error handling: Sentry + ErrorBoundary wrapper at root. Evidence: `webapp/src/main.jsx:1-26`, `webapp/src/components/ErrorBoundary.jsx:1`.

## Code Quality
Issue CQ1 (P1) - Monolithic page logic and duplicated filters.
Problem: `HomePage` owns geolocation, search, filters, caching, and list rendering in one file; category filters are re-implemented separately.
Evidence: `webapp/src/pages/HomePage.jsx:1177-1260`, `webapp/src/pages/CategoryProductsPage.jsx:334-396`.
Impact: High maintenance cost and inconsistent filter behavior across screens.
Recommendation: Extract shared filter/search components and hooks (`FilterBar`, `useOffersQuery`, `useLocationFilters`) and move cache logic out of components.
Effort: Medium.

Issue CQ2 (P2) - Localization is hard-coded and fragmented.
Problem: UI strings are embedded directly in components, while only status helpers include RU/UZ mapping.
Evidence: `webapp/src/pages/OrdersPage.jsx:307-476`, `webapp/src/utils/orderStatus.js:1-78`, `webapp/index.html:2`.
Impact: RU/UZ requirement is not met; copy updates require manual edits in many files.
Recommendation: Introduce i18n (e.g., `react-i18next`) and move all UI strings into locale dictionaries.
Effort: Medium to Large.

Issue CQ3 (P2) - Design tokens exist but are not enforced.
Problem: Components use hard-coded hex colors and fixed radii outside the token scale.
Evidence: `webapp/src/styles/design-tokens.css:1-140`, `webapp/src/components/OfferCard.css:41`, `webapp/src/components/OfferCard.css:134-137`.
Impact: Inconsistent visual language and harder theming.
Recommendation: Replace hard-coded values with CSS variables and lint for hex usage.
Effort: Medium.

## Performance
Issue P1 (P0) - Orders list fetches full dataset and polls every 10 seconds.
Problem: `/orders` is fetched without pagination, and active orders trigger forced refresh every 10s.
Evidence: `webapp/src/api/client.js:332-336`, `webapp/src/pages/OrdersPage.jsx:57`, `webapp/src/pages/OrdersPage.jsx:78`.
Impact: UI jank and backend load at 1k+ orders/day.
Recommendation: Add server pagination and status-filtered endpoints; virtualize lists; fetch active/history separately.
Effort: Large.

Issue P2 (P0) - Product lists are not scalable.
Problem: Home page renders all loaded offers in the DOM; category page hard-caps to 50 items with no pagination.
Evidence: `webapp/src/pages/HomePage.jsx:39`, `webapp/src/pages/HomePage.jsx:492-493`, `webapp/src/pages/HomePage.jsx:1400`, `webapp/src/pages/CategoryProductsPage.jsx:127`, `webapp/src/pages/CategoryProductsPage.jsx:451`.
Impact: Either incomplete catalog view or severe performance degradation at 10k+ products.
Recommendation: Implement cursor pagination and list virtualization (e.g., `react-window`) with server-side filtering.
Effort: Large.

Issue P3 (P1) - Order detail updates are redundant and heavy.
Problem: Details page uses polling + timeline refresh + WebSocket, and falls back to loading *all* orders for enrichment.
Evidence: `webapp/src/pages/OrderDetailsPage.jsx:102`, `webapp/src/pages/OrderDetailsPage.jsx:170`, `webapp/src/pages/OrderDetailsPage.jsx:222`.
Impact: Unnecessary network/battery usage and higher backend load.
Recommendation: Choose one realtime mechanism (WS/SSE) and add a dedicated order details endpoint with items.
Effort: Medium.

Issue P4 (P1) - Large in-memory caches with no eviction.
Problem: Page-level caches store full offer lists globally without size limits.
Evidence: `webapp/src/pages/HomePage.jsx:44`, `webapp/src/pages/HomePage.jsx:672`, `webapp/src/pages/CategoryProductsPage.jsx:26`, `webapp/src/pages/CategoryProductsPage.jsx:198`.
Impact: Memory growth and possible crashes during long sessions.
Recommendation: Limit cache size and store minimal state; adopt LRU or TTL-based eviction.
Effort: Medium.

## Reliability
Issue R1 (P1) - Error handling is alert-only on category products.
Problem: Failed loads only show `alert()` and leave the page without an inline recovery state.
Evidence: `webapp/src/pages/CategoryProductsPage.jsx:174`.
Impact: Users get stuck with no retry or fallback UI.
Recommendation: Add inline error states with retry and preserve last-known-good data.
Effort: Small.

Issue R2 (P2) - Optimistic order cancellation without confirmation.
Problem: UI marks orders as cancelled before the API succeeds.
Evidence: `webapp/src/pages/OrdersPage.jsx:483-492`.
Impact: Mis-taps can cancel orders and UI can temporarily display wrong status.
Recommendation: Add confirmation/undo, and revert UI on failure.
Effort: Small to Medium.

## Security
Issue S1 (P1) - Telegram initData persistence removed (Fixed).
Problem: initData is now kept in memory only with a short TTL.
Evidence: `webapp/src/api/client.js:29-70`.
Impact: Reduced risk of token leakage via storage.
Recommendation: Keep initData in memory and rely on short-lived server tokens.
Effort: Medium (done).

Issue S2 (P1) - WebSocket auth moved to short-lived token (Fixed).
Problem: WS URLs no longer include init_data; a ws_token is fetched over HTTPS.
Evidence: `webapp/src/api/client.js:272-305`, `webapp/src/pages/OrderDetailsPage.jsx:221-240`, `webapp/src/pages/CartPage.jsx:1385-1406`, `webapp/src/pages/YanaPage.jsx:132-134`.
Impact: Reduced query-string leakage risk.
Recommendation: Keep ws_token flow and remove init_data fallback server-side after migration.
Effort: Medium (done).

Security note: No `dangerouslySetInnerHTML` usage found in `webapp/src`, so direct DOM XSS injection risk is lower.

## Accessibility
Issue A1 (P1) - Zoom is disabled globally.
Problem: Viewport meta disables scaling.
Evidence: `webapp/index.html:5`.
Impact: Low-vision users cannot zoom.
Recommendation: Remove `maximum-scale` and `user-scalable=no`.
Effort: Small.

Issue A2 (P1) - Offer cards are not keyboard-accessible.
Problem: Clickable cards are `<div>` elements without role/tabindex.
Evidence: `webapp/src/components/OfferCard.jsx:193-194`.
Impact: Keyboard and assistive tech users cannot open product details.
Recommendation: Use `<button>`/`<a>` or add `role="button"`, `tabIndex`, and key handlers.
Effort: Small.

Issue A3 (P1) - Search inputs lack accessible labels.
Problem: Inputs rely on placeholders without labels or `aria-label`.
Evidence: `webapp/src/pages/HomePage.jsx:1036`, `webapp/src/pages/CategoryProductsPage.jsx:299`.
Impact: Screen readers announce them poorly.
Recommendation: Add `<label>` or `aria-label` and associate IDs.
Effort: Small.

Issue A4 (P2) - Icon-only buttons lack accessible names.
Problem: Filter toggle in category header has no `aria-label`.
Evidence: `webapp/src/pages/CategoryProductsPage.jsx:273`.
Impact: Users cannot understand the control via assistive tech.
Recommendation: Add `aria-label` or visually hidden text.
Effort: Small.
