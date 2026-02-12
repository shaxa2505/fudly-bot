# Security & Scalability Audit

Date: 2026-02-12

## Scope
- Telegram bot (aiogram), webhook server (aiohttp), Mini App API (FastAPI), WebApp, Partner Panel, payments, DB/Redis.

## Summary
- Security posture: medium. Core Telegram HMAC auth, CORS, and rate limiting exist, but there are important hardening gaps.
- Scale readiness: early-stage OK. Without pagination, Redis-backed realtime, and DB tuning, growth will hit bottlenecks fast.

## Security Findings (Active)
Issue S1 (P0) - Merchant webhook signatures are enforced in production (Fixed).
Problem: Signatures are now required by default in production.
Evidence: `app/api/merchant_webhooks.py`.
Impact: Reduces spoofing risk for payment callbacks.
Recommendation: Ensure `UZUM_MERCHANT_WEBHOOK_SECRET` is set in production.
Effort: Small.

Issue S2 (P1) - Telegram webhook secret token is optional.
Problem: Webhook handler validates `X-Telegram-Bot-Api-Secret-Token` only when configured.
Evidence: `app/core/webhook_server.py`.
Impact: If webhook URL is discovered, fake updates could be injected.
Recommendation: Always set `SECRET_TOKEN` in production and fail fast when missing.
Effort: Small.

Issue S3 (P1) - Rate limiting gaps on read-heavy endpoints.
Problem: Several read endpoints lack `@limiter` coverage (orders status/timeline, list endpoints).
Evidence: `app/api/orders.py`, `app/api/webapp/routes_orders.py`.
Impact: Authenticated abuse can amplify DB load and degrade service (DoS).
Recommendation: Add per-route limits and/or global burst limits for read-heavy routes.
Effort: Small to Medium.

Issue S4 (P2) - Payment card endpoint is unauthenticated.
Problem: `/api/v1/payment-card/{store_id}` returns card data without auth.
Evidence: `app/core/webhook_media_routes.py`.
Impact: Exposes payment card data publicly; raises phishing/compliance risks.
Recommendation: Require auth or serve masked card details only.
Effort: Small.

Issue S5 (P2) - CSP allows unsafe inline scripts and third-party CDNs.
Problem: CSP includes `'unsafe-inline'` and broad external sources for scripts/styles.
Evidence: `app/api/api_server.py`.
Impact: Increases blast radius if a third-party asset is compromised.
Recommendation: Self-host critical assets or add SRI; reduce inline scripts over time.
Effort: Medium.

## Resolved Or Mitigated In This Pass
Issue SR1 (P1) - Telegram initData persistence removed; WS uses short-lived tokens.
Evidence: `webapp/src/api/client.js`, `app/api/auth.py`, `app/core/ws_tokens.py`.
Impact: Reduced token leakage risk and query-string exposure.
Status: Fixed (2026-02-12).

Issue SR2 (P0) - WebSocket store access check now awaits async DB calls.
Evidence: `app/core/websocket.py`.
Impact: Prevents access bypass when DB methods are async.
Status: Fixed (2026-02-12).

## Scalability Findings
Issue SC1 (P0) - Orders and offers listing scale poorly.
Problem: Frontend renders large lists and backend endpoints can return large datasets.
Evidence: `webapp/src/pages/OrdersPage.jsx`, `webapp/src/pages/HomePage.jsx`, `app/api/webapp/routes_orders.py`.
Impact: High DB load and UI jank at 1k+ orders/day and 10k+ offers.
Recommendation: Server-side pagination, cursor-based loading, and list virtualization.
Effort: Large.

Issue SC2 (P1) - N+1 DB access in order history paths.
Problem: Order history handlers fetch offers/stores per item.
Evidence: `app/api/auth.py`, `app/api/webapp/routes_orders.py`.
Impact: Latency grows linearly with history size.
Recommendation: Join queries in repo layer or batch-load in a single query.
Effort: Medium.

Issue SC3 (P1) - Realtime stack depends on Redis for multi-instance.
Problem: WS tokens and notification pub/sub fall back to in-memory storage.
Evidence: `app/core/ws_tokens.py`, `app/core/notifications.py`.
Impact: Tokens fail across instances; WS notifications do not broadcast across nodes.
Recommendation: Enable Redis in production (`REDIS_URL`) and validate multi-instance flows.
Effort: Medium.

Issue SC4 (P2) - Polling + WS duplication in UIs.
Problem: Several screens poll while WS is active.
Evidence: `webapp/src/pages/OrderDetailsPage.jsx`, `webapp/partner-panel/index.html`.
Impact: Elevated backend load and unnecessary battery usage.
Recommendation: Prefer a single realtime mechanism and disable polling when WS is connected.
Effort: Small to Medium.

Issue SC5 (P2) - In-process background tasks in multi-instance mode.
Problem: Cleanup/expiry workers run inside the bot process by default.
Evidence: `bot.py`.
Impact: Duplicate work or conflicting updates if multiple instances run.
Recommendation: Move to a dedicated worker (arq) with distributed locks.
Effort: Medium.

## Scale Readiness Verdict
- With Redis + pagination + DB tuning, scaling to tens of thousands of orders/day is achievable.
- Without these, the first bottlenecks will be orders/offer listing, realtime fan-out, and DB load.

## Top Recommendations
1. Enforce merchant webhook signatures in production.
2. Add rate limits to read-heavy endpoints and cache frequent reads.
3. Implement pagination + virtualization for Orders and Offers.
4. Require Redis for WS tokens and notifications in multi-instance deployments.
5. Add DB indexes for orders (user_id, created_at, status) and offers (store_id, status, city).
