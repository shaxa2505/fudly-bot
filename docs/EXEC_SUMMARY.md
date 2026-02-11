# Executive Summary (WebApp Only)

1. P0 - Orders list loads the full dataset with no pagination/virtualization and polls every 10 seconds. Impact: the UI and backend will not scale to 1k+ orders/day and users will experience jank and long loads.
2. P0 - Products listing is not scalable: Home uses infinite scroll but renders all items in the DOM, while Category pages hard-cap to 50 items with no pagination. Impact: either incomplete catalog views or severe performance degradation at 10k+ products.
3. P1 - Order details refresh is redundant (15s polling + timeline polling + WebSocket) and even fetches all orders for enrichment. Impact: unnecessary network/battery usage, higher backend load, and slower perceived updates.
4. P1 - Telegram `initData` is persisted in storage and sent in WebSocket query params. Impact: elevated token leakage risk if logs or XSS are present.
5. P1 - i18n readiness is missing: UI strings are hard-coded (mostly Uzbek), `lang="uz"` is fixed, and RU support is only partial in status helpers. Impact: RU/UZ requirement is not met.
6. P1 - Orders flow lacks high-volume tooling (search, filters, bulk actions, fast status changes). Impact: slow triage and higher operational friction.
7. P1 - Accessibility blockers: zoom is disabled, primary cards are not keyboard-focusable, and key inputs lack labels. Impact: reduced usability and compliance risk.
8. P2 - “Value discounter” hierarchy is weak: discount tags are tiny and savings/expiry are not dominant. Impact: the core value proposition is under-communicated.
9. P2 - Maintainability risks: very large page components and duplicated filter UI across screens. Impact: higher regression risk and slow iteration.
10. P2 - Global in-memory caches store full lists without eviction. Impact: memory growth and instability on long sessions.
