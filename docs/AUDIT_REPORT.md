# Audit Report (Condensed)

Date: 2025-12-22
Scope: bot, API, partner panel, mini app (code + docs review)

## Critical issues
- Partner panel product management is non-functional: add/edit UI is TODO and API expects form while frontend sends JSON (broken stock updates).
- Product photos do not render: API returns no `photo_url` and uses a wrong path for Telegram file proxy.
- Mini app cart/checkout has conflicting state formats, causing order drift.
- DB performance risks: N+1 queries + missing indexes for frequent order/offer lookups.
- Security gaps: rate limits missing on critical endpoints; credentials stored unencrypted (per docs).

## High issues
- Legacy order services coexist with UnifiedOrderService, risking logic divergence.
- Duplicate API logic between webhook server and FastAPI webapp routes.
- Partner panel status filters mismatch with backend status fields.

## Medium/Low
- UX gaps: missing loading/error states, missing ErrorBoundary in mini app.
- Large components and inconsistent i18n.
- Legacy/backup files in repo.

## Target architecture (summary)
- Unified orders only (orders table + UnifiedOrderService), deprecate bookings.
- Single DTO mapping for webapp + partner panel.
- Centralized photo proxy endpoint.
- Batch DB queries + indexes for orders/offers/stores.

## Fix plan (first pass)
1) Partner panel API: accept JSON bodies for product create/update + fix photo URL field.
2) Partner panel frontend: wire add/edit product flows and correct filters.
3) Mini app: unify cart + checkout flow.
4) DB: address N+1 and add indexes.
