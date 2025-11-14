# type: ignore
"""
PostgreSQL Database Module for Fudly Bot
Replaces SQLite with PostgreSQL for production deployment
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Any
from contextlib import contextmanager

# Logging
try:
    from logging_config import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# Cache (optional)
try:
    from cache import cache
except ImportError:
    class SimpleCache:
        def get(self, key): return None
        def set(self, key, value, ex=None): pass
        def delete(self, key): pass
    cache = SimpleCache()

# Database connection configuration
DATABASE_URL = os.environ.get('DATABASE_URL', '')
MIN_CONNECTIONS = int(os.environ.get('DB_MIN_CONN', '1'))
MAX_CONNECTIONS = int(os.environ.get('DB_MAX_CONN', '10'))

class Database:
    def __init__(self, database_url: str = None):
        """
        Initialize PostgreSQL database connection
        
        Args:
            database_url: PostgreSQL connection string (postgresql://user:pass@host:port/dbname)
        """
        self.database_url = database_url or DATABASE_URL
        self.db_name = "PostgreSQL"  # For compatibility with SQLite code
        
        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable is required for PostgreSQL")
        
        # Initialize connection pool
        try:
            self.pool = SimpleConnectionPool(
                MIN_CONNECTIONS,
                MAX_CONNECTIONS,
                self.database_url
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
        conn = self.pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            self.pool.putconn(conn)
    
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
                    FOREIGN KEY (store_id) REFERENCES stores(store_id)
                )
            ''')
            
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
                    user_id BIGINT,
                    store_id INTEGER,
                    order_id INTEGER,
                    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
                    comment TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
                    offer_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (offer_id) REFERENCES offers(offer_id),
                    UNIQUE(user_id, offer_id)
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
            
            conn.commit()
            logger.info("✅ PostgreSQL database schema initialized successfully")
    
    def close(self):
        """Close all connections in the pool"""
        if hasattr(self, 'pool') and self.pool:
            self.pool.closeall()
            logger.info("PostgreSQL connection pool closed")
    
    # User management methods
    def add_user(self, user_id: int, username: str = None, first_name: str = None, 
                 phone: str = None, city: str = 'Ташкент', language: str = 'ru'):
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
    
    def get_user(self, user_id: int):
        """Get user by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
            return dict(cursor.fetchone()) if cursor.rowcount > 0 else None
    
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
    def add_store(self, owner_id: int, name: str, city: str, address: str = None,
                  description: str = None, category: str = 'Ресторан', phone: str = None):
        """Add new store"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO stores (owner_id, name, city, address, description, category, phone)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING store_id
            ''', (owner_id, name, city, address, description, category, phone))
            store_id = cursor.fetchone()[0]
            logger.info(f"Store {store_id} added by user {owner_id}")
            return store_id
    
    def get_store_by_owner(self, owner_id: int):
        """Get store by owner ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('SELECT * FROM stores WHERE owner_id = %s', (owner_id,))
            return dict(cursor.fetchone()) if cursor.rowcount > 0 else None
    
    def get_store(self, store_id: int):
        """Get store by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
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
    
    def get_pending_stores(self):
        """Get all pending stores"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('SELECT * FROM stores WHERE status = %s', ('pending',))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_approved_stores(self, city: str = None):
        """Get approved stores, optionally filtered by city"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
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
                  expiry_date: str = None, photo_id: str = None):
        """Add new offer"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO offers (store_id, title, description, original_price, discount_price,
                                  quantity, available_from, available_until, expiry_date, photo_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING offer_id
            ''', (store_id, title, description, original_price, discount_price,
                  quantity, available_from, available_until, expiry_date, photo_id))
            offer_id = cursor.fetchone()[0]
            logger.info(f"Offer {offer_id} added to store {store_id}")
            return offer_id
    
    def get_offer(self, offer_id: int):
        """Get offer by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('SELECT * FROM offers WHERE offer_id = %s', (offer_id,))
            return dict(cursor.fetchone()) if cursor.rowcount > 0 else None
    
    def get_store_offers(self, store_id: int, status: str = 'active'):
        """Get all offers for a store"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('SELECT * FROM offers WHERE store_id = %s AND status = %s', 
                         (store_id, status))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_active_offers(self, city: str = None):
        """Get all active offers, optionally filtered by city"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            if city:
                cursor.execute('''
                    SELECT o.* FROM offers o
                    JOIN stores s ON o.store_id = s.store_id
                    WHERE o.status = %s AND s.status = %s AND s.city = %s
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
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            query = '''
                SELECT o.*, s.name as store_name, s.address, s.city, s.business_type,
                       CAST((1.0 - o.discount_price::float / o.original_price::float) * 100 AS INTEGER) as discount_percent
                FROM offers o
                JOIN stores s ON o.store_id = s.store_id
                WHERE o.status = 'active' 
                AND o.quantity > 0
                AND (s.status = 'approved' OR s.status = 'active')
            '''
            
            params = []
            if city:
                query += ' AND s.city ILIKE %s'
                params.append(f'%{city}%')
            
            if business_type:
                query += ' AND s.business_type = %s'
                params.append(business_type)
            
            query += '''
                ORDER BY discount_percent DESC, 
                         COALESCE(o.expiry_date, '9999-12-31'::timestamp) ASC,
                         o.created_at DESC
                LIMIT %s OFFSET %s
            '''
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def update_offer_quantity(self, offer_id: int, quantity: int):
        """Update offer quantity"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE offers SET quantity = %s WHERE offer_id = %s', 
                         (quantity, offer_id))
    
    def get_user_stores(self, owner_id: int):
        """Get ALL stores for user (any status)"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
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
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('''
                SELECT o.*, s.name, s.address, s.city, s.category
                FROM offers o
                JOIN stores s ON o.store_id = s.store_id
                WHERE o.store_id = %s AND o.quantity > 0 AND o.expiry_date >= CURRENT_DATE
                ORDER BY o.created_at DESC
            ''', (store_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_top_offers_by_city(self, city: str, limit: int = 10):
        """Get top offers in city (by discount)"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('''
                SELECT o.*, s.name, s.address, s.city, s.category,
                       CAST((o.original_price - o.discount_price)::float / o.original_price * 100 AS INTEGER) as discount_percent
                FROM offers o
                JOIN stores s ON o.store_id = s.store_id
                WHERE s.city = %s AND s.status = 'active' 
                      AND o.status = 'active' AND o.quantity > 0 
                      AND o.expiry_date >= CURRENT_DATE
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
        
        conn = None
        try:
            conn = self.pool.getconn()
            conn.autocommit = False  # Start transaction
            cursor = conn.cursor()
            
            # Check and reserve product atomically
            cursor.execute('''
                SELECT quantity, status FROM offers 
                WHERE offer_id = %s AND status = 'active'
                FOR UPDATE
            ''', (offer_id,))
            offer = cursor.fetchone()
            
            if not offer or offer[0] is None or offer[0] < quantity or offer[1] != 'active':
                conn.rollback()
                return (False, None, None)
            
            current_quantity = offer[0]
            new_quantity = current_quantity - quantity
            
            # Update quantity atomically
            cursor.execute('''
                UPDATE offers 
                SET quantity = %s, 
                    status = CASE WHEN %s <= 0 THEN 'inactive' ELSE 'active' END
                WHERE offer_id = %s AND quantity = %s
            ''', (new_quantity, new_quantity, offer_id, current_quantity))
            
            if cursor.rowcount == 0:
                conn.rollback()
                return (False, None, None)
            
            # Generate unique booking code
            booking_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            
            # Create booking
            cursor.execute('''
                INSERT INTO bookings (offer_id, user_id, booking_code, status, quantity)
                VALUES (%s, %s, %s, 'pending', %s)
                RETURNING booking_id
            ''', (offer_id, user_id, booking_code, quantity))
            booking_id = cursor.fetchone()[0]
            
            conn.commit()
            return (True, booking_id, booking_code)
            
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            logger.error(f"Error creating booking atomically: {e}")
            return (False, None, None)
        finally:
            if conn:
                conn.autocommit = True
                self.pool.putconn(conn)
    
    def get_booking(self, booking_id: int):
        """Get booking by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
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
            cursor = conn.cursor(cursor_factory=RealDictCursor)
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
            cursor = conn.cursor(cursor_factory=RealDictCursor)
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
            cursor = conn.cursor(cursor_factory=RealDictCursor)
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
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('SELECT * FROM stores WHERE city = %s AND status = %s', (city, 'active'))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_all_users(self):
        """Get all users with notifications enabled"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('SELECT * FROM users WHERE notifications_enabled = TRUE')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_all_admins(self):
        """Get all admins"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users WHERE is_admin = TRUE')
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
    
    def get_platform_payment_card(self):
        """Get platform payment card"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('SELECT * FROM payment_settings LIMIT 1')
            result = cursor.fetchone()
            return dict(result) if result else None
    
    def update_user_role(self, user_id: int, role: str):
        """Update user role"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET role = %s WHERE user_id = %s', (role, user_id))
    
    def delete_user(self, user_id: int):
        """Delete user"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM users WHERE user_id = %s', (user_id,))
    
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
            cursor = conn.cursor(cursor_factory=RealDictCursor)
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
            cursor = conn.cursor(cursor_factory=RealDictCursor)
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
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('SELECT * FROM orders WHERE user_id = %s ORDER BY created_at DESC', 
                         (user_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_store_orders(self, store_id: int):
        """Get all orders for a store"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
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
            cursor = conn.cursor(cursor_factory=RealDictCursor)
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
        """Get user bookings"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('SELECT * FROM bookings WHERE user_id = %s AND status = %s', 
                         (user_id, 'active'))
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
            cursor = conn.cursor(cursor_factory=RealDictCursor)
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
    def add_favorite(self, user_id: int, offer_id: int):
        """Add offer to favorites"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO favorites (user_id, offer_id)
                    VALUES (%s, %s)
                ''', (user_id, offer_id))
                return True
        except:
            return False
    
    def remove_favorite(self, user_id: int, offer_id: int):
        """Remove offer from favorites"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM favorites WHERE user_id = %s AND offer_id = %s', 
                         (user_id, offer_id))
    
    def get_user_favorites(self, user_id: int):
        """Get user favorites"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('''
                SELECT o.* FROM offers o
                JOIN favorites f ON o.offer_id = f.offer_id
                WHERE f.user_id = %s AND o.status = %s
            ''', (user_id, 'active'))
            return [dict(row) for row in cursor.fetchall()]
    
    def is_favorite(self, user_id: int, offer_id: int) -> bool:
        """Check if offer is in favorites"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM favorites WHERE user_id = %s AND offer_id = %s', 
                         (user_id, offer_id))
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
