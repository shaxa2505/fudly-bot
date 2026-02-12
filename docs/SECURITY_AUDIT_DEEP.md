# Deep Security Audit

Date: 2026-02-12

## Scope
- Telegram bot (aiogram), webhook server (aiohttp), Mini App API (FastAPI), WebApp, Partner Panel, payments, DB/Redis, WebSockets.

## Executive Summary
- Security posture: medium.
- Critical controls (Telegram HMAC auth, webhook secret, rate limits on orders, WS short-lived tokens) are present.
- Main remaining risks: DOM‑XSS surface in Partner Panel, missing rate limits on high‑read endpoints, and overly permissive partner auth TTL defaults.

## Threat Model (Condensed)
- External clients: WebApp, Partner Panel in Telegram WebView and browsers.
- Trust boundaries: Telegram initData verification; API gateway; DB/Redis; payment webhooks.
- High‑value assets: payment state, order data, partner inventory, store data, user phone numbers.

## Findings

### P1 — DOM XSS surface in Partner Panel (innerHTML + unescaped data)
Problem: Partner Panel templates interpolate server data into `innerHTML` without escaping.
Evidence: `webapp/partner-panel/app.js` (rendering products, orders, modals).
Impact: If a product name/description contains HTML/JS, it can execute in partner sessions.
Recommendation: Escape all dynamic text, or build DOM nodes safely. Avoid `innerHTML` for untrusted data.

### P1 — CSP cannot be fully hardened due to inline handlers
Problem: Partner Panel still relies on inline `onclick` handlers, forcing `'unsafe-inline'` in CSP.
Evidence: `webapp/partner-panel/index.html`, `app/api/api_server.py`.
Impact: CSP is weakened, increasing XSS blast radius in partner panel.
Recommendation: Move all inline handlers to `addEventListener` in JS, then remove `'unsafe-inline'`.

### P1 — Rate limiting gaps on read‑heavy endpoints
Problem: Search/stores/favorites endpoints lack `@limiter`.
Evidence: `app/api/webapp/routes_search.py`, `app/api/webapp/routes_stores.py`, `app/api/webapp/routes_favorites.py`.
Impact: Authenticated abuse can amplify DB load (DoS).
Recommendation: Add per‑route limits similar to orders endpoints.

### P1 — Partner auth TTL effectively ≥24h
Problem: Partner panel auth TTL is clamped to a minimum of 24h.
Evidence: `app/api/partner_panel_simple.py` (`PARTNER_PANEL_AUTH_MAX_AGE_SECONDS` clamp).
Impact: Stolen/old initData can remain valid longer than desired.
Recommendation: Allow tighter TTLs (e.g., 5–30 minutes) for partner panel sessions.

### P2 — Payment card data exposed to any authenticated user
Problem: `/api/v1/payment-card/{store_id}` returns full card number; it only checks that the caller is authenticated.
Evidence: `app/core/webhook_media_routes.py`.
Impact: Authenticated users can fetch card data for arbitrary stores.
Recommendation: Return masked card only, and validate store ownership or permissions.

### P2 — Redis pickle deserialization risk
Problem: Redis cache stores pickled objects; if Redis is exposed, it can be an RCE vector.
Evidence: `app/core/caching.py` (pickle loads).
Impact: Compromised Redis can lead to code execution.
Recommendation: Restrict Redis network access; consider JSON serialization for untrusted caches.

### P2 — Missing HSTS header
Problem: No `Strict-Transport-Security` header.
Evidence: `app/api/api_server.py` security headers.
Impact: Browsers may allow downgrade attacks if TLS is misconfigured upstream.
Recommendation: Add `Strict-Transport-Security` in production (when behind HTTPS).

### P2 — Rate limiting uses X‑Forwarded‑For without trust boundary
Problem: Webhook server rate limiter trusts `X-Forwarded-For` blindly.
Evidence: `app/core/webhook_server.py`.
Impact: If not behind a trusted proxy, attackers can spoof IPs and bypass limits.
Recommendation: Only honor `X-Forwarded-For` when behind trusted proxy; otherwise use `request.remote`.

### P3 — Public photo redirect endpoint
Problem: `/api/v1/photo/{file_id}` is unauthenticated and not rate‑limited.
Evidence: `app/core/webhook_media_routes.py`, `app/api/webapp/routes_photo.py`.
Impact: Can be abused to generate Telegram API traffic.
Recommendation: Add rate limits, or cache aggressively.

## Recent Fixes (Already Implemented)
- Webhook secret required in production. (`app/core/webhook_server.py`)
- Merchant webhooks require signature in production. (`app/api/merchant_webhooks.py`)
- WS short‑lived tokens; init_data no longer accepted. (`app/core/websocket.py`, `app/core/ws_tokens.py`)
- Rate limits added to orders endpoints. (`app/api/orders.py`, `app/api/webapp/routes_orders.py`, `app/api/auth.py`)
- SRI added for partner panel CDN assets; Lucide pinned. (`webapp/partner-panel/index.html`)

## Recommended Next Steps (Priority Order)
1. Remove partner panel inline handlers and stop using `innerHTML` for untrusted data.
2. Add rate limits on search/stores/favorites endpoints.
3. Mask payment card data and check store access.
4. Make partner panel auth TTL configurable below 24h.
5. Add HSTS and tighten proxy trust for rate limiting.
