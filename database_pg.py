"""
PostgreSQL Database Module for Fudly Bot
Replaces SQLite with PostgreSQL for production deployment
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, List, Optional, Tuple

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

# Logging
try:
    from logging_config import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# Cache (optional)
try:
    from cache import cache  # type: ignore[import]
except ImportError:
    class SimpleCache:
        def get(self, key: str) -> Any:
            return None
        def set(self, key: str, value: Any, ex: Optional[int] = None) -> None:
            pass
        def delete(self, key: str) -> None:
            pass
    cache = SimpleCache()

class HybridRow:
    """
    A row object that supports both index access (like a tuple) and key access (like a dict).
    This allows for a smooth transition from tuple-based code to dict-based code.
    """
    def __init__(self, cursor, values):
        self._data = dict(zip([d.name for d in cursor.description], values))
        self._values = values
        
    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._data[key]
        
    def get(self, key, default=None):
        return self._data.get(key, default)
        
    def __iter__(self):
        return iter(self._values)
        
    def __repr__(self):
        return repr(self._data)
        
    def __len__(self):
        return len(self._values)
        
    def keys(self):
        return self._data.keys()
        
    def values(self):
        return self._data.values()
        
    def items(self):
        return self._data.items()

def hybrid_row_factory(cursor):
    """
    Row factory that returns HybridRow objects.
    """
    def make_row(values):
        return HybridRow(cursor, values)
    return make_row

# Database connection configuration
DATABASE_URL = os.environ.get('DATABASE_URL', '')
MIN_CONNECTIONS = int(os.environ.get('DB_MIN_CONN', '1'))
MAX_CONNECTIONS = int(os.environ.get('DB_MAX_CONN', '10'))

def fix_railway_database_url(url: str) -> str:
    """
    Fix Railway internal hostname to use public URL
    Railway sometimes provides internal hostnames that don't work across services
    """
    if not url:
        return url
    
    # Replace .railway.internal with public hostname components
    if '.railway.internal' in url:
        # Try to use individual PostgreSQL variables if available
        pghost = os.environ.get('PGHOST', '')
        pgport = os.environ.get('PGPORT', '5432')
        pgdatabase = os.environ.get('PGDATABASE', 'railway')
        pguser = os.environ.get('PGUSER', 'postgres')
        pgpassword = os.environ.get('PGPASSWORD', '')
        
        if pghost and pgpassword and not '.railway.internal' in pghost:
            # Build URL from components
            rebuilt_url = f"postgresql://{pguser}:{pgpassword}@{pghost}:{pgport}/{pgdatabase}"
            logger.info(f"🔧 Rebuilt DATABASE_URL from PGHOST components")
            return rebuilt_url
        else:
            logger.warning(f"⚠️ DATABASE_URL contains .railway.internal but no valid PGHOST found")
    
    return url

class Database:
    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize PostgreSQL database connection
        
        Args:
            database_url: PostgreSQL connection string (postgresql://user:pass@host:port/dbname)
        """
        raw_url = database_url or DATABASE_URL
        self.database_url = fix_railway_database_url(raw_url)
        self.db_name = "PostgreSQL"  # For compatibility with SQLite code
        
        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable is required for PostgreSQL")
        
        # Log connection attempt (hide password)
        safe_url = self.database_url.split('@')[1] if '@' in self.database_url else self.database_url
        logger.info(f"🔌 Attempting to connect to: ...@{safe_url}")
        
        # Initialize connection pool
        try:
            self.pool = ConnectionPool(
                conninfo=self.database_url,
                min_size=MIN_CONNECTIONS,
                max_size=MAX_CONNECTIONS,
                kwargs={"row_factory": hybrid_row_factory}
            )
            logger.info(f"✅ PostgreSQL connection pool created (min={MIN_CONNECTIONS}, max={MAX_CONNECTIONS})")
        except Exception as e:
            logger.error(f"❌ Failed to create PostgreSQL connection pool: {e}")
            raise
        
        # Initialize database schema
        self.init_db()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections from pool"""
        with self.pool.connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Database error: {e}")
                raise
    
    def init_db(self):
        """Initialize PostgreSQL database schema"""
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
                cursor.execute('ALTER TABLE offers ADD COLUMN IF NOT EXISTS unit TEXT DEFAULT \'шт\'')
                cursor.execute('ALTER TABLE offers ADD COLUMN IF NOT EXISTS category TEXT DEFAULT \'other\'')
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
            
            # Favorites table (store favorites – align with SQLite schema)
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
            
            # FSM states table (for persistent FSM storage)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS fsm_states (
                    user_id BIGINT PRIMARY KEY,
                    state TEXT,
                    data JSONB,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create indexes for better performance
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
            
            # Check if favorites table needs migration from offer_id to store_id
            try:
                cursor.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='favorites' AND column_name='offer_id'
                """)
                has_offer_id = cursor.fetchone() is not None
                
                if has_offer_id:
                    logger.warning("⚠️ Migrating favorites table from offer_id to store_id...")
                    # Backup existing data if needed
                    cursor.execute("SELECT COUNT(*) FROM favorites")
                    count = cursor.fetchone()[0]
                    if count > 0:
                        logger.warning(f"⚠️ Found {count} existing favorites - they will be lost during migration")
                    
                    # Drop and recreate with correct schema
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
                else:
                    # Table already has store_id, just ensure index exists
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_favorites_store ON favorites(store_id)')
            except Exception as e:
                logger.error(f"Error checking/migrating favorites table: {e}")
                # If error, try to create index anyway (might already exist)
                try:
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_favorites_store ON favorites(store_id)')
                except:
                    pass
            
            # Migrate stores table to add delivery fields
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
                    # Enable delivery for all existing stores
                    cursor.execute("UPDATE stores SET delivery_enabled = 1 WHERE delivery_enabled IS NULL")
                    logger.info("✅ Delivery fields added to stores table")
            except Exception as e:
                logger.error(f"Error adding delivery fields to stores: {e}")
            
            conn.commit()
            logger.info("✅ PostgreSQL database schema initialized successfully")
    
    def close(self):
        """Close all connections in the pool"""
        if hasattr(self, 'pool') and self.pool:
            self.pool.close()
            logger.info("PostgreSQL connection pool closed")
    
    # User management methods
    def add_user(self, user_id: int, username: Optional[str] = None, first_name: Optional[str] = None,
                 phone: Optional[str] = None, city: str = 'Ташкент', language: str = 'ru') -> None:
        """Add or update user"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name, phone, city, language)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    phone = COALESCE(EXCLUDED.phone, users.phone),
                    city = COALESCE(EXCLUDED.city, users.city),
                    language = EXCLUDED.language
            ''', (user_id, username, first_name, phone, city, language))
            logger.info(f"User {user_id} added/updated")
    
    def get_user(self, user_id: int) -> Optional[dict[str, Any]]:
        """Get user by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
            result = cursor.fetchone()
            return dict(result) if result else None
    
    def update_user_phone(self, user_id: int, phone: str):
        """Update user phone"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET phone = %s WHERE user_id = %s', (phone, user_id))
    
    def update_user_city(self, user_id: int, city: str):
        """Update user city"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET city = %s WHERE user_id = %s', (city, user_id))
    
    def update_user_language(self, user_id: int, language: str):
        """Update user language"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET language = %s WHERE user_id = %s', (language, user_id))
    
    def get_user_language(self, user_id: int) -> str:
        """Get user language"""
        user = self.get_user(user_id)
        return user['language'] if user else 'ru'

    def get_user_model(self, user_id: int) -> Optional['User']:
        """Return user as Pydantic model (NEW - type-safe).
        
        Returns:
            User model or None if not found
        """
        try:
            from app.domain import User
        except ImportError:
            logger.error("Domain models not available. Install pydantic.")
            return None
        
        user_dict = self.get_user(user_id)
        if not user_dict:
            return None
        
        try:
            return User.from_db_row(user_dict)
        except Exception as e:
            logger.error(f"Failed to convert user {user_id} to model: {e}")
            return None

    def get_store_model(self, store_id: int) -> Optional['Store']:
        """Get store as Pydantic model (new API).
        
        Returns:
            Store model with type safety and validation, or None if not found.
        """
        try:
            from app.domain import Store
        except ImportError:
            logger.error("Domain models not available. Install pydantic.")
            return None
        
        store_dict = self.get_store(store_id)
        if not store_dict:
            return None
        
        try:
            return Store.from_db_row(store_dict)
        except Exception as e:
            logger.error(f"Failed to convert store {store_id} to model: {e}")
            return None

    def get_offer_model(self, offer_id: int) -> Optional['Offer']:
        """Get offer as Pydantic model (new API).
        
        Returns:
            Offer model with type safety and validation, or None if not found.
        """
        try:
            from app.domain import Offer
        except ImportError:
            logger.error("Domain models not available. Install pydantic.")
            return None
        
        offer_tuple = self.get_offer(offer_id)
        if not offer_tuple:
            return None
        
        try:
            return Offer.from_db_row(offer_tuple)
        except Exception as e:
            logger.error(f"Failed to convert offer {offer_id} to model: {e}")
            return None

    def get_booking_model(self, booking_id: int) -> Optional['Booking']:
        """Get booking as Pydantic model (new API).
        
        Returns:
            Booking model with type safety and validation, or None if not found.
        """
        try:
            from app.domain import Booking
        except ImportError:
            logger.error("Domain models not available. Install pydantic.")
            return None
        
        booking_tuple = self.get_booking(booking_id)
        if not booking_tuple:
            return None
        
        try:
            return Booking.from_db_row(booking_tuple)
        except Exception as e:
            logger.error(f"Failed to convert booking {booking_id} to model: {e}")
            return None

    # ===================== ADDITIONAL / PORTED METHODS (from SQLite) =====================
    def get_user_stores(self, owner_id: int):
        """Return all stores belonging to an owner"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('SELECT * FROM stores WHERE owner_id = %s ORDER BY created_at DESC', (owner_id,))
            return list(cursor.fetchall())

    def get_stores_by_city(self, city: str):
        """Return active stores for a given city (compact projection)"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute("""
                SELECT store_id, name, address, category, city
                FROM stores
                WHERE city = %s AND status = 'active'
                ORDER BY created_at DESC
            """, (city,))
            return list(cursor.fetchall())

    def get_active_offers(self, city: Optional[str] = None, store_id: Optional[int] = None) -> List[dict[str, Any]]:
        """Return active offers, optionally filtered by city or store.
        Matches the flexible signature used in handlers.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            base = ["SELECT o.*, s.city FROM offers o JOIN stores s ON o.store_id = s.store_id WHERE o.status = 'active'"]
            params = []
            if city:
                base.append('AND s.city = %s')
                params.append(city)
            if store_id:
                base.append('AND o.store_id = %s')
                params.append(store_id)
            base.append('ORDER BY o.created_at DESC')
            query = ' '.join(base)
            cursor.execute(query, tuple(params))
            return list(cursor.fetchall())

    def toggle_notifications(self, user_id: int) -> bool:
        """Toggle notifications_enabled flag; return new state"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users
                SET notifications_enabled = CASE WHEN notifications_enabled = 1 THEN 0 ELSE 1 END
                WHERE user_id = %s
                RETURNING notifications_enabled
            ''', (user_id,))
            new_val = cursor.fetchone()[0]
            return new_val == 1

    def update_user_role(self, user_id: int, role: str):
        """Update user role"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET role = %s WHERE user_id = %s', (role, user_id))

    def get_all_admins(self):
        """Return list of admin user_ids"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users WHERE is_admin = 1')
            return [row[0] for row in cursor.fetchall()]

    def add_to_favorites(self, user_id: int, store_id: int):
        """Add store to user's favorites"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO favorites (user_id, store_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, store_id) DO NOTHING
            ''', (user_id, store_id))

    def remove_from_favorites(self, user_id: int, store_id: int):
        """Remove store from user's favorites"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM favorites WHERE user_id = %s AND store_id = %s', (user_id, store_id))

    def get_favorites(self, user_id: int):
        """Return list of favorite stores for user"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('''
                SELECT f.store_id, s.name, s.city, s.category, s.address
                FROM favorites f
                JOIN stores s ON f.store_id = s.store_id
                WHERE f.user_id = %s AND s.status = 'active'
                ORDER BY f.created_at DESC
            ''', (user_id,))
            return list(cursor.fetchall())

    def activate_offer(self, offer_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE offers SET status = 'active' WHERE offer_id = %s", (offer_id,))

    def deactivate_offer(self, offer_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE offers SET status = 'inactive' WHERE offer_id = %s", (offer_id,))

    def get_booking_history(self, user_id: int, limit: int = 50):
        """Return recent bookings for user"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('''
                SELECT b.*, o.title, o.discount_price
                FROM bookings b
                JOIN offers o ON b.offer_id = o.offer_id
                WHERE b.user_id = %s
                ORDER BY b.created_at DESC
                LIMIT %s
            ''', (user_id, limit))
            return list(cursor.fetchall())

    def get_platform_payment_card(self):
        """Return generic platform payment card (first settings row)"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('SELECT card_number, card_holder FROM payment_settings ORDER BY created_at ASC LIMIT 1')
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def set_admin(self, user_id: int):
        """Set user as admin"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET is_admin = 1 WHERE user_id = %s', (user_id,))
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT is_admin FROM users WHERE user_id = %s', (user_id,))
            result = cursor.fetchone()
            return result and result[0] == 1
    
    # Store management methods
    def add_store(self, owner_id: int, name: str, city: str, address: Optional[str] = None,
                  description: Optional[str] = None, category: str = 'Ресторан', 
                  phone: Optional[str] = None, business_type: str = 'supermarket') -> int:
        """Add new store"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO stores (owner_id, name, city, address, description, category, phone, business_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING store_id
            ''', (owner_id, name, city, address, description, category, phone, business_type))
            store_id = cursor.fetchone()[0]
            logger.info(f"Store {store_id} added by user {owner_id}")
            return store_id
    
    def get_store_by_owner(self, owner_id: int):
        """Get store by owner ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('SELECT * FROM stores WHERE owner_id = %s', (owner_id,))
            return dict(cursor.fetchone()) if cursor.rowcount > 0 else None
    
    def get_store(self, store_id: int):
        """Get store by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('SELECT * FROM stores WHERE store_id = %s', (store_id,))
            return dict(cursor.fetchone()) if cursor.rowcount > 0 else None
    
    def update_store_status(self, store_id: int, status: str, rejection_reason: str = None):
        """Update store status"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE stores SET status = %s, rejection_reason = %s 
                WHERE store_id = %s
            ''', (status, rejection_reason, store_id))
    
    def get_approved_stores(self, city: str = None):
        """Get approved stores, optionally filtered by city"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            if city:
                cursor.execute('SELECT * FROM stores WHERE status = %s AND city = %s', 
                             ('approved', city))
            else:
                cursor.execute('SELECT * FROM stores WHERE status = %s', ('approved',))
            return [dict(row) for row in cursor.fetchall()]
    
    # Offer management methods
    def add_offer(self, store_id: int, title: str, description: str = None,
                  original_price: float = None, discount_price: float = None,
                  quantity: int = 1, available_from: str = None, available_until: str = None,
                  photo_id: str = None, expiry_date: str = None, unit: str = 'шт', category: str = 'other',
                  photo: str = None):
        """Add new offer - compatible with SQLite version parameter order"""
        
        # Support both photo and photo_id (protocol uses photo, legacy uses photo_id)
        actual_photo_id = photo if photo is not None else photo_id
        
        # Normalize expiry_date format to YYYY-MM-DD for PostgreSQL
        if expiry_date and '.' in expiry_date:
            try:
                from datetime import datetime
                # Convert DD.MM.YYYY to YYYY-MM-DD
                dt = datetime.strptime(expiry_date, '%d.%m.%Y')
                expiry_date = dt.strftime('%Y-%m-%d')
            except ValueError:
                pass  # Keep original format if parsing fails
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO offers (store_id, title, description, original_price, discount_price,
                                  quantity, available_from, available_until, expiry_date, photo_id, unit, category)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING offer_id
            ''', (store_id, title, description, original_price, discount_price,
                  quantity, available_from, available_until, expiry_date, actual_photo_id, unit, category))
            result = cursor.fetchone()
            if not result:
                raise ValueError("Failed to create offer")
            offer_id = result[0]
            logger.info(f"Offer {offer_id} added to store {store_id}")
            return offer_id
    
    def get_offer(self, offer_id: int):
        """Get offer by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('SELECT * FROM offers WHERE offer_id = %s', (offer_id,))
            return dict(cursor.fetchone()) if cursor.rowcount > 0 else None
    
    def get_store_offers(self, store_id: int, status: str = 'active'):
        """Get all offers for a store (excluding expired ones)"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('''
                SELECT * FROM offers 
                WHERE store_id = %s 
                AND status = %s
                AND (expiry_date IS NULL 
                     OR expiry_date !~ '[.]'
                     OR (expiry_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' AND expiry_date::date >= CURRENT_DATE))
                ORDER BY created_at DESC
            ''', (store_id, status))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_active_offers(self, city: str = None):
        """Получить все активные предложения, исключая истекшие"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            if city:
                cursor.execute('''
                    SELECT o.* FROM offers o
                    JOIN stores s ON o.store_id = s.store_id
                    WHERE o.status = %s AND s.status = %s AND s.city = %s
                    AND (o.expiry_date IS NULL 
                         OR expiry_date !~ '[.]'
                         OR (o.expiry_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' AND o.expiry_date::date >= CURRENT_DATE))
                    ORDER BY o.created_at DESC
                ''', ('active', 'approved', city))
            else:
                cursor.execute('''
                    SELECT o.* FROM offers o
                    JOIN stores s ON o.store_id = s.store_id
                    WHERE o.status = %s AND s.status = %s
                    ORDER BY o.created_at DESC
                ''', ('active', 'approved'))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_hot_offers(self, city: str = None, limit: int = 20, offset: int = 0, business_type: str = None):
        """Get hot offers (top by discount and expiry date)
        
        Args:
            city: City filter
            limit: Maximum number of offers
            offset: Offset for pagination
            business_type: Business type filter (supermarket, restaurant, bakery, cafe, pharmacy)
        
        Returns: List of dicts with offer data + store info
        Sorted by: discount_percent DESC, expiry_date ASC
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            
            query = '''
                SELECT o.*, s.name as store_name, s.address, s.city, s.category as store_category,
                       s.delivery_enabled, s.delivery_price, s.min_order_amount,
                       CAST((1.0 - o.discount_price::float / o.original_price::float) * 100 AS INTEGER) as discount_percent
                FROM offers o
                JOIN stores s ON o.store_id = s.store_id
                WHERE o.status = 'active' 
                AND o.quantity > 0
                AND (s.status = 'approved' OR s.status = 'active')
                AND (o.available_until IS NULL OR LENGTH(o.available_until) < 6 OR 
                     (LENGTH(o.available_until) > 10 AND o.available_until::timestamp >= NOW()))
                AND (o.expiry_date IS NULL 
                     OR o.expiry_date !~ '[.]'
                     OR (o.expiry_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' AND o.expiry_date::date >= CURRENT_DATE))
            '''
            
            params = []
            if city:
                query += ' AND s.city ILIKE %s'
                params.append(f'%{city}%')
            
            if business_type:
                query += ' AND s.category = %s'
                params.append(business_type)
            
            query += '''
                ORDER BY discount_percent DESC, 
                         COALESCE(o.expiry_date, '9999-12-31') ASC,
                         o.created_at DESC
                LIMIT %s OFFSET %s
            '''
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def count_hot_offers(self, city: str = None, business_type: str = None) -> int:
        """Подсчёт горячих предложений без загрузки данных (быстрая операция)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = '''
                SELECT COUNT(*)
                FROM offers o
                JOIN stores s ON o.store_id = s.store_id
                WHERE o.status = 'active'
                  AND o.quantity > 0
                  AND s.status = 'active'
                  AND (o.available_until IS NULL OR LENGTH(o.available_until) < 6 OR 
                       (LENGTH(o.available_until) > 10 AND o.available_until::timestamp >= NOW()))
            '''
            params = []
            
            if city:
                query += ' AND s.city = %s'
                params.append(city)
            
            if business_type:
                query += ' AND s.business_type = %s'
                params.append(business_type)
            
            cursor.execute(query, params)
            return cursor.fetchone()[0]
    
    def update_offer_quantity(self, offer_id: int, quantity: int):
        """Update offer quantity"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE offers SET quantity = %s WHERE offer_id = %s', 
                         (quantity, offer_id))
    
    def get_user_stores(self, owner_id: int):
        """Get ALL stores for user (any status)"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('''
                SELECT s.*, u.first_name, u.username 
                FROM stores s
                LEFT JOIN users u ON s.owner_id = u.user_id
                WHERE s.owner_id = %s
                ORDER BY s.created_at DESC
            ''', (owner_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_offers_by_store(self, store_id: int):
        """Get active offers for store"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('''
                SELECT o.*, s.name, s.address, s.city, s.category
                FROM offers o
                JOIN stores s ON o.store_id = s.store_id
                WHERE o.store_id = %s AND o.quantity > 0 
                AND (o.expiry_date IS NULL 
                     OR o.expiry_date !~ '[.]'
                     OR (o.expiry_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' AND o.expiry_date::date >= CURRENT_DATE))
                ORDER BY o.created_at DESC
            ''', (store_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_top_offers_by_city(self, city: str, limit: int = 10):
        """Get top offers in city (by discount)"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('''
                SELECT o.*, s.name, s.address, s.city, s.category,
                       CAST((o.original_price - o.discount_price)::float / o.original_price * 100 AS INTEGER) as discount_percent
                FROM offers o
                JOIN stores s ON o.store_id = s.store_id
                WHERE s.city = %s AND s.status = 'active' 
                      AND o.status = 'active' AND o.quantity > 0 
                      AND (o.expiry_date IS NULL 
                           OR o.expiry_date !~ '[.]'
                           OR (o.expiry_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' AND o.expiry_date::date >= CURRENT_DATE))
                ORDER BY discount_percent DESC, o.created_at DESC
                LIMIT %s
            ''', (city, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def create_booking_atomic(self, offer_id: int, user_id: int, quantity: int = 1):
        """Atomically reserve product and create booking in one transaction
        
        Returns: Tuple[bool, Optional[int], Optional[str]]
            - ok: True if booking created successfully
            - booking_id: ID of created booking or None on error
            - booking_code: Booking code or None on error
        """
        import random
        import string
        
        logger.info(f"🔵 create_booking_atomic START: offer_id={offer_id}, user_id={user_id}, quantity={quantity}")
        
        conn = None
        try:
            conn = self.pool.getconn()
            conn.autocommit = False  # Start transaction
            cursor = conn.cursor()
            
            logger.info(f"🔵 Checking offer status...")
            
            # Check and reserve product atomically
            cursor.execute('''
                SELECT quantity, status FROM offers 
                WHERE offer_id = %s AND status = 'active'
                FOR UPDATE
            ''', (offer_id,))
            offer = cursor.fetchone()
            
            logger.info(f"🔵 Offer check result: {offer}")
            
            if not offer or offer[0] is None or offer[0] < quantity or offer[1] != 'active':
                conn.rollback()
                logger.warning(f"🔵 Offer check FAILED: not available")
                return (False, None, None)
            
            current_quantity = offer[0]
            new_quantity = current_quantity - quantity
            
            logger.info(f"🔵 Updating quantity: {current_quantity} -> {new_quantity}")
            
            # Update quantity atomically
            cursor.execute('''
                UPDATE offers 
                SET quantity = %s, 
                    status = CASE WHEN %s <= 0 THEN 'inactive' ELSE 'active' END
                WHERE offer_id = %s AND quantity = %s
            ''', (new_quantity, new_quantity, offer_id, current_quantity))
            
            if cursor.rowcount == 0:
                conn.rollback()
                logger.warning(f"🔵 Quantity update FAILED: rowcount=0")
                return (False, None, None)
            
            logger.info(f"🔵 Quantity updated successfully")
            
            # Generate unique booking code
            booking_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            
            logger.info(f"🔵 Creating booking with code={booking_code}")
            
            # Create booking
            cursor.execute('''
                INSERT INTO bookings (offer_id, user_id, booking_code, status, quantity)
                VALUES (%s, %s, %s, 'pending', %s)
                RETURNING booking_id
            ''', (offer_id, user_id, booking_code, quantity))
            booking_id = cursor.fetchone()[0]
            
            logger.info(f"🔵 Booking created: booking_id={booking_id}")
            
            conn.commit()
            logger.info(f"✅ create_booking_atomic SUCCESS: booking_id={booking_id}, code={booking_code}")
            return (True, booking_id, booking_code)
            
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            logger.error(f"❌ Error creating booking atomically: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return (False, None, None)
        finally:
            if conn:
                conn.autocommit = True
                self.pool.putconn(conn)
    
    def get_booking(self, booking_id: int):
        """Get booking by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('''
                SELECT booking_id, offer_id, user_id, status, booking_code, 
                       pickup_time, COALESCE(quantity, 1) as quantity, created_at 
                FROM bookings 
                WHERE booking_id = %s
            ''', (booking_id,))
            result = cursor.fetchone()
            return dict(result) if result else None
    
    def get_booking_by_code(self, booking_code: str):
        """Get booking by code"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('''
                SELECT b.booking_id, b.offer_id, b.user_id, b.status, b.booking_code,
                       b.pickup_time, COALESCE(b.quantity, 1) as quantity, b.created_at,
                       u.first_name, u.username
                FROM bookings b
                JOIN users u ON b.user_id = u.user_id
                WHERE b.booking_code = %s AND b.status = 'pending'
            ''', (booking_code,))
            result = cursor.fetchone()
            return dict(result) if result else None
    
    def get_store_bookings(self, store_id: int):
        """Get all bookings for store"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('''
                SELECT b.*, o.title, u.first_name, u.username, u.phone
                FROM bookings b
                JOIN offers o ON b.offer_id = o.offer_id
                JOIN users u ON b.user_id = u.user_id
                WHERE o.store_id = %s
                ORDER BY b.created_at DESC
            ''', (store_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def update_booking_status(self, booking_id: int, status: str):
        """Update booking status"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE bookings SET status = %s WHERE booking_id = %s', 
                         (status, booking_id))
    
    def complete_booking(self, booking_id: int):
        """Complete booking"""
        self.update_booking_status(booking_id, 'completed')
    
    def cancel_booking(self, booking_id: int):
        """Cancel booking"""
        self.update_booking_status(booking_id, 'cancelled')
    
    def approve_store(self, store_id: int):
        """Approve store and promote owner to seller"""
        conn = None
        try:
            conn = self.pool.getconn()
            conn.autocommit = False
            cursor = conn.cursor()
            
            # Get store data
            cursor.execute('''
                SELECT s.owner_id, u.user_id, s.status, s.name 
                FROM stores s
                LEFT JOIN users u ON s.owner_id = u.user_id
                WHERE s.store_id = %s
            ''', (store_id,))
            
            result = cursor.fetchone()
            if not result:
                conn.rollback()
                logger.error(f"Store {store_id} not found")
                return False
                
            owner_id, user_exists, current_status, store_name = result
            
            if not user_exists:
                conn.rollback()
                logger.error(f"Owner {owner_id} for store {store_id} ({store_name}) not found")
                return False
            
            if current_status != 'pending':
                conn.rollback()
                logger.warning(f"Store {store_id} already has status: {current_status}")
                return False
            
            # Update store status
            cursor.execute('UPDATE stores SET status = %s WHERE store_id = %s', ('active', store_id))
            
            # Update owner role
            cursor.execute('UPDATE users SET role = %s WHERE user_id = %s', ('seller', owner_id))
            
            conn.commit()
            logger.info(f"Store {store_id} ({store_name}) approved, owner {owner_id} promoted to seller")
            return True
            
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error approving store: {e}")
            return False
        finally:
            if conn:
                conn.autocommit = True
                self.pool.putconn(conn)
    
    def reject_store(self, store_id: int, reason: str):
        """Reject store with reason"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE stores SET status = %s, rejection_reason = %s WHERE store_id = %s', 
                         ('rejected', reason, store_id))
    
    def get_pending_stores(self):
        """Get all pending stores"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('''
                SELECT s.*, u.first_name, u.username
                FROM stores s
                JOIN users u ON s.owner_id = u.user_id
                WHERE s.status = 'pending'
                ORDER BY s.created_at DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]
    
    def delete_offer(self, offer_id: int):
        """Soft delete offer (set status to inactive)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE offers SET status = %s WHERE offer_id = %s', 
                         ('inactive', offer_id))
    
    def get_store_owner(self, store_id: int):
        """Get store owner ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT owner_id FROM stores WHERE store_id = %s', (store_id,))
            result = cursor.fetchone()
            return result[0] if result else None
    
    def get_stores_by_city(self, city: str):
        """Get all active stores in city"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('SELECT * FROM stores WHERE city = %s AND status = %s', (city, 'active'))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_stores_by_business_type(self, business_type: str, city: str = None):
        """Get stores by business type (using business_type field) with active offers count"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            
            # Log for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"🏪 SQL query: business_type={business_type}, city={city}")
            
            query = '''
                SELECT s.*, 
                       COUNT(o.offer_id) as offers_count
                FROM stores s
                INNER JOIN offers o ON s.store_id = o.store_id 
                    AND o.status = 'active' 
                    AND o.quantity > 0
                WHERE (s.status = 'active' OR s.status = 'approved')
                AND LOWER(s.business_type) = LOWER(%s)
            '''
            params = [business_type]
            
            if city:
                # Use exact match first, then try partial match
                query += ' AND (LOWER(s.city) = LOWER(%s) OR s.city ILIKE %s OR s.city IS NULL)'
                params.append(city)
                params.append(f'%{city}%')
            
            query += '''
                GROUP BY s.store_id
                HAVING COUNT(o.offer_id) > 0
                ORDER BY COUNT(o.offer_id) DESC, s.name
            '''
            
            cursor.execute(query, params)
            results = [dict(row) for row in cursor.fetchall()]
            
            logger.info(f"🏪 SQL returned {len(results)} stores")
            if results:
                logger.info(f"🏪 First store: {results[0].get('name', 'Unknown')} in {results[0].get('city', 'Unknown')}")
            
            return results
    
    def get_all_users(self):
        """Get all users with notifications enabled"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('SELECT * FROM users WHERE notifications_enabled = 1')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_all_admins(self):
        """Get all admins"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users WHERE is_admin = 1')
            return [row[0] for row in cursor.fetchall()]

    def toggle_notifications(self, user_id: int):
        """Toggle notifications for user"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT notifications_enabled FROM users WHERE user_id = %s', (user_id,))
            result = cursor.fetchone()
            if result:
                new_value = not result[0]
                cursor.execute('UPDATE users SET notifications_enabled = %s WHERE user_id = %s', 
                             (new_value, user_id))
                return new_value
            return None
    
    def update_user_role(self, user_id: int, role: str):
        """Update user role"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET role = %s WHERE user_id = %s', (role, user_id))
    
    def delete_user(self, user_id: int):
        """Delete user and all related data (cascading delete)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Delete in order to respect foreign key constraints
            # 1. Delete ratings (references bookings, stores, orders, users)
            cursor.execute('DELETE FROM ratings WHERE user_id = %s', (user_id,))
            
            # 2. Delete favorites (references users, stores)
            cursor.execute('DELETE FROM favorites WHERE user_id = %s', (user_id,))
            
            # 3. Delete notifications (references users)
            cursor.execute('DELETE FROM notifications WHERE user_id = %s', (user_id,))
            
            # 4. Delete bookings (references users, offers, stores)
            cursor.execute('DELETE FROM bookings WHERE user_id = %s', (user_id,))
            
            # 5. Delete orders related to user's stores (if seller)
            cursor.execute('''
                DELETE FROM orders 
                WHERE store_id IN (SELECT store_id FROM stores WHERE owner_id = %s)
            ''', (user_id,))
            
            # 6. Delete payment settings for user's stores
            cursor.execute('''
                DELETE FROM payment_settings 
                WHERE store_id IN (SELECT store_id FROM stores WHERE owner_id = %s)
            ''', (user_id,))
            
            # 7. Delete offers for user's stores
            cursor.execute('''
                DELETE FROM offers 
                WHERE store_id IN (SELECT store_id FROM stores WHERE owner_id = %s)
            ''', (user_id,))
            
            # 8. Delete user's stores
            cursor.execute('DELETE FROM stores WHERE owner_id = %s', (user_id,))
            
            # 9. Finally delete the user
            cursor.execute('DELETE FROM users WHERE user_id = %s', (user_id,))
            
            logger.info(f"Successfully deleted user {user_id} and all related data")
    
    def delete_store(self, store_id: int):
        """Delete store"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM stores WHERE store_id = %s', (store_id,))
    
    def activate_offer(self, offer_id: int):
        """Activate offer"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE offers SET status = %s WHERE offer_id = %s', ('active', offer_id))
    
    def deactivate_offer(self, offer_id: int):
        """Deactivate offer"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE offers SET status = %s WHERE offer_id = %s', ('inactive', offer_id))
    
    def get_booking_history(self, user_id: int):
        """Get user booking history"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('''
                SELECT b.*, o.title, s.name as store_name
                FROM bookings b
                JOIN offers o ON b.offer_id = o.offer_id
                JOIN stores s ON o.store_id = s.store_id
                WHERE b.user_id = %s
                ORDER BY b.created_at DESC
            ''', (user_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def add_to_favorites(self, user_id: int, offer_id: int):
        """Add offer to favorites"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO favorites (user_id, offer_id) 
                VALUES (%s, %s) 
                ON CONFLICT DO NOTHING
            ''', (user_id, offer_id))
    
    def remove_from_favorites(self, user_id: int, offer_id: int):
        """Remove offer from favorites"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM favorites WHERE user_id = %s AND offer_id = %s', 
                         (user_id, offer_id))
    
    def get_statistics(self):
        """Get platform statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            cursor.execute('SELECT COUNT(*) FROM users')
            stats['users'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM users WHERE role = %s', ('customer',))
            stats['customers'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM users WHERE role = %s', ('seller',))
            stats['sellers'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM stores')
            stats['stores'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM stores WHERE status = %s', ('active',))
            stats['approved_stores'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM stores WHERE status = %s', ('pending',))
            stats['pending_stores'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM offers')
            stats['offers'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM offers WHERE status = %s', ('active',))
            stats['active_offers'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM bookings')
            stats['bookings'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = %s', ('completed',))
            stats['completed_bookings'] = cursor.fetchone()[0]
            
            return stats
    
    # ============== OFFER QUANTITY & EXPIRY METHODS ==============
    
    def increment_offer_quantity(self, offer_id: int, amount: int = 1):
        """Увеличить количество товара (при отмене бронирования)"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            # Получаем текущее количество
            cursor.execute('SELECT quantity FROM offers WHERE offer_id = %s', (offer_id,))
            row = cursor.fetchone()
            if row:
                current_qty = row['quantity'] if row['quantity'] is not None else 0
                new_qty = current_qty + amount
                self.update_offer_quantity(offer_id, new_qty)
    
    def update_offer_expiry(self, offer_id: int, new_expiry: str):
        """Обновить срок годности товара"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE offers SET expiry_date = %s WHERE offer_id = %s', (new_expiry, offer_id))
    
    def delete_expired_offers(self):
        """Удаляет предложения с истёкшим сроком годности"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Деактивируем товары с истёкшим сроком годности
            cursor.execute('''
                UPDATE offers 
                SET status = 'inactive' 
                WHERE status = 'active' 
                AND expiry_date IS NOT NULL
                AND expiry_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                AND expiry_date::date < CURRENT_DATE
            ''')
            return cursor.rowcount  # Return number of updated rows
    
    # ============== RATING METHODS ==============
    
    def add_rating(self, booking_id: int, user_id: int, store_id: int, rating: int, comment: str = None):
        """Добавить рейтинг"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO ratings (booking_id, user_id, store_id, rating, comment)
                VALUES (%s, %s, %s, %s, %s)
            ''', (booking_id, user_id, store_id, rating, comment))
    
    def save_booking_rating(self, booking_id: int, rating: int) -> bool:
        """Сохранить оценку заказа (используется в bookings.py)"""
        try:
            # Получить информацию о бронировании
            booking = self.get_booking(booking_id)
            if not booking:
                logger.error(f"Booking {booking_id} not found")
                return False
            
            # Извлечь user_id и offer_id
            if isinstance(booking, dict):
                user_id = booking.get('user_id')
                offer_id = booking.get('offer_id')
            else:
                user_id = booking[1]
                offer_id = booking[2]
            
            # Получить store_id из offer
            offer = self.get_offer(offer_id)
            if not offer:
                logger.error(f"Offer {offer_id} not found")
                return False
            
            if isinstance(offer, dict):
                store_id = offer.get('store_id')
            else:
                store_id = offer[1]
            
            # Сохранить рейтинг
            self.add_rating(booking_id, user_id, store_id, rating)
            return True
        except Exception as e:
            logger.error(f"Error saving booking rating: {e}")
            return False
    
    def get_store_ratings(self, store_id: int) -> List[dict]:
        """Получить все рейтинги магазина"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('''
                SELECT r.*, u.first_name, u.username
                FROM ratings r
                JOIN users u ON r.user_id = u.user_id
                WHERE r.store_id = %s
                ORDER BY r.created_at DESC
            ''', (store_id,))
            return cursor.fetchall()
    
    def get_store_average_rating(self, store_id: int) -> float:
        """Получить средний рейтинг магазина"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT AVG(rating) FROM ratings WHERE store_id = %s', (store_id,))
            result = cursor.fetchone()
            return round(result[0], 1) if result and result[0] else 0.0
    
    def has_rated_booking(self, booking_id: int) -> bool:
        """Проверить, оценил ли пользователь бронирование"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM ratings WHERE booking_id = %s', (booking_id,))
            count = cursor.fetchone()[0]
            return count > 0
    
    # ============== STORE SALES STATISTICS ==============
    
    def get_store_sales_stats(self, store_id: int) -> dict:
        """Получить статистику продаж магазина"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            # Всего продано
            cursor.execute('''
                SELECT COUNT(*), SUM(o.discount_price)
                FROM bookings b
                JOIN offers o ON b.offer_id = o.offer_id
                WHERE o.store_id = %s AND b.status = 'completed'
            ''', (store_id,))
            result = cursor.fetchone()
            stats['total_sales'] = result[0] if result[0] else 0
            stats['total_revenue'] = result[1] if result[1] else 0
            
            # Активные брони
            cursor.execute('''
                SELECT COUNT(*)
                FROM bookings b
                JOIN offers o ON b.offer_id = o.offer_id
                WHERE o.store_id = %s AND b.status = 'pending'
            ''', (store_id,))
            stats['pending_bookings'] = cursor.fetchone()[0]
            
            return stats
    
    # ============== STORE FILTERING METHODS ==============
    
    def get_stores_by_category(self, category: str, city: str = None) -> List[dict]:
        """Получить магазины по категории и опционально по городу"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            if city:
                cursor.execute('''
                    SELECT * 
                    FROM stores 
                    WHERE category = %s AND city = %s AND status = 'active'
                    ORDER BY name
                ''', (category, city))
            else:
                cursor.execute('''
                    SELECT * 
                    FROM stores 
                    WHERE category = %s AND status = 'active'
                    ORDER BY name
                ''', (category,))
            return cursor.fetchall()
    
    def get_offers_by_city_and_category(self, city: str, category: str, limit: int = 20) -> List[dict]:
        """Получить предложения в городе по категории товара (offers.category)"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('''
                SELECT o.*, s.name as store_name, s.address, s.city, s.category as store_category,
                       CAST((o.original_price - o.discount_price) AS NUMERIC) / o.original_price * 100 as discount_percent
                FROM offers o
                JOIN stores s ON o.store_id = s.store_id
                WHERE s.city = %s AND o.category = %s AND s.status = 'active'
                      AND o.status = 'active' AND o.quantity > 0 
                      AND (o.expiry_date IS NULL 
                           OR o.expiry_date !~ '[.]'
                           OR (o.expiry_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' AND o.expiry_date::date >= CURRENT_DATE))
                ORDER BY discount_percent DESC, o.created_at DESC
                LIMIT %s
            ''', (city, category, limit))
            return cursor.fetchall()
    
    def get_stores_count_by_category(self, city: str) -> dict:
        """Получить количество магазинов по каждой категории в городе"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT category, COUNT(*) as count
                FROM stores
                WHERE city = %s AND status = 'active'
                GROUP BY category
            ''', (city,))
            results = cursor.fetchall()
            # Возвращаем словарь {категория: количество}
            return {row[0]: row[1] for row in results}
    
    def get_top_stores_by_city(self, city: str, limit: int = 10) -> List[dict]:
        """Получить топ магазины по рейтингу в городе"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('''
                SELECT s.*, 
                       COALESCE(AVG(r.rating), 0) as avg_rating,
                       COUNT(r.rating_id) as ratings_count
                FROM stores s
                LEFT JOIN ratings r ON s.store_id = r.store_id
                WHERE s.city = %s AND s.status = 'active'
                GROUP BY s.store_id
                ORDER BY avg_rating DESC, ratings_count DESC
                LIMIT %s
            ''', (city, limit))
            return cursor.fetchall()
    
    # ============== FAVORITES & ANALYTICS ==============
    
    def get_favorites(self, user_id: int) -> List[dict]:
        """Получить избранные магазины пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('''
                SELECT s.* FROM stores s
                JOIN favorites f ON s.store_id = f.store_id
                WHERE f.user_id = %s AND s.status = 'active'
                ORDER BY f.created_at DESC
            ''', (user_id,))
            return cursor.fetchall()
    
    def get_store_analytics(self, store_id: int) -> dict:
        """Получить аналитику магазина"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Общая статистика
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_bookings,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled
                FROM bookings b
                JOIN offers o ON b.offer_id = o.offer_id
                WHERE o.store_id = %s
            ''', (store_id,))
            stats = cursor.fetchone()
            
            # Продажи по дням недели
            cursor.execute('''
                SELECT 
                    EXTRACT(DOW FROM b.created_at)::INTEGER as day_of_week,
                    COUNT(*) as count
                FROM bookings b
                JOIN offers o ON b.offer_id = o.offer_id
                WHERE o.store_id = %s AND b.status = 'completed'
                GROUP BY day_of_week
            ''', (store_id,))
            days = cursor.fetchall()
            
            # Популярные категории
            cursor.execute('''
                SELECT 
                    o.category,
                    COUNT(*) as count
                FROM bookings b
                JOIN offers o ON b.offer_id = o.offer_id
                WHERE o.store_id = %s AND b.status = 'completed'
                GROUP BY o.category
                ORDER BY count DESC
                LIMIT 5
            ''', (store_id,))
            categories = cursor.fetchall()
            
            # Средний рейтинг
            cursor.execute('''
                SELECT AVG(rating) as avg_rating, COUNT(*) as rating_count
                FROM ratings
                WHERE store_id = %s
            ''', (store_id,))
            rating = cursor.fetchone()
            
            return {
                'total_bookings': stats[0] or 0,
                'completed': stats[1] or 0,
                'cancelled': stats[2] or 0,
                'conversion_rate': (stats[1] / stats[0] * 100) if stats[0] > 0 else 0,
                'days_of_week': dict(days) if days else {},
                'popular_categories': categories or [],
                'avg_rating': rating[0] or 0,
                'rating_count': rating[1] or 0
            }
    
    # ============== UTILITY METHODS ==============
    
    @staticmethod
    def get_time_remaining(expiry_date: str) -> str:
        """
        Возвращает строку с оставшимся временем до истечения срока годности
        Формат: '🕐 Годен: 2 дня' или '⏰ Срок годности истек'
        """
        if not expiry_date:
            return ""
        
        from datetime import datetime
        
        try:
            # Парсим дату истечения срока годности
            if isinstance(expiry_date, str):
                if ' ' in expiry_date:
                    # Если есть время, пробуем разные форматы
                    try:
                        end_date = datetime.strptime(expiry_date, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        try:
                            end_date = datetime.strptime(expiry_date, '%Y-%m-%d %H:%M')
                        except ValueError:
                            return ""
                elif '-' in expiry_date:
                    # Если только дата в формате YYYY-MM-DD
                    end_date = datetime.strptime(expiry_date, '%Y-%m-%d')
                elif '.' in expiry_date:
                    # Если дата в формате DD.MM.YYYY
                    end_date = datetime.strptime(expiry_date, '%d.%m.%Y')
                else:
                    return ""
            else:
                return ""
            
            # Считаем разницу
            now = datetime.now()
            delta = end_date - now
            
            if delta.days < 0:
                return "⏰ Срок годности истек"
            elif delta.days == 0:
                hours = delta.seconds // 3600
                if hours > 0:
                    return f"🕐 Годен: {hours} ч"
                else:
                    return "⏰ Срок истекает сегодня"
            elif delta.days == 1:
                return "🕐 Годен: 1 день"
            else:
                return f"🕐 Годен: {delta.days} дня" if delta.days < 5 else f"🕐 Годен: {delta.days} дней"
        except Exception:
            return ""
    
    # Order management methods
    def create_order(self, user_id: int, store_id: int, offer_id: int, quantity: int,
                     order_type: str, delivery_address: str = None, delivery_price: int = 0,
                     payment_method: str = None):
        """Create new order"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get offer price
            offer = self.get_offer(offer_id)
            if not offer:
                return None
            
            discount_price = offer['discount_price']
            total_amount = (discount_price * quantity) + delivery_price
            
            # Generate pickup code for pickup orders
            import random
            import string
            pickup_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6)) if order_type == 'pickup' else None
            
            cursor.execute('''
                INSERT INTO orders (user_id, store_id, offer_id, quantity, delivery_address,
                                  total_price, payment_method, payment_status, order_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING order_id
            ''', (user_id, store_id, offer_id, quantity, delivery_address,
                  total_amount, payment_method or 'card', 'pending', 'pending'))
            order_id = cursor.fetchone()[0]
            logger.info(f"Order {order_id} created by user {user_id}")
            return order_id
    
    def get_order(self, order_id: int):
        """Get order by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('SELECT * FROM orders WHERE order_id = %s', (order_id,))
            return dict(cursor.fetchone()) if cursor.rowcount > 0 else None
    
    def update_order_payment_proof(self, order_id: int, photo_id: str):
        """Update order with payment proof photo"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE orders SET payment_proof_photo_id = %s, payment_status = %s 
                WHERE order_id = %s
            ''', (photo_id, 'proof_submitted', order_id))
    
    def update_payment_status(self, order_id: int, status: str, photo_id: str = None):
        """Update payment status and optionally save proof photo"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if photo_id:
                cursor.execute('''
                    UPDATE orders SET payment_status = %s, payment_proof_photo_id = %s
                    WHERE order_id = %s
                ''', (status, photo_id, order_id))
            else:
                cursor.execute('''
                    UPDATE orders SET payment_status = %s
                    WHERE order_id = %s
                ''', (status, order_id))
    
    def update_order_status(self, order_id: int, order_status: str, payment_status: str = None):
        """Update order status"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if payment_status:
                cursor.execute('''
                    UPDATE orders SET order_status = %s, payment_status = %s 
                    WHERE order_id = %s
                ''', (order_status, payment_status, order_id))
            else:
                cursor.execute('UPDATE orders SET order_status = %s WHERE order_id = %s', 
                             (order_status, order_id))
    
    def get_user_orders(self, user_id: int):
        """Get all orders for a user"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('SELECT * FROM orders WHERE user_id = %s ORDER BY created_at DESC', 
                         (user_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_store_orders(self, store_id: int, status: str = None):
        """Get all orders for a store, optionally filtered by status"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            if status:
                cursor.execute('SELECT * FROM orders WHERE store_id = %s AND order_status = %s ORDER BY created_at DESC', 
                             (store_id, status))
            else:
                cursor.execute('SELECT * FROM orders WHERE store_id = %s ORDER BY created_at DESC', 
                             (store_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    # Payment settings methods
    def set_payment_card(self, store_id: int, card_number: str, card_holder: str = None,
                         card_expiry: str = None, payment_instructions: str = None):
        """Set payment card for store"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO payment_settings (store_id, card_number, card_holder, 
                                              card_expiry, payment_instructions)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (store_id) DO UPDATE SET
                    card_number = EXCLUDED.card_number,
                    card_holder = EXCLUDED.card_holder,
                    card_expiry = EXCLUDED.card_expiry,
                    payment_instructions = EXCLUDED.payment_instructions
            ''', (store_id, card_number, card_holder, card_expiry, payment_instructions))
    
    def get_payment_card(self, store_id: int):
        """Get payment card for store"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('SELECT * FROM payment_settings WHERE store_id = %s', (store_id,))
            return dict(cursor.fetchone()) if cursor.rowcount > 0 else None
    
    # Booking methods
    def add_booking(self, user_id: int, offer_id: int, store_id: int, quantity: int = 1):
        """Add new booking"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO bookings (user_id, offer_id, store_id, quantity)
                VALUES (%s, %s, %s, %s)
                RETURNING booking_id
            ''', (user_id, offer_id, store_id, quantity))
            return cursor.fetchone()[0]
    
    def get_user_bookings(self, user_id: int):
        """Get all user bookings (not just active)"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('SELECT * FROM bookings WHERE user_id = %s ORDER BY created_at DESC', 
                         (user_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def cancel_booking(self, booking_id: int):
        """Cancel booking"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE bookings SET status = %s WHERE booking_id = %s', 
                         ('cancelled', booking_id))
    
    # Notification methods
    def add_notification(self, user_id: int, type: str, title: str, message: str):
        """Add notification"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO notifications (user_id, type, title, message)
                VALUES (%s, %s, %s, %s)
            ''', (user_id, type, title, message))
    
    def get_user_notifications(self, user_id: int, unread_only: bool = False):
        """Get user notifications"""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            if unread_only:
                cursor.execute('''
                    SELECT * FROM notifications 
                    WHERE user_id = %s AND is_read = 0 
                    ORDER BY created_at DESC
                ''', (user_id,))
            else:
                cursor.execute('''
                    SELECT * FROM notifications 
                    WHERE user_id = %s 
                    ORDER BY created_at DESC
                ''', (user_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def mark_notification_read(self, notification_id: int):
        """Mark notification as read"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE notifications SET is_read = 1 WHERE notification_id = %s', 
                         (notification_id,))
    
    # Favorites methods
    # Deprecated offer-based favorites removed; using store-based favorites API (add_to_favorites/remove_from_favorites/get_favorites)
    def is_favorite(self, user_id: int, store_id: int) -> bool:
        """Check if store is in user's favorites (store-based)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM favorites WHERE user_id = %s AND store_id = %s', (user_id, store_id))
            return cursor.fetchone() is not None
    
    # Statistics methods
    def get_total_users(self) -> int:
        """Get total users count"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users')
            return cursor.fetchone()[0]
    
    def get_total_stores(self) -> int:
        """Get total stores count"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM stores WHERE status = %s', ('approved',))
            return cursor.fetchone()[0]
    
    def get_total_offers(self) -> int:
        """Get total active offers count"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM offers WHERE status = %s', ('active',))
            return cursor.fetchone()[0]
    
    def get_total_orders(self) -> int:
        """Get total orders count"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM orders')
            return cursor.fetchone()[0]

    def search_offers(self, query: str, city: str) -> List[Any]:
        """Search offers by title or store name using advanced PostgreSQL full-text search."""
        sql = """
            SELECT 
                o.offer_id, o.store_id, o.title, o.description, 
                o.original_price, o.discount_price, o.quantity, 
                o.available_from, o.available_until, o.expiry_date, 
                o.status, o.photo_id as photo, o.created_at, o.unit,
                s.name as store_name, s.address, s.category as store_category,
                CAST((1.0 - o.discount_price::float / o.original_price::float) * 100 AS INTEGER) as discount_percent,
                s.delivery_enabled, s.delivery_price, s.min_order_amount,
                -- Ranking for relevance
                (
                    -- Exact match bonus
                    CASE WHEN LOWER(o.title) = LOWER(%s) THEN 100 ELSE 0 END +
                    -- Starts with bonus
                    CASE WHEN LOWER(o.title) LIKE LOWER(%s) || '%%' THEN 50 ELSE 0 END +
                    -- Contains match
                    CASE WHEN LOWER(o.title) LIKE '%%' || LOWER(%s) || '%%' THEN 10 ELSE 0 END +
                    -- Transliteration matches (banan → банан)
                    CASE WHEN 
                        -- Russian to Latin
                        TRANSLATE(LOWER(o.title), 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя', 'abvgdeejziiklmnoprstufxcchshshhyyyeua') LIKE '%%' || LOWER(%s) || '%%'
                        -- Latin to Russian approximation
                        OR LOWER(o.title) LIKE '%%' || REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(%s), 'a', 'а'), 'e', 'е'), 'o', 'о'), 'p', 'р'), 'c', 'с') || '%%'
                    THEN 5 ELSE 0 END
                ) as relevance
            FROM offers o
            JOIN stores s ON o.store_id = s.store_id
            WHERE o.status = 'active' 
            AND o.quantity > 0
            AND (s.status = 'approved' OR s.status = 'active')
            AND s.city ILIKE %s
            AND (o.expiry_date IS NULL 
                 OR o.expiry_date !~ '[.]'
                 OR (o.expiry_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' AND o.expiry_date::date >= CURRENT_DATE))
            AND (
                LOWER(o.title) LIKE '%%' || LOWER(%s) || '%%' OR 
                LOWER(s.name) LIKE '%%' || LOWER(%s) || '%%' OR
                LOWER(s.category) LIKE '%%' || LOWER(%s) || '%%' OR
                -- Transliteration search
                TRANSLATE(LOWER(o.title), 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя', 'abvgdeejziiklmnoprstufxcchshshhyyyeua') LIKE '%%' || LOWER(%s) || '%%'
            )
            ORDER BY relevance DESC, o.created_at DESC
            LIMIT 50
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            # Pass query 10 times for all placeholders (5 for relevance + 1 city + 4 for WHERE)
            cursor.execute(sql, (query, query, query, query, query, city, query, query, query, query))
            return [dict(row) for row in cursor.fetchall()]


