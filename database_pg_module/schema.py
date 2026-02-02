"""
Database schema initialization.
"""
from __future__ import annotations

import os

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class SchemaMixin:
    """Mixin for database schema initialization."""

    def init_db(self):
        """Initialize PostgreSQL database schema."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            run_runtime_migrations = (
                os.getenv("RUN_DB_MIGRATIONS", "0").strip().lower() in {"1", "true", "yes"}
            )
            if not run_runtime_migrations:
                logger.info(
                    "Runtime migrations disabled (set RUN_DB_MIGRATIONS=1 to enable)."
                )

            # Users table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    phone TEXT,
                    city TEXT DEFAULT 'Ташкент',
                    language TEXT DEFAULT 'ru',
                    role TEXT DEFAULT 'customer',
                    is_admin INTEGER DEFAULT 0,
                    notifications_enabled INTEGER DEFAULT 1,
                    view_mode TEXT DEFAULT 'customer',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    region TEXT,
                    district TEXT,
                    latitude REAL,
                    longitude REAL,
                    region_id INTEGER,
                    district_id INTEGER
                )
            """
            )

            # Geo reference tables
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS geo_regions (
                    region_id SERIAL PRIMARY KEY,
                    name_ru TEXT NOT NULL,
                    name_uz TEXT NOT NULL,
                    slug_ru TEXT NOT NULL,
                    slug_uz TEXT NOT NULL,
                    is_city INTEGER DEFAULT 0,
                    UNIQUE (slug_ru),
                    UNIQUE (slug_uz)
                )
            """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS geo_districts (
                    district_id SERIAL PRIMARY KEY,
                    region_id INTEGER NOT NULL,
                    name_ru TEXT NOT NULL,
                    name_uz TEXT NOT NULL,
                    slug_ru TEXT NOT NULL,
                    slug_uz TEXT NOT NULL,
                    FOREIGN KEY (region_id) REFERENCES geo_regions(region_id) ON DELETE CASCADE,
                    UNIQUE (region_id, slug_ru),
                    UNIQUE (region_id, slug_uz)
                )
            """
            )

            # Stores table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS stores (
                    store_id SERIAL PRIMARY KEY,
                    owner_id BIGINT,
                    name TEXT NOT NULL,
                    city TEXT NOT NULL,
                    city_slug TEXT,
                    region TEXT,
                    region_slug TEXT,
                    district TEXT,
                    district_slug TEXT,
                    address TEXT,
                    description TEXT,
                    category TEXT DEFAULT 'Ресторан',
                    phone TEXT,
                    status TEXT DEFAULT 'pending',
                    rejection_reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    business_type TEXT DEFAULT 'supermarket',
                    delivery_enabled INTEGER DEFAULT 1,
                    delivery_price INTEGER DEFAULT 15000,
                    min_order_amount INTEGER DEFAULT 30000,
                    region_id INTEGER,
                    district_id INTEGER,
                    FOREIGN KEY (owner_id) REFERENCES users(user_id)
                )
            """
            )

            # Offers table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS offers (
                    offer_id SERIAL PRIMARY KEY,
                    store_id INTEGER,
                    title TEXT NOT NULL,
                    description TEXT,
                    original_price INTEGER,
                    discount_price INTEGER,
                    quantity INTEGER DEFAULT 1,
                    stock_quantity INTEGER DEFAULT 0,
                    available_from TIME,
                    available_until TIME,
                    expiry_date DATE,
                    photo_id TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    unit TEXT DEFAULT 'шт',
                    category TEXT DEFAULT 'other',
                    FOREIGN KEY (store_id) REFERENCES stores(store_id)
                )
            """
            )

            # Migration: Add unit and category columns if they don't exist
            if run_runtime_migrations:
                try:
                    cursor.execute(
                        "ALTER TABLE offers ADD COLUMN IF NOT EXISTS stock_quantity INTEGER DEFAULT 0"
                    )
                    cursor.execute(
                        """
                        UPDATE offers
                        SET stock_quantity = COALESCE(quantity, 0)
                        WHERE stock_quantity IS NULL
                           OR (stock_quantity = 0 AND COALESCE(quantity, 0) > 0)
                        """
                    )
                    cursor.execute("ALTER TABLE offers ADD COLUMN IF NOT EXISTS unit TEXT DEFAULT 'шт'")
                    cursor.execute(
                        "ALTER TABLE offers ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'other'"
                    )
                except Exception as e:
                    logger.warning(f"Migration for offers table: {e}")
                    conn.rollback()

            # Migration: Add photo column to stores table if it doesn't exist
            if run_runtime_migrations:
                try:
                    cursor.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS photo TEXT")
                except Exception as e:
                    logger.warning(f"Migration for stores photo column: {e}")
                    conn.rollback()
            # Migration: Add region/district columns to stores table if they don't exist
            if run_runtime_migrations:
                try:
                    cursor.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS region TEXT")
                    cursor.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS district TEXT")
                    cursor.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS city_slug TEXT")
                    cursor.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS region_slug TEXT")
                    cursor.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS district_slug TEXT")
                except Exception as e:
                    logger.warning(f"Migration for stores region/district columns: {e}")
                    conn.rollback()
            # Migration: Add geo reference ids to users/stores tables
            if run_runtime_migrations:
                try:
                    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS region_id INTEGER")
                    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS district_id INTEGER")
                    cursor.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS region_id INTEGER")
                    cursor.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS district_id INTEGER")
                except Exception as e:
                    logger.warning(f"Migration for geo reference ids: {e}")
                    conn.rollback()
            # Migration: Add geo reference foreign keys
            if run_runtime_migrations:
                try:
                    cursor.execute(
                        """
                        ALTER TABLE users
                        ADD CONSTRAINT fk_users_region_id
                        FOREIGN KEY (region_id) REFERENCES geo_regions(region_id)
                        """
                    )
                except Exception as e:
                    logger.warning(f"Migration for fk_users_region_id: {e}")
                    conn.rollback()
                try:
                    cursor.execute(
                        """
                        ALTER TABLE users
                        ADD CONSTRAINT fk_users_district_id
                        FOREIGN KEY (district_id) REFERENCES geo_districts(district_id)
                        """
                    )
                except Exception as e:
                    logger.warning(f"Migration for fk_users_district_id: {e}")
                    conn.rollback()
                try:
                    cursor.execute(
                        """
                        ALTER TABLE stores
                        ADD CONSTRAINT fk_stores_region_id
                        FOREIGN KEY (region_id) REFERENCES geo_regions(region_id)
                        """
                    )
                except Exception as e:
                    logger.warning(f"Migration for fk_stores_region_id: {e}")
                    conn.rollback()
                try:
                    cursor.execute(
                        """
                        ALTER TABLE stores
                        ADD CONSTRAINT fk_stores_district_id
                        FOREIGN KEY (district_id) REFERENCES geo_districts(district_id)
                        """
                    )
                except Exception as e:
                    logger.warning(f"Migration for fk_stores_district_id: {e}")
                    conn.rollback()
            # Seed geo reference tables if empty
            if run_runtime_migrations:
                try:
                    cursor.execute("SELECT COUNT(*) FROM geo_regions")
                    geo_regions_count = cursor.fetchone()[0] or 0
                    if geo_regions_count == 0:
                        from database_pg_module.mixins.offers import canonicalize_geo_slug

                        regions = [
                            {
                                "ru": "Ташкент",
                                "uz": "Toshkent",
                                "is_city": 1,
                                "districts": [
                                    {"ru": "Бектемир", "uz": "Bektemir"},
                                    {"ru": "Мирабад", "uz": "Mirobod"},
                                    {"ru": "Мирзо-Улугбек", "uz": "Mirzo Ulug'bek"},
                                    {"ru": "Сергелий", "uz": "Sergeli"},
                                    {"ru": "Шайхантахур", "uz": "Shayxontohur"},
                                    {"ru": "Учтепа", "uz": "Uchtepa"},
                                    {"ru": "Яшнабад", "uz": "Yashnobod"},
                                    {"ru": "Янгихаёт", "uz": "Yangihayot"},
                                    {"ru": "Юнусабад", "uz": "Yunusobod"},
                                    {"ru": "Яккасарай", "uz": "Yakkasaroy"},
                                    {"ru": "Алмазар", "uz": "Olmazor"},
                                    {"ru": "Чиланзар", "uz": "Chilonzor"},
                                ],
                            },
                            {
                                "ru": "Ташкентская область",
                                "uz": "Toshkent viloyati",
                                "is_city": 0,
                                "districts": [],
                                "slug_uz": "toshkent_viloyati",
                            },
                            {
                                "ru": "Андижан",
                                "uz": "Andijon",
                                "is_city": 0,
                                "districts": [],
                            },
                            {
                                "ru": "Бухара",
                                "uz": "Buxoro",
                                "is_city": 0,
                                "districts": [],
                            },
                            {
                                "ru": "Фергана",
                                "uz": "Farg'ona",
                                "is_city": 0,
                                "districts": [],
                            },
                            {
                                "ru": "Джизак",
                                "uz": "Jizzax",
                                "is_city": 0,
                                "districts": [],
                            },
                            {
                                "ru": "Наманган",
                                "uz": "Namangan",
                                "is_city": 0,
                                "districts": [],
                            },
                            {
                                "ru": "Навои",
                                "uz": "Navoiy",
                                "is_city": 0,
                                "districts": [],
                            },
                            {
                                "ru": "Кашкадарья",
                                "uz": "Qashqadaryo",
                                "is_city": 0,
                                "districts": [],
                            },
                            {
                                "ru": "Самарканд",
                                "uz": "Samarqand",
                                "is_city": 0,
                                "districts": [
                                    {"ru": "Самарканд", "uz": "Samarqand"},
                                    {"ru": "Каттакурган", "uz": "Kattaqo'rg'on"},
                                    {"ru": "Акдарья", "uz": "Oqdaryo"},
                                    {"ru": "Булунгур", "uz": "Bulung'ur"},
                                    {"ru": "Джамбай", "uz": "Jomboy"},
                                    {"ru": "Иштыхан", "uz": "Ishtixon"},
                                    {"ru": "Кошрабад", "uz": "Qo'shrabot"},
                                    {"ru": "Нарпай", "uz": "Narpay"},
                                    {"ru": "Нурабад", "uz": "Nurobod"},
                                    {"ru": "Пайарык", "uz": "Payariq"},
                                    {"ru": "Пастдаргом", "uz": "Pastdarg'om"},
                                    {"ru": "Пахтачи", "uz": "Paxtachi"},
                                    {"ru": "Тайлак", "uz": "Toyloq"},
                                    {"ru": "Ургут", "uz": "Urgut"},
                                ],
                            },
                            {
                                "ru": "Сырдарья",
                                "uz": "Sirdaryo",
                                "is_city": 0,
                                "districts": [],
                            },
                            {
                                "ru": "Сурхандарья",
                                "uz": "Surxondaryo",
                                "is_city": 0,
                                "districts": [],
                            },
                            {
                                "ru": "Хорезм",
                                "uz": "Xorazm",
                                "is_city": 0,
                                "districts": [],
                            },
                            {
                                "ru": "Каракалпакстан",
                                "uz": "Qoraqalpog'iston",
                                "is_city": 0,
                                "districts": [],
                            },
                        ]

                        for region in regions:
                            slug_uz = region.get("slug_uz") or canonicalize_geo_slug(region["uz"])
                            slug_ru = canonicalize_geo_slug(region["ru"])
                            cursor.execute(
                                """
                                INSERT INTO geo_regions (name_ru, name_uz, slug_ru, slug_uz, is_city)
                                VALUES (%s, %s, %s, %s, %s)
                                RETURNING region_id
                                """,
                                (
                                    region["ru"],
                                    region["uz"],
                                    slug_ru,
                                    slug_uz,
                                    int(region.get("is_city", 0)),
                                ),
                            )
                            region_id = cursor.fetchone()[0]
                            for district in region.get("districts", []):
                                cursor.execute(
                                    """
                                    INSERT INTO geo_districts (region_id, name_ru, name_uz, slug_ru, slug_uz)
                                    VALUES (%s, %s, %s, %s, %s)
                                    """,
                                    (
                                        region_id,
                                        district["ru"],
                                        district["uz"],
                                        canonicalize_geo_slug(district["ru"]),
                                        canonicalize_geo_slug(district["uz"]),
                                    ),
                                )
                except Exception as e:
                    logger.warning(f"Geo reference seed failed: {e}")
                    conn.rollback()

            # Orders table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    order_id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    offer_id INTEGER,
                    store_id INTEGER,
                    delivery_address TEXT,
                    comment TEXT,
                    delivery_city TEXT,
                    delivery_region TEXT,
                    delivery_district TEXT,
                    delivery_lat REAL,
                    delivery_lon REAL,
                    delivery_structured JSONB,
                    delivery_price INTEGER,
                    payment_method TEXT DEFAULT 'cash',
                    payment_status TEXT DEFAULT 'not_required',
                    payment_proof_photo_id TEXT,
                    order_status TEXT DEFAULT 'pending',
                    cancel_reason VARCHAR(50),
                    cancel_comment TEXT,
                    quantity INTEGER DEFAULT 1,
                    total_price REAL,
                    item_title TEXT,
                    item_price INTEGER,
                    item_original_price INTEGER,
                    pickup_code TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (offer_id) REFERENCES offers(offer_id),
                    FOREIGN KEY (store_id) REFERENCES stores(store_id)
                )
            """
            )

            # Migration: Add pickup_code column to orders table
            if run_runtime_migrations:
                try:
                    cursor.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS pickup_code TEXT")
                except Exception as e:
                    logger.warning(f"Migration for orders pickup_code column: {e}")
                try:
                    cursor.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_city TEXT")
                    cursor.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_region TEXT")
                    cursor.execute(
                        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_district TEXT"
                    )
                    cursor.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS comment TEXT")
                    cursor.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_lat REAL")
                    cursor.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_lon REAL")
                    cursor.execute(
                        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_structured JSONB"
                    )
                    cursor.execute(
                        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_price INTEGER"
                    )
                    cursor.execute(
                        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS item_title TEXT"
                    )
                    cursor.execute(
                        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS item_price INTEGER"
                    )
                    cursor.execute(
                        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS item_original_price INTEGER"
                    )
                except Exception as e:
                    logger.warning(f"Migration for orders delivery structured columns: {e}")

            # Migration: Add cart_items column to orders table for multi-item orders
            if run_runtime_migrations:
                try:
                    cursor.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS cart_items JSONB")
                    cursor.execute(
                        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS is_cart_order INTEGER DEFAULT 0"
                    )
                except Exception as e:
                    logger.warning(f"Migration for orders cart columns: {e}")

            # Migration: Add customer_message_id for editable status notifications
            if run_runtime_migrations:
                try:
                    cursor.execute(
                        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_message_id BIGINT"
                    )
                except Exception as e:
                    logger.warning(f"Migration for orders customer_message_id: {e}")

            # Migration: Add seller_message_id for editable seller notifications
            if run_runtime_migrations:
                try:
                    cursor.execute(
                        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS seller_message_id BIGINT"
                    )
                except Exception as e:
                    logger.warning(f"Migration for orders seller_message_id: {e}")

            # Migration: Add order_type column to orders (pickup/delivery)
            if run_runtime_migrations:
                try:
                    cursor.execute(
                        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS order_type TEXT DEFAULT 'delivery'"
                    )
                except Exception as e:
                    logger.warning(f"Migration for orders order_type: {e}")

            # Migration: Add cancel_reason/cancel_comment for partner cancellations
            if run_runtime_migrations:
                try:
                    cursor.execute(
                        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS cancel_reason VARCHAR(50)"
                    )
                    cursor.execute(
                        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS cancel_comment TEXT"
                    )
                except Exception as e:
                    logger.warning(f"Migration for orders cancel fields: {e}")

            # Migration: Add rating_reminder_sent and updated_at for rating reminders
            if run_runtime_migrations:
                try:
                    cursor.execute(
                        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS rating_reminder_sent BOOLEAN DEFAULT false"
                    )
                    cursor.execute(
                        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                    )
                except Exception as e:
                    logger.warning(f"Migration for orders rating_reminder: {e}")

            # Bookings table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS bookings (
                    booking_id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    offer_id INTEGER,
                    store_id INTEGER,
                    quantity INTEGER DEFAULT 1,
                    booking_code TEXT,
                    pickup_time TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (offer_id) REFERENCES offers(offer_id),
                    FOREIGN KEY (store_id) REFERENCES stores(store_id)
                )
            """
            )

            # Migration: Add cart_items column to bookings table for multi-item bookings
            if run_runtime_migrations:
                try:
                    cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS cart_items JSONB")
                    cursor.execute(
                        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS is_cart_booking INTEGER DEFAULT 0"
                    )
                except Exception as e:
                    logger.warning(f"Migration for bookings cart columns: {e}")

            # Migration: Add customer_message_id for editable status notifications
            if run_runtime_migrations:
                try:
                    cursor.execute(
                        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS customer_message_id BIGINT"
                    )
                except Exception as e:
                    logger.warning(f"Migration for bookings customer_message_id: {e}")

            # Migration: Add seller_message_id for editable seller notifications
            if run_runtime_migrations:
                try:
                    cursor.execute(
                        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS seller_message_id BIGINT"
                    )
                except Exception as e:
                    logger.warning(f"Migration for bookings seller_message_id: {e}")

            # Migration: Add rating_reminder_sent and updated_at for rating reminders
            if run_runtime_migrations:
                try:
                    cursor.execute(
                        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS rating_reminder_sent BOOLEAN DEFAULT false"
                    )
                    cursor.execute(
                        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                    )
                except Exception as e:
                    logger.warning(f"Migration for bookings rating_reminder: {e}")

            # Payment settings table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS payment_settings (
                    store_id INTEGER PRIMARY KEY,
                    card_number TEXT,
                    card_holder TEXT,
                    card_expiry TEXT,
                    payment_instructions TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (store_id) REFERENCES stores(store_id)
                )
            """
            )

            # Store payment integrations table (Click/Payme per store)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS store_payment_integrations (
                    id SERIAL PRIMARY KEY,
                    store_id INTEGER NOT NULL,
                    provider TEXT NOT NULL,
                    merchant_id TEXT,
                    merchant_user_id TEXT,
                    service_id TEXT,
                    secret_key TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (store_id) REFERENCES stores(store_id),
                    UNIQUE(store_id, provider)
                )
            """
            )

            # Uzum Bank merchant transactions
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS uzum_transactions (
                    id SERIAL PRIMARY KEY,
                    trans_id UUID UNIQUE NOT NULL,
                    order_id INTEGER NOT NULL,
                    service_id BIGINT,
                    amount BIGINT NOT NULL,
                    status TEXT NOT NULL,
                    payload JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (order_id) REFERENCES orders(order_id)
                )
                """
            )

            # Migration: add merchant_user_id to store_payment_integrations if missing
            if run_runtime_migrations:
                try:
                    cursor.execute(
                        "ALTER TABLE store_payment_integrations ADD COLUMN IF NOT EXISTS merchant_user_id TEXT"
                    )
                except Exception as e:
                    logger.warning(
                        f"Migration for store_payment_integrations.merchant_user_id: {e}"
                    )

            # Click fiscalization tracking
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS click_fiscalization (
                    id SERIAL PRIMARY KEY,
                    order_id INTEGER,
                    payment_id TEXT NOT NULL,
                    service_id TEXT,
                    status TEXT DEFAULT 'pending',
                    error_code INTEGER,
                    error_note TEXT,
                    request_payload JSONB,
                    response_payload JSONB,
                    qr_code_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(order_id, payment_id),
                    FOREIGN KEY (order_id) REFERENCES orders(order_id)
                )
                """
            )

            # Click transactions (Prepare/Complete idempotency)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS click_transactions (
                    id SERIAL PRIMARY KEY,
                    click_trans_id BIGINT UNIQUE NOT NULL,
                    click_paydoc_id TEXT,
                    merchant_trans_id TEXT,
                    merchant_prepare_id TEXT,
                    service_id TEXT,
                    amount TEXT,
                    status TEXT DEFAULT 'prepared',
                    error_code INTEGER,
                    error_note TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            if run_runtime_migrations:
                try:
                    cursor.execute(
                        "ALTER TABLE click_transactions ADD COLUMN IF NOT EXISTS click_paydoc_id TEXT"
                    )
                except Exception as e:
                    logger.warning(f"Migration for click_transactions click_paydoc_id: {e}")

            # Store admins table (multiple admins per store)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS store_admins (
                    id SERIAL PRIMARY KEY,
                    store_id INTEGER NOT NULL,
                    user_id BIGINT NOT NULL,
                    role TEXT DEFAULT 'admin',
                    added_by BIGINT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (store_id) REFERENCES stores(store_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (added_by) REFERENCES users(user_id),
                    UNIQUE(store_id, user_id)
                )
            """
            )

            # Notifications table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS notifications (
                    notification_id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    type TEXT,
                    title TEXT,
                    message TEXT,
                    is_read INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """
            )

            # Ratings table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS ratings (
                    rating_id SERIAL PRIMARY KEY,
                    booking_id INTEGER,
                    user_id BIGINT,
                    store_id INTEGER,
                    order_id INTEGER,
                    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
                    comment TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (booking_id) REFERENCES bookings(booking_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (store_id) REFERENCES stores(store_id),
                    FOREIGN KEY (order_id) REFERENCES orders(order_id)
                )
            """
            )

            # Favorites table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS favorites (
                    favorite_id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    store_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (store_id) REFERENCES stores(store_id),
                    UNIQUE(user_id, store_id)
                )
            """
            )

            # Favorite offers table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS favorite_offers (
                    favorite_id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    offer_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (offer_id) REFERENCES offers(offer_id),
                    UNIQUE(user_id, offer_id)
                )
            """
            )

            # Promocodes table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS promocodes (
                    promo_id SERIAL PRIMARY KEY,
                    code TEXT UNIQUE NOT NULL,
                    discount_percent INTEGER,
                    discount_amount REAL,
                    max_uses INTEGER DEFAULT 0,
                    current_uses INTEGER DEFAULT 0,
                    valid_from TIMESTAMP,
                    valid_until TIMESTAMP,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Promo usage table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS promo_usage (
                    usage_id SERIAL PRIMARY KEY,
                    promo_id INTEGER,
                    user_id BIGINT,
                    order_id INTEGER,
                    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (promo_id) REFERENCES promocodes(promo_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (order_id) REFERENCES orders(order_id)
                )
            """
            )

            # Referrals table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS referrals (
                    referral_id SERIAL PRIMARY KEY,
                    referrer_user_id BIGINT,
                    referred_user_id BIGINT,
                    bonus_amount REAL DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (referrer_user_id) REFERENCES users(user_id),
                    FOREIGN KEY (referred_user_id) REFERENCES users(user_id)
                )
            """
            )

            # FSM states table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS fsm_states (
                    user_id BIGINT NOT NULL,
                    chat_id BIGINT NOT NULL,
                    state TEXT,
                    state_name TEXT,
                    data JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    PRIMARY KEY (user_id, chat_id)
                )
            """
            )

            # Recently viewed offers table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS recently_viewed (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    offer_id INTEGER NOT NULL,
                    viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (offer_id) REFERENCES offers(offer_id)
                )
            """
            )

            # Search history table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS search_history (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    query TEXT NOT NULL,
                    searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """
            )

            # Platform settings table (for payment card, etc)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS platform_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Pickup slots table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS pickup_slots (
                    store_id INTEGER,
                    slot_ts TEXT,
                    capacity INTEGER DEFAULT 5,
                    reserved INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (store_id, slot_ts),
                    FOREIGN KEY (store_id) REFERENCES stores(store_id)
                )
            """
            )

            # Create indexes
            if run_runtime_migrations:
                self._create_indexes(cursor)
                # Run migrations
                self._run_migrations(cursor)

            conn.commit()
            logger.info("✅ PostgreSQL database schema initialized successfully")

    def _create_indexes(self, cursor):
        """Create database indexes."""
        # Store indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stores_owner ON stores(owner_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stores_status ON stores(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stores_city ON stores(city)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stores_city_status ON stores(city, status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stores_region ON stores(region)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stores_district ON stores(district)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stores_region_id ON stores(region_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stores_district_id ON stores(district_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stores_city_slug ON stores(city_slug)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stores_region_slug ON stores(region_slug)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stores_district_slug ON stores(district_slug)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stores_city_slug_status ON stores(city_slug, status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_region_id ON users(region_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_district_id ON users(district_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_geo_regions_slug_ru ON geo_regions(slug_ru)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_geo_regions_slug_uz ON geo_regions(slug_uz)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_geo_districts_region_id ON geo_districts(region_id)")

        # Offer indexes - critical for browsing/search performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_offers_store ON offers(store_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_offers_status ON offers(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_offers_category ON offers(category)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_offers_status_store ON offers(status, store_id)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_offers_expiry ON offers(expiry_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_offers_stock ON offers(stock_quantity)")

        # Order indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_store ON orders(store_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(order_status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at DESC)")

        # Booking indexes - critical for daily operations
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookings_store ON bookings(store_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookings_offer ON bookings(offer_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bookings_code ON bookings(booking_code)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_bookings_created ON bookings(created_at DESC)"
        )

        # Notification indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(user_id, is_read)"
        )

        # Rating and favorites indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ratings_store ON ratings(store_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ratings_user ON ratings(user_id)")
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_ratings_booking_unique ON ratings(booking_id)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_favorites_store ON favorites(store_id)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_favorite_offers_user ON favorite_offers(user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_favorite_offers_offer ON favorite_offers(offer_id)"
        )

        # Search optimization indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_recently_viewed_user ON recently_viewed(user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_search_history_user ON search_history(user_id)"
        )

    def _run_migrations(self, cursor):
        """Run database migrations."""
        self._migrate_favorites_table(cursor)
        self._migrate_stores_delivery(cursor)
        self._migrate_bookings_delivery(cursor)
        self._migrate_user_view_mode(cursor)

    def _migrate_user_view_mode(self, cursor):
        """Add view_mode column to users table if not exists."""
        try:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS view_mode TEXT DEFAULT 'customer'"
            )
            logger.info("✅ view_mode column ensured in users table")
        except Exception as e:
            logger.warning(f"Could not add view_mode column: {e}")

        # Add last_delivery_address for saved addresses
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_delivery_address TEXT")
            logger.info("✅ last_delivery_address column ensured in users table")
        except Exception as e:
            logger.warning(f"Could not add last_delivery_address column: {e}")

        # Add location fields for user-level search scoping
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS region TEXT")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS district TEXT")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS latitude REAL")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS longitude REAL")
            logger.info("INFO: user location columns ensured in users table")
        except Exception as e:
            logger.warning(f"Could not add user location columns: {e}")

    def _migrate_favorites_table(self, cursor):
        """Migrate favorites from offer_id to store_id if needed."""
        try:
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='favorites' AND column_name='offer_id'
            """
            )
            has_offer_id = cursor.fetchone() is not None

            if has_offer_id:
                logger.warning("⚠️ Migrating favorites table from offer_id to store_id...")
                cursor.execute("SELECT COUNT(*) FROM favorites")
                count = cursor.fetchone()[0]
                if count > 0:
                    logger.warning(f"⚠️ Found {count} existing favorites - they will be lost")

                cursor.execute("DROP TABLE IF EXISTS favorites CASCADE")
                cursor.execute(
                    """
                    CREATE TABLE favorites (
                        favorite_id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        store_id INTEGER NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(user_id),
                        FOREIGN KEY (store_id) REFERENCES stores(store_id),
                        UNIQUE(user_id, store_id)
                    )
                """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_favorites_store ON favorites(store_id)"
                )
                logger.info("✅ Favorites table migrated successfully")
        except Exception as e:
            logger.error(f"Error checking/migrating favorites table: {e}")

    def _migrate_stores_delivery(self, cursor):
        """Add delivery fields to stores table."""
        try:
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='stores' AND column_name='delivery_enabled'
            """
            )
            has_delivery = cursor.fetchone() is not None

            if not has_delivery:
                logger.info("⚠️ Adding delivery fields to stores table...")
                cursor.execute(
                    "ALTER TABLE stores ADD COLUMN IF NOT EXISTS business_type TEXT DEFAULT 'supermarket'"
                )
                cursor.execute(
                    "ALTER TABLE stores ADD COLUMN IF NOT EXISTS delivery_enabled INTEGER DEFAULT 1"
                )
                cursor.execute(
                    "ALTER TABLE stores ADD COLUMN IF NOT EXISTS delivery_price INTEGER DEFAULT 15000"
                )
                cursor.execute(
                    "ALTER TABLE stores ADD COLUMN IF NOT EXISTS min_order_amount INTEGER DEFAULT 30000"
                )
                cursor.execute(
                    "UPDATE stores SET delivery_enabled = 1 WHERE delivery_enabled IS NULL"
                )
                logger.info("✅ Delivery fields added to stores table")

            # Add geolocation fields
            cursor.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS latitude REAL")
            cursor.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS longitude REAL")
            cursor.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS rating REAL DEFAULT 0")
        except Exception as e:
            logger.error(f"Error adding delivery fields to stores: {e}")

    def _migrate_bookings_delivery(self, cursor):
        """Add delivery and expiry fields to bookings table."""
        try:
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='bookings' AND column_name='delivery_option'
            """
            )
            has_booking_delivery = cursor.fetchone() is not None

            if not has_booking_delivery:
                logger.info("⚠️ Adding delivery fields to bookings table...")
                cursor.execute(
                    "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS delivery_option INTEGER DEFAULT 0"
                )
                cursor.execute(
                    "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS delivery_address TEXT"
                )
                cursor.execute(
                    "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS delivery_cost INTEGER DEFAULT 0"
                )
                logger.info("✅ Delivery fields added to bookings table")

            cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS expiry_time TIMESTAMP")
            cursor.execute(
                "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS reminder_sent INTEGER DEFAULT 0"
            )
            cursor.execute(
                "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS partner_reminder_sent INTEGER DEFAULT 0"
            )
            cursor.execute(
                "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS payment_proof_photo_id TEXT"
            )
            cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS pickup_address TEXT")
            cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS delivery_city TEXT")
            cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS delivery_region TEXT")
            cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS delivery_district TEXT")
            cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS delivery_lat REAL")
            cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS delivery_lon REAL")
            cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS delivery_structured JSONB")

        except Exception as e:
            logger.warning(f"Could not add columns to bookings: {e}")
