# PR Plan (WebApp)

PR1 - Data scalability and list virtualization
Scope: Add pagination for `/orders` and `/offers`, implement virtualized lists for Orders and Products, and update infinite-scroll logic to keep DOM size bounded.
Files likely touched: `app/api/orders.py`, `app/api/webapp_api.py`, `webapp/src/api/client.js`, `webapp/src/pages/OrdersPage.jsx`, `webapp/src/pages/HomePage.jsx`, `webapp/src/pages/CategoryProductsPage.jsx`.
Risk: High (API + UI changes).
How to test: Load 10k offer fixtures; scroll lists smoothly; confirm pagination works; verify active/history orders count correctness.
Expected outcome: Stable performance with large datasets and reduced backend load.

PR2 - Orders high-volume UX
Scope: Add search by order ID/phone, status + date filters, bulk actions (cancel with reason), and preserve list context when opening details.
Files likely touched: `webapp/src/pages/OrdersPage.jsx`, `webapp/src/components/OrderModals.jsx`, `webapp/src/styles/shared-components.css`.
Risk: Medium.
How to test: Search/filter orders, bulk-cancel, open/close details while keeping scroll and active tab.
Expected outcome: Faster triage and fewer misclicks for daily operations.

PR3 - Value-first product UI + design tokens
Scope: Introduce a `PriceStack` and `DiscountBadge` component, promote savings/expiry cues, and align OfferCard styling with design tokens.
Files likely touched: `webapp/src/components/OfferCard.jsx`, `webapp/src/components/OfferCard.css`, `webapp/src/styles/design-tokens.css`, `webapp/src/styles/shared-components.css`.
Risk: Medium (visual regressions).
How to test: Visual QA on Home and Category pages; verify discount/savings hierarchy; check mobile layout.
Expected outcome: Strong “value discounter” positioning and more consistent visuals.

PR4 - Security hardening for Telegram auth
Scope: Remove `initData` persistence, introduce short-lived WS auth tokens, and stop sending `init_data` in query params.
Files likely touched: `webapp/src/api/client.js`, `webapp/src/pages/OrderDetailsPage.jsx`, `webapp/src/pages/CartPage.jsx`, `app/api/webapp_api.py`.
Risk: Medium (auth flow changes).
How to test: Fresh login, WebSocket updates, and order status updates; verify tokens are not stored in localStorage.
Expected outcome: Lower token leakage risk with secure real-time updates.

PR5 - i18n + accessibility
Scope: Add RU/UZ translation layer, update `lang` dynamically, remove zoom lock, and improve keyboard/ARIA support for cards and inputs.
Files likely touched: `webapp/index.html`, `webapp/src/pages/*.jsx`, `webapp/src/components/OfferCard.jsx`, `webapp/src/styles/accessibility.css`.
Risk: Medium.
How to test: Language switch, screen reader labels, keyboard navigation, and zoom on mobile devices.
Expected outcome: Full RU/UZ readiness and improved accessibility.
