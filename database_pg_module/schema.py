"""
Database schema initialization.
"""
from __future__ import annotations

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
            
            # Users table
            cursor.execute('''
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Stores table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS stores (
                    store_id SERIAL PRIMARY KEY,
                    owner_id BIGINT,
                    name TEXT NOT NULL,
                    city TEXT NOT NULL,
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
                    FOREIGN KEY (owner_id) REFERENCES users(user_id)
                )
            ''')
            
            # Offers table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS offers (
                    offer_id SERIAL PRIMARY KEY,
                    store_id INTEGER,
                    title TEXT NOT NULL,
                    description TEXT,
                    original_price REAL,
                    discount_price REAL,
                    quantity INTEGER DEFAULT 1,
                    available_from TEXT,
                    available_until TEXT,
                    expiry_date TEXT,
                    photo_id TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    unit TEXT DEFAULT 'шт',
                    category TEXT DEFAULT 'other',
                    FOREIGN KEY (store_id) REFERENCES stores(store_id)
                )
            ''')
            
            # Migration: Add unit and category columns if they don't exist
            try:
                cursor.execute("ALTER TABLE offers ADD COLUMN IF NOT EXISTS unit TEXT DEFAULT 'шт'")
                cursor.execute("ALTER TABLE offers ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'other'")
            except Exception as e:
                logger.warning(f"Migration for offers table: {e}")
            
            # Orders table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    order_id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    offer_id INTEGER,
                    store_id INTEGER,
                    delivery_address TEXT,
                    payment_method TEXT DEFAULT 'card',
                    payment_status TEXT DEFAULT 'pending',
                    payment_proof_photo_id TEXT,
                    order_status TEXT DEFAULT 'pending',
                    quantity INTEGER DEFAULT 1,
                    total_price REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (offer_id) REFERENCES offers(offer_id),
                    FOREIGN KEY (store_id) REFERENCES stores(store_id)
                )
            ''')
            
            # Bookings table
            cursor.execute('''
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
            ''')
            
            # Payment settings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payment_settings (
                    store_id INTEGER PRIMARY KEY,
                    card_number TEXT,
                    card_holder TEXT,
                    card_expiry TEXT,
                    payment_instructions TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (store_id) REFERENCES stores(store_id)
                )
            ''')
            
            # Notifications table
            cursor.execute('''
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
            ''')
            
            # Ratings table
            cursor.execute('''
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
            ''')
            
            # Favorites table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS favorites (
                    favorite_id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    store_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (store_id) REFERENCES stores(store_id),
                    UNIQUE(user_id, store_id)
                )
            ''')
            
            # Promocodes table
            cursor.execute('''
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
            ''')
            
            # Promo usage table
            cursor.execute('''
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
            ''')
            
            # Referrals table
            cursor.execute('''
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
            ''')
            
            # FSM states table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS fsm_states (
                    user_id BIGINT PRIMARY KEY,
                    state TEXT,
                    data JSONB,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Platform settings table (for payment card, etc)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS platform_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Pickup slots table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pickup_slots (
                    store_id INTEGER,
                    slot_ts TEXT,
                    capacity INTEGER DEFAULT 5,
                    reserved INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (store_id, slot_ts),
                    FOREIGN KEY (store_id) REFERENCES stores(store_id)
                )
            ''')
            
            # Create indexes
            self._create_indexes(cursor)
            
            # Run migrations
            self._run_migrations(cursor)
            
            conn.commit()
            logger.info("✅ PostgreSQL database schema initialized successfully")

    def _create_indexes(self, cursor):
        """Create database indexes."""
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_stores_owner ON stores(owner_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_stores_status ON stores(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_offers_store ON offers(store_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_offers_status ON offers(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_store ON orders(store_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ratings_store ON ratings(store_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_favorites_store ON favorites(store_id)')

    def _run_migrations(self, cursor):
        """Run database migrations."""
        self._migrate_favorites_table(cursor)
        self._migrate_stores_delivery(cursor)
        self._migrate_bookings_delivery(cursor)

    def _migrate_favorites_table(self, cursor):
        """Migrate favorites from offer_id to store_id if needed."""
        try:
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='favorites' AND column_name='offer_id'
            """)
            has_offer_id = cursor.fetchone() is not None
            
            if has_offer_id:
                logger.warning("⚠️ Migrating favorites table from offer_id to store_id...")
                cursor.execute("SELECT COUNT(*) FROM favorites")
                count = cursor.fetchone()[0]
                if count > 0:
                    logger.warning(f"⚠️ Found {count} existing favorites - they will be lost")
                
                cursor.execute("DROP TABLE IF EXISTS favorites CASCADE")
                cursor.execute('''
                    CREATE TABLE favorites (
                        favorite_id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        store_id INTEGER NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(user_id),
                        FOREIGN KEY (store_id) REFERENCES stores(store_id),
                        UNIQUE(user_id, store_id)
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_favorites_store ON favorites(store_id)')
                logger.info("✅ Favorites table migrated successfully")
        except Exception as e:
            logger.error(f"Error checking/migrating favorites table: {e}")

    def _migrate_stores_delivery(self, cursor):
        """Add delivery fields to stores table."""
        try:
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='stores' AND column_name='delivery_enabled'
            """)
            has_delivery = cursor.fetchone() is not None
            
            if not has_delivery:
                logger.info("⚠️ Adding delivery fields to stores table...")
                cursor.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS business_type TEXT DEFAULT 'supermarket'")
                cursor.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS delivery_enabled INTEGER DEFAULT 1")
                cursor.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS delivery_price INTEGER DEFAULT 15000")
                cursor.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS min_order_amount INTEGER DEFAULT 30000")
                cursor.execute("UPDATE stores SET delivery_enabled = 1 WHERE delivery_enabled IS NULL")
                logger.info("✅ Delivery fields added to stores table")
        except Exception as e:
            logger.error(f"Error adding delivery fields to stores: {e}")

    def _migrate_bookings_delivery(self, cursor):
        """Add delivery and expiry fields to bookings table."""
        try:
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='bookings' AND column_name='delivery_option'
            """)
            has_booking_delivery = cursor.fetchone() is not None
            
            if not has_booking_delivery:
                logger.info("⚠️ Adding delivery fields to bookings table...")
                cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS delivery_option INTEGER DEFAULT 0")
                cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS delivery_address TEXT")
                cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS delivery_cost INTEGER DEFAULT 0")
                logger.info("✅ Delivery fields added to bookings table")
            
            cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS expiry_time TIMESTAMP")
            cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS reminder_sent INTEGER DEFAULT 0")
            cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS payment_proof_photo_id TEXT")
        except Exception as e:
            logger.warning(f"Could not add columns to bookings: {e}")
