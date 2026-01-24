# Agent Guide (Detailed)

This file guides automated agents working on this repository. Keep changes small, follow existing patterns, and avoid committing secrets.

## Purpose and expectations
- Prefer minimal, well-scoped changes and preserve existing behavior.
- Follow the established architecture (handlers, services, repositories) instead of adding ad-hoc logic in bot.py.
- Keep user-facing text in localization files (localization.py + locales/).
- Update tests when behavior changes; avoid breaking production flows.

## Project snapshot
- Language/runtime: Python 3.10+ (aiogram 3.x).
- Bot entry point: bot.py (polling or webhook).
- Mini App + partner panel API: FastAPI (app/api/api_server.py) served by uvicorn.
- Storage: PostgreSQL (recommended) or SQLite fallback; optional Redis caching.
- Migrations: Alembic (migrations_alembic, configured in alembic.ini).
- Payments: Telegram Payments (Click provider) and direct Click Merchant API.

## Runtime topology
### Telegram bot
- bot.py wires routers, services, and starts polling or webhook mode.
- Webhook controls: USE_WEBHOOK, WEBHOOK_URL, WEBHOOK_PATH, PORT.
- Bot routes are split into handlers/ by feature. See handlers/README.md.

### Mini App API (FastAPI)
- app/api/api_server.py creates the FastAPI app.
- Routers: auth, orders, partner_panel_simple, webapp_api, merchant_webhooks.
- Static mounts:
  - webapp/dist (Mini App assets)
  - webapp/partner-panel (partner panel assets)

### Background/maintenance
- scripts/booking_expiry_worker.py and scripts/run_booking_worker.py: reminders + auto-cancel expired bookings.
- scripts/README.md: overview of maintenance utilities.

## Key domains and flows
### Orders and payments (unified)
- Domain types and status normalization: app/domain/order.py (OrderStatus, PaymentStatus).
- Service orchestration: app/services/unified_order_service.py.
- Use-cases: app/application/orders/{confirm_payment,reject_payment,submit_payment_proof}.py.
- Data access: app/infra/db/orders_repo.py.
- Bot presenters: app/interfaces/bot/presenters/* for order/payment messages.
- API endpoints: app/api/orders.py and app/api/merchant_webhooks.py.

Guidance:
- Keep payment status transitions consistent with PaymentStatus.normalize/initial_for_method.
- For new order flows, update both bot and API surfaces if needed.

### Offers, bookings, users, stats
- Services: app/services/offer_service.py, booking_service.py, search_service.py, stats.py.
- Repositories: app/repositories/* (user, store, offer, booking, cached wrappers).
- Handlers: handlers/customer, handlers/seller, handlers/bookings, handlers/admin.

### API security and rate limiting
- FastAPI uses slowapi rate limiting and strict CORS headers.
- Avoid widening CORS or security headers unless required.
- Any new API route should be added in app/api/api_server.py with the correct DB injection.

## Repository map (important paths)
- bot.py: application bootstrap and router wiring.
- app/core/: bootstrap, config, cache, utils, exceptions.
- app/services/: business logic.
- app/repositories/: data access wrappers (shared).
- app/infra/db/: infra repositories for orders.
- app/application/orders/: order payment use-cases.
- app/domain/: domain entities, models, value objects.
- app/interfaces/bot/presenters/: message builders for bot flows.
- app/api/: FastAPI endpoints + webapp/partner panel wiring.
- handlers/: aiogram routers by feature (see handlers/README.md).
- localization.py + locales/: all user-facing strings.
- migrations_alembic/: Alembic migration scripts (see alembic.ini).
- webapp/: front-end build output and partner panel assets.

## Configuration (.env)
See .env.example for the full list. Key groups:
- Core: TELEGRAM_BOT_TOKEN, ADMIN_ID, WEBAPP_URL.
- Webhook: USE_WEBHOOK, WEBHOOK_URL, WEBHOOK_PATH, PORT.
- Database: DATABASE_URL (Postgres) or DATABASE_PATH (SQLite), DB_MIN_CONN, DB_MAX_CONN.
- Cache/logging: REDIS_URL, LOG_LEVEL, CACHE_TTL_SECONDS.
- Security: SECRET_TOKEN, ENCRYPTION_KEY.
- Payments: TELEGRAM_PAYMENT_PROVIDER_TOKEN, CLICK_* (merchant + fiscalization).

Never commit real tokens. Use .env for local runs.

## Quick start (PowerShell)
```powershell
# Create/activate venv (if you use one)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install deps
pip install -r requirements.txt

# Configure env
Copy-Item .env.example .env
# Edit .env with TELEGRAM_BOT_TOKEN and ADMIN_ID

# Run the bot (polling)
python bot.py
```

## Common commands
```powershell
# Tests
pytest
pytest -v -s
pytest --cov=app --cov=handlers --cov-report=html

# Lint/format/type-check
black .
ruff check .
mypy .

# Alembic migrations
python scripts/migrate.py upgrade
python scripts/migrate.py downgrade
python scripts/migrate.py current
python scripts/migrate.py history
python scripts/migrate.py new "Add new_column to users"
```

## Migrations
- Managed by Alembic; configured in alembic.ini.
- Migration scripts live in migrations_alembic/.
- scripts/migrate.py wraps common Alembic commands and reads DATABASE_URL.
- When you change schema, add a migration and update both Postgres and SQLite paths if they diverge.

## Localization rules
- Do not hardcode user-facing strings in handlers or services.
- Add or update strings in localization.py and locales/ and use helpers to resolve them.

## Change guidance (practical)
- Prefer adding/modifying handlers in handlers/; keep bot.py mostly wiring.
- Keep business rules inside services; keep I/O in repositories and API layers.
- For new API endpoints, register the router in app/api/api_server.py and wire DB dependencies.
- For payment changes, update:
  - app/domain/order.py status rules
  - app/services/unified_order_service.py
  - app/application/orders/* use-cases
  - app/interfaces/bot/presenters/* messages
- Keep Click and Telegram payment logic consistent with existing env flags.

## Debugging tips
- If the Mini App or partner panel static files are missing, confirm webapp/dist and webapp/partner-panel exist.
- If migrations fail, check DATABASE_URL and alembic.ini script_location.
- If bot text looks wrong, check localization.py + locales/ first.

## References
- DEV_SETUP.md: developer setup and tooling.
- handlers/README.md: handler migration pattern and stats integration notes.
- scripts/README.md: maintenance utilities overview.
