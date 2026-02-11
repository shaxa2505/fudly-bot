# Design and UX Audit (WebApp)

## Orders Flow
Issue O1 (P1) - No search, filters, or bulk actions in orders list.
Problem: The orders view only provides Active/History tabs and manual scanning.
Evidence: `webapp/src/pages/OrdersPage.jsx:42`, `webapp/src/pages/OrdersPage.jsx:317-329`.
Impact: Slow triage when order volume grows; high risk of missed orders.
Recommendation: Add search (order ID/phone), status + date filters, and bulk actions (e.g., cancel with reason).

Issue O2 (P1) - Cancel action is exposed without confirmation.
Problem: Cancel is a primary action on the card with no confirmation step.
Evidence: `webapp/src/pages/OrdersPage.jsx:477-512`.
Impact: Mis-taps can cancel orders and create support load.
Recommendation: Add a confirmation bottom sheet and provide an undo window.

## Products Flow
Issue P1 (P0) - Category page cannot surface large catalogs.
Problem: Category page fetches a hard limit of 50 items and has no pagination or “load more.”
Evidence: `webapp/src/pages/CategoryProductsPage.jsx:127`.
Impact: Users cannot browse 10k+ products; catalog feels incomplete.
Recommendation: Add pagination + infinite scroll with virtualization for categories.

Issue P2 (P1) - Search is not barcode/scanner friendly.
Problem: Search is a single text field with no barcode/SKU affordances.
Evidence: `webapp/src/pages/HomePage.jsx:1036`.
Impact: High-volume lookup workflows are slow.
Recommendation: Add barcode/SKU scan mode, autofocus, and parse numeric scans separately.

Issue P3 (P1) - Management actions are missing from product cards.
Problem: Product list is consumer-oriented (add-to-cart only) with no edit/bulk controls.
Evidence: `webapp/src/components/OfferCard.jsx:309-321`.
Impact: The specified “products management” flows (price/discount/qty/expiry edits, bulk actions) are not supported.
Recommendation: Introduce an operations mode or a separate management surface with inline edits and bulk actions.

## Information Hierarchy
Issue H1 (P1) - Discount visibility is too weak for a value-first discounter.
Problem: Discount badges are tiny (9px) and price hierarchy competes with meta info.
Evidence: `webapp/src/components/OfferCard.css:130-137`, `webapp/src/components/OfferCard.css:178-188`.
Impact: The core “save money” message is under-communicated.
Recommendation: Promote discount % and absolute savings; increase size and contrast; place next to primary price.

## Layout and Spacing Rhythm
Issue L1 (P2) - Component sizing is inconsistent with the token system.
Problem: Offer cards use custom radii and hard-coded values that diverge from tokens.
Evidence: `webapp/src/components/OfferCard.css:41`, `webapp/src/styles/design-tokens.css:121-129`.
Impact: Visual rhythm varies across screens and complicates future theming.
Recommendation: Align component radii/spacing with tokens and remove hard-coded values.

## Design System Issues
Issue D1 (P2) - Tokens exist but are not consistently applied.
Problem: Many components use hex colors instead of CSS variables.
Evidence: `webapp/src/components/OfferCard.css:134-137`, `webapp/src/styles/design-tokens.css:1-40`.
Impact: Color system drifts; brand updates are expensive.
Recommendation: Replace hex colors with `var(--color-*)` and centralize component styles.

## Consistency Issues
Issue C1 (P2) - Filter UI is duplicated with inconsistent structure.
Problem: Home and Category filters are separate implementations with different classes and spacing.
Evidence: `webapp/src/pages/HomePage.jsx:1177-1260`, `webapp/src/pages/CategoryProductsPage.jsx:334-396`.
Impact: UI feels inconsistent and increases design debt.
Recommendation: Create a shared FilterBar component with a unified layout and tokenized styling.

## Value Discounter Alignment
Issue V1 (P1) - Savings and urgency cues are not dominant.
Problem: Cards show old/new prices but do not emphasize “you save” or expiry urgency.
Evidence: `webapp/src/components/OfferCard.jsx:108-160`, `webapp/src/components/OfferCard.css:130-188`.
Impact: The value proposition is muted, reducing conversion.
Recommendation: Add a savings line, expiry countdown, and a prominent discount stack.

## Quick Wins
1. Increase discount badge size and move it next to the current price.
2. Add a savings line (e.g., “You save 12,000 so'm”) on cards.
3. Add order search by ID/phone and a date filter in Orders.
4. Add a barcode/SKU toggle in search inputs.
5. Add confirmation for order cancellation.

## Structural Changes
1. Build a standardized “Price Stack” component and apply it across all product cards.
2. Create a unified FilterBar and SearchBar used by Home and Category pages.
3. Add a management surface or mode for product edits and bulk actions.
4. Introduce list virtualization and pagination for all large lists.
5. Implement full RU/UZ i18n across the webapp.
