# Refactoring Plan (Fudly) - Full Audit Driven

This document is a full refactoring plan based on the current repository state.
It is intentionally detailed so it can be executed in phases and tracked.

## Scope and Goals

- Reduce codebase entropy: remove duplicates, legacy paths, and unused assets.
- Establish clear boundaries: bot handlers, API, domain/services, data layer.
- Reduce monoliths and improve testability and onboarding.
- Standardize migrations, logging, security, and i18n.
- Clean the repository from generated artifacts and backups.

## Current State: Why the Repo Feels Mixed

- Multiple overlapping layers and entry points (root modules vs app/ core).
- Legacy and "new" flows coexist (bookings, cart, unified orders).
- Direct DB access from handlers and services with duplicated logic.
- Multiple migration systems and many one-off scripts at root.
- Generated artifacts and backups committed (builds, caches, dumps).
- Encoding issues (mojibake) in code and docs.

## Hotspots and Duplication (Examples)

### Monoliths (high risk for changes)
- app/core/webhook_server.py
- app/services/unified_order_service.py
- handlers/bookings/customer.py
- handlers/seller/store_settings.py
- app/api/partner_panel_simple.py
- handlers/admin/dashboard.py
- localization.py

### Overlapping or Redundant Modules
- Database: database.py (wrapper), database_pg.py (wrapper),
  database_pg_module/ (real implementation), app/core/database.py (factory).
- Security: security.py (wrapper) and app/core/security.py (source of truth).
- FSM storage: fsm_storage_pg.py and app/core/fsm_storage.py (two implementations).
- i18n: localization.py + locales/ and app/core/i18n.py (two paths).
- Logging: logging_config.py used everywhere but not inside app/core.
- Orders: booking_service.py, order_service.py, unified_order_service.py,
  plus handlers/common/unified_order/ and handlers/customer/orders/.
- API: app/api/orders.py vs app/api/webapp/routes_orders.py with overlapping DTOs.

### Duplicate Workers / Scripts
- tasks/booking_expiry_worker.py vs scripts/booking_expiry_worker.py
- Root apply_* migration scripts vs scripts/apply_migrations.py vs migrations_alembic/

### Generated / Legacy Artifacts in Repo
- .venv/, __pycache__/, .mypy_cache/, .ruff_cache/, .pytest_cache/, htmlcov/
- .coverage, *.sql backups, database.py.bak
- webapp/node_modules/, webapp/dist/, webapp/src_backup_*
- webapp/partner-panel and webapp/webapp/ alongside webapp/src
- Root .env (should not be committed)

### Encoding Issues
- Mojibake appears in docs and some source files (example: docs/PROJECT_MAP.md,
  app/core/database.py, bot.py). This complicates edits and reviews.

## Target Architecture (North Star)

- Bot layer (handlers/): UI orchestration only, no DB or business logic.
- API layer (app/api/): validation, auth, DTO mapping, no direct SQL.
- Domain layer (app/domain/): entities, value objects, invariants.
- Services (app/services/): business logic and workflows.
- Data layer (app/repositories/ + database_pg_module/): all DB access.
- Infrastructure (app/core/): config, logging, security, i18n, cache, metrics.
- Webapp (webapp/src/): single source of frontend; API client in one place.

## Decision: Canonical Order Flow (Selected)

Source of truth for order creation and status changes is:
- app/services/unified_order_service.py

Primary entry points that must route through it:
- Bot callbacks: handlers/common/unified_order_handlers.py
- Webapp API: app/api/webapp/routes_orders.py
- Webhook flow: app/core/webhook_server.py

Legacy order code to deprecate after migration:
- app/services/booking_service.py
- app/services/order_service.py
- handlers/bookings/* (booking_confirm_* and related legacy callbacks)
- handlers/customer/orders/* fallback flows that bypass unified order service

Immediate fixes required to make this safe:
- Remove or rewire booking_* callbacks that call UnifiedOrderService with
  entity_type="booking" while the service only updates orders.
- Ensure all order creation (cart, pickup, delivery) uses a single DTO and
  status mapping inside unified_order_service.

## Refactoring Roadmap

### Phase 0 - Safety and Inventory (P0)
- Freeze feature work except urgent fixes.
- Create an inventory list of all entry points and long-running workers.
- Add a cleanup list and move generated artifacts out of the repo.
- Fix encoding to UTF-8 and add checks (pre-commit or CI).
- Agree on canonical modules (database, logging, i18n, FSM storage).

### Phase 1 - Core Consolidation (P0/P1)
- Move logging_config.py into app/core/logging.py and update imports.
- Keep compatibility wrappers (database.py, database_pg.py, security.py)
  but relocate them to a legacy/ or compat/ package with warnings.
- Choose a single FSM storage implementation and remove the other.
- Standardize config loading through app/core/config.py only.

### Phase 2 - Data Layer and Domain Boundaries (P1)
- Ensure all SQL stays in database_pg_module/ or app/repositories/.
- Remove direct DB calls from handlers and API routes.
- Introduce explicit repositories for orders, bookings, payments, users.
- Define canonical DTOs for Order, Booking, Payment, Offer.

### Phase 3 - Flow Unification and Handler Split (P1/P2)
- Unify order flows: bookings, cart checkout, unified orders, delivery.
- Pick one source of truth (unified_order_service) and migrate legacy paths.
- Split large handlers into smaller modules by feature sub-flow.
- Move shared UI builders to app/templates/ or app/keyboards/.

### Phase 4 - API and Webapp Contract Cleanup (P1/P2)
- Align app/api/orders.py and app/api/webapp/routes_orders.py with shared DTOs.
- Deprecate old endpoints and remove duplicated "simple" panels.
- Webapp: keep only webapp/src, remove webapp/webapp and src_backup_*.
- Remove webapp/dist from repo; build artifacts belong to CI/CD only.

### Phase 5 - Migrations and Data Ops (P2)
- Choose one migration system (Alembic recommended).
- Deprecate root apply_* scripts and scripts/apply_migrations.py.
- Document a single migration workflow with rollback steps.

### Phase 6 - DevEx and Quality Gates (P2)
- Add lint, type checks, and encoding validation to CI.
- Expand tests around order creation, payment, and cancellation paths.
- Add contract tests for API <-> webapp alignment.

## Deliverables Checklist

- Repository cleanup list applied and .gitignore updated.
- Single source for database, logging, i18n, FSM storage.
- Unified order flow and DTOs with tests.
- Migrations standardized to one toolchain.
- Reduced monoliths with smaller, named modules.
- Encoding normalized to UTF-8 across code and docs.

## Risks and Dependencies

- Order flow unification risks data mismatches and regressions.
- Migration consolidation needs clear rollback and staging validation.
- Webapp changes depend on stable API DTOs and auth boundaries.
- Encoding cleanup can introduce merge conflicts; do it early and once.

## Success Metrics

- No duplicate code paths for orders and payments.
- Fewer than 5 files over 500 lines in handlers/ and services/.
- Onboarding: new dev can find "where to change X" within 5 minutes.
- CI catches auth, order, and encoding regressions consistently.
