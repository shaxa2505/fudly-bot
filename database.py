# type: ignore
import sqlite3
import os
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

# pooling, caching and structured logging
from db_pool import SQLitePool
from cache import cache
from logging_config import logger

# Module-level pool (configurable via env vars)
DB_PATH = os.environ.get('DATABASE_PATH', 'fudly.db')
POOL = SQLitePool(DB_PATH, maxsize=int(os.environ.get('DB_POOL_SIZE', 5)), timeout=int(os.environ.get('DB_TIMEOUT', 5)))

class Database:
    def __init__(self, db_name: str = "fudly.db"):
        # Backwards-compatible: allow passing explicit db_name (tests). Otherwise use DB_PATH.
        self.db_name = db_name or DB_PATH
        self.init_db()
    
    def get_connection(self):
        """Return a pooled connection. The returned object supports .cursor(), .commit(), and .close().
        Calling .close() will return the underlying connection to the pool.
        """
        try:
            return POOL.getconn()
        except Exception:
            # fallback to direct connection
            conn = sqlite3.connect(self.db_name, timeout=int(os.environ.get('DB_TIMEOUT', 5)))
            try:
                conn.execute('PRAGMA journal_mode=WAL')
            except Exception:
                pass
            return conn
    
    def init_db(self):
        """Инициализация базы данных"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
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
        
        # Таблица ресторанов/магазинов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stores (
                store_id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
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
        
        # Таблица предложений еды
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS offers (
                offer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id INTEGER,
                title TEXT NOT NULL,
                description TEXT,
                original_price REAL,
                discount_price REAL,
                quantity INTEGER DEFAULT 1,
                available_from TEXT,
                available_until TEXT,
                expiry_date TEXT,
                status TEXT DEFAULT 'active',
                photo TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (store_id) REFERENCES stores(store_id)
            )
        ''')
        
        # Таблица бронирований
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                booking_id INTEGER PRIMARY KEY AUTOINCREMENT,
                offer_id INTEGER,
                user_id INTEGER,
                status TEXT DEFAULT 'pending',
                booking_code TEXT,
                pickup_time TEXT,
                quantity INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (offer_id) REFERENCES offers(offer_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        # Добавляем поле quantity если его нет (для старых БД)
        try:
            cursor.execute('ALTER TABLE bookings ADD COLUMN quantity INTEGER DEFAULT 1')
            conn.commit()
        except:
            pass  # Поле уже существует
        
        # Добавляем поле expiry_date если его нет (для старых БД)
        try:
            cursor.execute('ALTER TABLE offers ADD COLUMN expiry_date TEXT')
            conn.commit()
        except:
            pass  # Поле уже существует
        
        # Таблица уведомлений
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message TEXT,
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        # Таблица рейтингов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ratings (
                rating_id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id INTEGER,
                user_id INTEGER,
                store_id INTEGER,
                rating INTEGER CHECK(rating >= 1 AND rating <= 5),
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (booking_id) REFERENCES bookings(booking_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (store_id) REFERENCES stores(store_id)
            )
        ''')
        
        # Таблица избранных магазинов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS favorites (
                favorite_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                store_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (store_id) REFERENCES stores(store_id),
                UNIQUE(user_id, store_id)
            )
        ''')
        
        # Таблица промокодов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS promocodes (
                promo_id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                discount_percent INTEGER DEFAULT 0,
                discount_amount REAL DEFAULT 0,
                max_uses INTEGER DEFAULT 1,
                current_uses INTEGER DEFAULT 0,
                valid_until TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица использования промокодов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS promo_usage (
                usage_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                promo_id INTEGER,
                booking_id INTEGER,
                discount_applied REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (promo_id) REFERENCES promocodes(promo_id),
                FOREIGN KEY (booking_id) REFERENCES bookings(booking_id)
            )
        ''')
        
        # Таблица рефералов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                referral_id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                bonus_given INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                FOREIGN KEY (referred_id) REFERENCES users(user_id)
            )
        ''')
        
        # Добавляем поле bonus_balance в users если его нет
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN bonus_balance REAL DEFAULT 0')
            conn.commit()
        except:
            pass
        
        # Добавляем поле referral_code в users если его нет
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN referral_code TEXT UNIQUE')
            conn.commit()
        except:
            pass
        
        try:
            conn.close()
        except Exception:
            pass

        # create supporting indexes (best-effort)
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_stores_city_status ON stores(city, status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_offers_store_status ON offers(store_id, status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_offers_created ON offers(created_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_bookings_offer ON bookings(offer_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)')
            conn.commit()
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
    
    # Методы для пользователей
    def add_user(self, user_id: int, username: Optional[str] = None, first_name: Optional[str] = None, role: str = 'customer', city: str = 'Ташкент'):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, first_name, role, city)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, role, city))
        conn.commit()
        try:
            conn.close()
        except Exception:
            pass
        try:
            cache.delete('offers:all')
        except Exception:
            pass
    
    def get_user(self, user_id: int) -> Optional[Tuple]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        conn.close()
        return user
    
    def update_user_city(self, user_id: int, city: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET city = ? WHERE user_id = ?', (city, user_id))
        conn.commit()
        conn.close()
    
    def update_user_role(self, user_id: int, role: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET role = ? WHERE user_id = ?', (role, user_id))
        conn.commit()
        conn.close()
    
    def update_user_phone(self, user_id: int, phone: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET phone = ? WHERE user_id = ?', (phone, user_id))
        conn.commit()
        conn.close()
    
    def update_user_language(self, user_id: int, language: str):
        """Обновить язык пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET language = ? WHERE user_id = ?', (language, user_id))
        conn.commit()
        conn.close()
    
    def get_user_language(self, user_id: int) -> str:
        """Получить язык пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT language FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 'ru'
    
    # Методы для магазинов
    def add_store(self, owner_id: int, name: str, city: str, address: Optional[str] = None, description: Optional[str] = None, category: str = 'Ресторан', phone: Optional[str] = None) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO stores (owner_id, name, city, address, description, category, phone, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
        ''', (owner_id, name, city, address, description, category, phone))
        store_id = cursor.lastrowid
        conn.commit()
        try:
            conn.close()
        except Exception:
            pass
        # invalidate relevant cache keys
        try:
            cache.delete(f'stores:city:{city}')
            cache.delete('offers:all')
        except Exception:
            pass
        return store_id
    
    def get_user_stores(self, owner_id: int) -> List[Tuple]:
        """Получить ВСЕ магазины пользователя (любой статус)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.*, u.first_name, u.username 
            FROM stores s
            LEFT JOIN users u ON s.owner_id = u.user_id
            WHERE s.owner_id = ?
            ORDER BY s.created_at DESC
        ''', (owner_id,))
        stores = cursor.fetchall()
        conn.close()
        return stores
    
    def get_approved_stores(self, owner_id: int) -> List[Tuple]:
        """Получить только ОДОБРЕННЫЕ магазины пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM stores WHERE owner_id = ? AND status = "approved"', (owner_id,))
        stores = cursor.fetchall()
        conn.close()
        return stores
    
    def get_store(self, store_id: int) -> Optional[Tuple]:
        key = f'store:{store_id}'
        try:
            cached = cache.get(key)
            if cached is not None:
                return cached
        except Exception:
            pass

        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM stores WHERE store_id = ?', (store_id,))
        store = cursor.fetchone()
        try:
            conn.close()
        except Exception:
            pass

        try:
            cache.set(key, store, ex=int(os.environ.get('CACHE_TTL_SECONDS', 300)))
        except Exception:
            pass

        return store
    
    def get_stores_by_city(self, city: str) -> List[Tuple]:
        key = f'stores:city:{city}'
        try:
            cached = cache.get(key)
            if cached is not None:
                return cached
        except Exception:
            pass

        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM stores WHERE city = ? AND status = "approved"', (city,))
        stores = cursor.fetchall()
        try:
            conn.close()
        except Exception:
            pass

        try:
            cache.set(key, stores, ex=int(os.environ.get('CACHE_TTL_SECONDS', 300)))
        except Exception:
            pass

        return stores
    
    def _format_datetime_field(self, time_input: str) -> str:
        """
        Преобразует различные форматы времени в стандартный формат YYYY-MM-DD HH:MM
        """
        from datetime import datetime, timedelta
        
        if not time_input:
            return ""
            
        time_input = time_input.strip()
        
        # Если уже в правильном формате - возвращаем как есть
        try:
            datetime.strptime(time_input, '%Y-%m-%d %H:%M')
            return time_input
        except ValueError:
            pass
        
        current_date = datetime.now()
        
        # Обрабатываем формат HH:MM (например "21:00")
        try:
            time_obj = datetime.strptime(time_input, '%H:%M')
            # Добавляем сегодняшнюю дату
            result_dt = current_date.replace(
                hour=time_obj.hour, 
                minute=time_obj.minute, 
                second=0, 
                microsecond=0
            )
            # Если время уже прошло сегодня, переносим на завтра
            if result_dt <= current_date:
                result_dt += timedelta(days=1)
            return result_dt.strftime('%Y-%m-%d %H:%M')
        except ValueError:
            pass
        
        # Обрабатываем формат HH (например "21")
        try:
            hour = int(time_input)
            if 0 <= hour <= 23:
                result_dt = current_date.replace(
                    hour=hour, 
                    minute=0, 
                    second=0, 
                    microsecond=0
                )
                # Если время уже прошло сегодня, переносим на завтра
                if result_dt <= current_date:
                    result_dt += timedelta(days=1)
                return result_dt.strftime('%Y-%m-%d %H:%M')
        except ValueError:
            pass
        
        # Если ничего не подходит, возвращаем исходное значение
        return time_input

    # Методы для предложений
    def add_offer(self, store_id: int, title: str, description: str, original_price: float, 
                  discount_price: float, quantity: int, available_from: str, available_until: str, 
                  photo: str = None, expiry_date: str = None) -> int:
        
        # Приводим время к стандартному формату
        formatted_from = self._format_datetime_field(available_from)
        formatted_until = self._format_datetime_field(available_until)
        
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO offers (store_id, title, description, original_price, discount_price, 
                              quantity, available_from, available_until, expiry_date, status, photo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
        ''', (store_id, title, description, original_price, discount_price, quantity, formatted_from, formatted_until, expiry_date, photo))
        offer_id = cursor.lastrowid
        conn.commit()
        try:
            conn.close()
        except Exception:
            pass
        # invalidate related caches
        try:
            cache.delete('offers:all')
            cache.delete(f'offers:store:{store_id}')
            cache.delete(f'store:{store_id}')
        except Exception:
            pass
        return offer_id
    
    def get_active_offers(self, city: str = None, store_id: int = None) -> List[Tuple]:
        # Cache keys: offers:all, offers:city:<city>, offers:store:<id>
        cache_key = 'offers:all'
        if store_id:
            cache_key = f'offers:store:{store_id}'
        elif city:
            cache_key = f'offers:city:{city}'
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
        except Exception:
            pass

        conn = self.get_connection()
        cursor = conn.cursor()
        
        if store_id:
            # Фильтр по конкретному магазину
            cursor.execute('''
                SELECT o.*, s.name as store_name, s.address, s.city, s.category
                FROM offers o
                JOIN stores s ON o.store_id = s.store_id
                WHERE o.status = 'active' AND o.quantity > 0 AND s.store_id = ? AND s.status = 'approved'
                ORDER BY o.created_at DESC
            ''', (store_id,))
        elif city:
            # Фильтр по городу
            cursor.execute('''
                SELECT o.*, s.name as store_name, s.address, s.city, s.category
                FROM offers o
                JOIN stores s ON o.store_id = s.store_id
                WHERE o.status = 'active' AND o.quantity > 0 AND s.city = ? AND s.status = 'approved'
                ORDER BY o.created_at DESC
            ''', (city,))
        else:
            # Все предложения
            cursor.execute('''
                SELECT o.*, s.name as store_name, s.address, s.city, s.category
                FROM offers o
                JOIN stores s ON o.store_id = s.store_id
                WHERE o.status = 'active' AND o.quantity > 0 AND s.status = 'approved'
                ORDER BY o.created_at DESC
            ''')
        
        offers = cursor.fetchall()
        try:
            conn.close()
        except Exception:
            pass
        
        # Фильтруем товары с истёкшим сроком годности
        from datetime import datetime
        valid_offers = []
        for offer in offers:
            # Проверяем срок годности если он указан (индекс 9 - expiry_date)
            if len(offer) > 9 and offer[9]:
                try:
                    # Преобразуем дату из формата DD.MM.YYYY
                    expiry_parts = offer[9].split('.')
                    if len(expiry_parts) == 3:
                        expiry_date = datetime(int(expiry_parts[2]), int(expiry_parts[1]), int(expiry_parts[0]))
                        # Если срок годности не истёк
                        if expiry_date >= datetime.now():
                            valid_offers.append(offer)
                    else:
                        valid_offers.append(offer)  # Неверный формат - показываем
                except:
                    valid_offers.append(offer)  # Ошибка парсинга - показываем
            else:
                valid_offers.append(offer)  # Нет срока годности - показываем
        
        # cache result
        try:
            cache.set(cache_key, valid_offers, ex=int(os.environ.get('CACHE_TTL_SECONDS', 120)))
        except Exception:
            pass

        return valid_offers
    
    def get_offer(self, offer_id: int) -> Optional[Tuple]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT o.*, s.name as store_name, s.address, s.city, s.category
            FROM offers o
            JOIN stores s ON o.store_id = s.store_id
            WHERE o.offer_id = ?
        ''', (offer_id,))
        offer = cursor.fetchone()
        conn.close()
        return offer
    
    def get_store_offers(self, store_id: int) -> List[Tuple]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM offers WHERE store_id = ? ORDER BY created_at DESC', (store_id,))
        offers = cursor.fetchall()
        conn.close()
        return offers
    
    def update_offer_quantity(self, offer_id: int, new_quantity: int):
        """Обновить количество товара и автоматически управлять статусом"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if new_quantity <= 0:
            # Если товар закончился - ставим quantity=0 и деактивируем
            cursor.execute('UPDATE offers SET quantity = 0, status = ? WHERE offer_id = ?', ('inactive', offer_id))
        else:
            # Если товар есть - активируем (на случай возврата при отмене)
            cursor.execute('UPDATE offers SET quantity = ?, status = ? WHERE offer_id = ?', (new_quantity, 'active', offer_id))
        
        conn.commit()
        conn.close()
    
    def deactivate_offer(self, offer_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE offers SET status = ? WHERE offer_id = ?', ('inactive', offer_id))
        conn.commit()
        try:
            conn.close()
        except Exception:
            pass
        try:
            cache.delete('offers:all')
        except Exception:
            pass
    
    def delete_expired_offers(self):
        """Удаляет предложения с истёкшим сроком действия"""
        from datetime import datetime
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Получаем текущую дату и время
        now = datetime.now()
        current_time_str = now.strftime('%Y-%m-%d %H:%M')
        
        # Сначала нормализуем все записи с неправильным форматом времени
        cursor.execute('SELECT offer_id, available_until FROM offers WHERE status = "active"')
        offers_to_fix = cursor.fetchall()
        
        for offer_id, available_until in offers_to_fix:
            if available_until:
                # Приводим к правильному формату если нужно
                normalized_time = self._format_datetime_field(available_until)
                if normalized_time != available_until:
                    cursor.execute(
                        'UPDATE offers SET available_until = ? WHERE offer_id = ?', 
                        (normalized_time, offer_id)
                    )
        
        conn.commit()
        
        # Теперь деактивируем истекшие предложения
        cursor.execute('''
            UPDATE offers 
            SET status = 'inactive' 
            WHERE status = 'active' 
            AND available_until != ''
            AND available_until IS NOT NULL
            AND (
                datetime(available_until) < datetime(?)
                OR available_until NOT LIKE '%-%-%'
            )
        ''', (current_time_str,))
        
        deleted_count = cursor.rowcount
        conn.commit()
        try:
            conn.close()
        except Exception:
            pass
        # Invalidate offers cache when expiry cleanups happen
        try:
            cache.delete('offers:all')
        except Exception:
            pass
        return deleted_count
    
    # Методы для бронирований
    def create_booking(self, offer_id: int, user_id: int, booking_code: str) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO bookings (offer_id, user_id, booking_code, status)
            VALUES (?, ?, ?, 'pending')
        ''', (offer_id, user_id, booking_code))
        booking_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return booking_id
    
    def get_user_bookings(self, user_id: int) -> List[Tuple]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT b.*, o.title, o.discount_price, o.available_until, s.name, s.address, s.city
            FROM bookings b
            JOIN offers o ON b.offer_id = o.offer_id
            JOIN stores s ON o.store_id = s.store_id
            WHERE b.user_id = ?
            ORDER BY b.created_at DESC
        ''', (user_id,))
        bookings = cursor.fetchall()
        conn.close()
        return bookings
    
    def get_booking(self, booking_id: int) -> Optional[Tuple]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM bookings WHERE booking_id = ?', (booking_id,))
        booking = cursor.fetchone()
        conn.close()
        return booking
    
    def get_booking_by_code(self, booking_code: str) -> Optional[Tuple]:
        """Получить бронирование по коду"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT b.*, u.first_name, u.username
            FROM bookings b
            JOIN users u ON b.user_id = u.user_id
            WHERE b.booking_code = ? AND b.status = 'pending'
        ''', (booking_code,))
        booking = cursor.fetchone()
        conn.close()
        return booking
    
    def update_booking_status(self, booking_id: int, status: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE bookings SET status = ? WHERE booking_id = ?', (status, booking_id))
        conn.commit()
        conn.close()
    
    def complete_booking(self, booking_id: int):
        """Завершить бронирование"""
        self.update_booking_status(booking_id, 'completed')
    
    def cancel_booking(self, booking_id: int):
        """Отменить бронирование"""
        self.update_booking_status(booking_id, 'cancelled')
    
    def get_store_bookings(self, store_id: int) -> List[Tuple]:
        """Получить все бронирования для магазина"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT b.*, o.title, u.first_name, u.username
            FROM bookings b
            JOIN offers o ON b.offer_id = o.offer_id
            JOIN users u ON b.user_id = u.user_id
            WHERE o.store_id = ?
            ORDER BY b.created_at DESC
        ''', (store_id,))
        bookings = cursor.fetchall()
        conn.close()
        return bookings
    
    # Методы для админа
    def set_admin(self, user_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET is_admin = 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
    
    def is_admin(self, user_id: int) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT is_admin FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result and result[0] == 1
    
    def get_all_admins(self) -> List[Tuple]:
        """Получить всех администраторов"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users WHERE is_admin = 1')
        admins = cursor.fetchall()
        conn.close()
        return admins
    
    def get_pending_stores(self) -> List[Tuple]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.*, u.first_name, u.username
            FROM stores s
            JOIN users u ON s.owner_id = u.user_id
            WHERE s.status = 'pending'
            ORDER BY s.created_at DESC
        ''')
        stores = cursor.fetchall()
        conn.close()
        return stores
    
    def approve_store(self, store_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE stores SET status = ? WHERE store_id = ?', ('approved', store_id))
        cursor.execute('UPDATE users SET role = ? WHERE user_id = (SELECT owner_id FROM stores WHERE store_id = ?)', ('seller', store_id))
        conn.commit()
        conn.close()
    
    def reject_store(self, store_id: int, reason: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE stores SET status = ?, rejection_reason = ? WHERE store_id = ?', ('rejected', reason, store_id))
        conn.commit()
        conn.close()
    
    def get_store_owner(self, store_id: int) -> Optional[int]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT owner_id FROM stores WHERE store_id = ?', (store_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def get_statistics(self) -> dict:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        # Пользователи
        cursor.execute('SELECT COUNT(*) FROM users')
        stats['users'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE role = ?', ('customer',))
        stats['customers'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE role = ?', ('seller',))
        stats['sellers'] = cursor.fetchone()[0]
        
        # Магазины
        cursor.execute('SELECT COUNT(*) FROM stores')
        stats['stores'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM stores WHERE status = ?', ('approved',))
        stats['approved_stores'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM stores WHERE status = ?', ('pending',))
        stats['pending_stores'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM stores WHERE status = ?', ('rejected',))
        stats['rejected_stores'] = cursor.fetchone()[0]
        
        # Предложения
        cursor.execute('SELECT COUNT(*) FROM offers')
        stats['offers'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM offers WHERE status = ?', ('active',))
        stats['active_offers'] = cursor.fetchone()[0]
        
        # Бронирования
        cursor.execute('SELECT COUNT(*) FROM bookings')
        stats['bookings'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = ?', ('pending',))
        stats['pending_bookings'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = ?', ('completed',))
        stats['completed_bookings'] = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = ?', ('cancelled',))
        stats['cancelled_bookings'] = cursor.fetchone()[0]
        
        conn.close()
        return stats
    
    def get_all_users(self) -> List[Tuple]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE notifications_enabled = 1')
        users = cursor.fetchall()
        conn.close()
        return users
    
    def add_notification(self, user_id: int, message: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO notifications (user_id, message) VALUES (?, ?)', (user_id, message))
        conn.commit()
        conn.close()
    
    def toggle_notifications(self, user_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT notifications_enabled FROM users WHERE user_id = ?', (user_id,))
        current = cursor.fetchone()[0]
        new_value = 0 if current == 1 else 1
        cursor.execute('UPDATE users SET notifications_enabled = ? WHERE user_id = ?', (new_value, user_id))
        conn.commit()
        conn.close()
        return new_value == 1
    
    # Методы для рейтингов
    def add_rating(self, booking_id: int, user_id: int, store_id: int, rating: int, comment: str = None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO ratings (booking_id, user_id, store_id, rating, comment)
            VALUES (?, ?, ?, ?, ?)
        ''', (booking_id, user_id, store_id, rating, comment))
        conn.commit()
        conn.close()
    
    def get_store_ratings(self, store_id: int) -> List[Tuple]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT r.*, u.first_name, u.username
            FROM ratings r
            JOIN users u ON r.user_id = u.user_id
            WHERE r.store_id = ?
            ORDER BY r.created_at DESC
        ''', (store_id,))
        ratings = cursor.fetchall()
        conn.close()
        return ratings
    
    def get_store_average_rating(self, store_id: int) -> float:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT AVG(rating) FROM ratings WHERE store_id = ?', (store_id,))
        result = cursor.fetchone()
        conn.close()
        return round(result[0], 1) if result[0] else 0.0
    
    def has_rated_booking(self, booking_id: int) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM ratings WHERE booking_id = ?', (booking_id,))
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    
    # Методы для статистики продаж
    def get_store_sales_stats(self, store_id: int) -> dict:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        # Всего продано
        cursor.execute('''
            SELECT COUNT(*), SUM(o.discount_price)
            FROM bookings b
            JOIN offers o ON b.offer_id = o.offer_id
            WHERE o.store_id = ? AND b.status = 'completed'
        ''', (store_id,))
        result = cursor.fetchone()
        stats['total_sales'] = result[0] if result[0] else 0
        stats['total_revenue'] = result[1] if result[1] else 0
        
        # Активные брони
        cursor.execute('''
            SELECT COUNT(*)
            FROM bookings b
            JOIN offers o ON b.offer_id = o.offer_id
            WHERE o.store_id = ? AND b.status = 'pending'
        ''', (store_id,))
        stats['pending_bookings'] = cursor.fetchone()[0]
        
        conn.close()
        return stats

    # Методы для рейтингов
    def add_rating(self, booking_id: int, user_id: int, store_id: int, rating: int, comment: str = None):
        """Добавить рейтинг"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO ratings (booking_id, user_id, store_id, rating, comment)
            VALUES (?, ?, ?, ?, ?)
        ''', (booking_id, user_id, store_id, rating, comment))
        conn.commit()
        conn.close()
    
    def get_store_ratings(self, store_id: int) -> List[Tuple]:
        """Получить все рейтинги магазина"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT r.*, u.first_name
            FROM ratings r
            JOIN users u ON r.user_id = u.user_id
            WHERE r.store_id = ?
            ORDER BY r.created_at DESC
        ''', (store_id,))
        ratings = cursor.fetchall()
        conn.close()
        return ratings
    
    def get_store_average_rating(self, store_id: int) -> float:
        """Получить средний рейтинг магазина"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT AVG(rating) FROM ratings WHERE store_id = ?', (store_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result[0] else 0.0
    
    def has_rated_booking(self, booking_id: int) -> bool:
        """Проверить, оценил ли пользователь бронирование"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM ratings WHERE booking_id = ?', (booking_id,))
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    
    # Методы для управления пользователями
    def delete_user(self, user_id: int):
        """Полное удаление пользователя и всех связанных данных"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Получаем все магазины пользователя
        cursor.execute('SELECT store_id FROM stores WHERE owner_id = ?', (user_id,))
        stores = cursor.fetchall()
        
        # Удаляем все связанные данные для каждого магазина
        for store in stores:
            store_id = store[0]
            # Удаляем рейтинги магазина
            cursor.execute('DELETE FROM ratings WHERE store_id = ?', (store_id,))
            # Удаляем бронирования на предложения этого магазина
            cursor.execute('''
                DELETE FROM bookings 
                WHERE offer_id IN (SELECT offer_id FROM offers WHERE store_id = ?)
            ''', (store_id,))
            # Удаляем предложения магазина
            cursor.execute('DELETE FROM offers WHERE store_id = ?', (store_id,))
        
        # Удаляем магазины пользователя
        cursor.execute('DELETE FROM stores WHERE owner_id = ?', (user_id,))
        
        # Удаляем бронирования пользователя (как клиента)
        cursor.execute('DELETE FROM bookings WHERE user_id = ?', (user_id,))
        
        # Удаляем рейтинги пользователя
        cursor.execute('DELETE FROM ratings WHERE user_id = ?', (user_id,))
        
        # Удаляем уведомления пользователя
        cursor.execute('DELETE FROM notifications WHERE user_id = ?', (user_id,))
        
        # Удаляем самого пользователя
        cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        
        conn.commit()
        conn.close()
    
    # ============== НОВЫЕ МЕТОДЫ ==============
    
    # Избранное
    def add_to_favorites(self, user_id: int, store_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO favorites (user_id, store_id) VALUES (?, ?)', (user_id, store_id))
            conn.commit()
        except:
            pass  # Уже в избранном
        conn.close()
    
    def remove_from_favorites(self, user_id: int, store_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM favorites WHERE user_id = ? AND store_id = ?', (user_id, store_id))
        conn.commit()
        conn.close()
    
    def get_user_favorites(self, user_id: int) -> List[Tuple]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.* FROM stores s
            JOIN favorites f ON s.store_id = f.store_id
            WHERE f.user_id = ?
            ORDER BY f.created_at DESC
        ''', (user_id,))
        favorites = cursor.fetchall()
        conn.close()
        return favorites
    
    def is_favorite(self, user_id: int, store_id: int) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM favorites WHERE user_id = ? AND store_id = ?', (user_id, store_id))
        result = cursor.fetchone() is not None
        conn.close()
        return result
    
    # История бронирований
    def get_booking_history(self, user_id: int, status: str = None) -> List[Tuple]:
        conn = self.get_connection()
        cursor = conn.cursor()
        if status:
            cursor.execute('''
                SELECT b.*, o.title, o.discount_price, o.original_price, s.name, s.address, s.city
                FROM bookings b
                JOIN offers o ON b.offer_id = o.offer_id
                JOIN stores s ON o.store_id = s.store_id
                WHERE b.user_id = ? AND b.status = ?
                ORDER BY b.created_at DESC
            ''', (user_id, status))
        else:
            cursor.execute('''
                SELECT b.*, o.title, o.discount_price, o.original_price, s.name, s.address, s.city
                FROM bookings b
                JOIN offers o ON b.offer_id = o.offer_id
                JOIN stores s ON o.store_id = s.store_id
                WHERE b.user_id = ?
                ORDER BY b.created_at DESC
            ''', (user_id,))
        history = cursor.fetchall()
        conn.close()
        return history
    
    def get_user_savings(self, user_id: int) -> float:
        """Подсчитывает сколько пользователь сэкономил"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT SUM((o.original_price - o.discount_price) * b.quantity)
            FROM bookings b
            JOIN offers o ON b.offer_id = o.offer_id
            WHERE b.user_id = ? AND b.status = 'completed'
        ''', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result and result[0] else 0
    
    # Промокоды
    def create_promo(self, code: str, discount_percent: int = 0, discount_amount: float = 0, max_uses: int = 1, valid_until: str = None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO promocodes (code, discount_percent, discount_amount, max_uses, valid_until)
            VALUES (?, ?, ?, ?, ?)
        ''', (code, discount_percent, discount_amount, max_uses, valid_until))
        conn.commit()
        conn.close()
    
    def get_promo(self, code: str) -> Optional[Tuple]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM promocodes WHERE code = ?', (code,))
        promo = cursor.fetchone()
        conn.close()
        return promo
    
    def use_promo(self, user_id: int, promo_id: int, booking_id: int, discount_applied: float):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO promo_usage (user_id, promo_id, booking_id, discount_applied)
            VALUES (?, ?, ?, ?)
        ''', (user_id, promo_id, booking_id, discount_applied))
        cursor.execute('UPDATE promocodes SET current_uses = current_uses + 1 WHERE promo_id = ?', (promo_id,))
        conn.commit()
        conn.close()
    
    # Реферальная система
    def generate_referral_code(self, user_id: int) -> str:
        import random, string
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET referral_code = ? WHERE user_id = ?', (code, user_id))
        conn.commit()
        conn.close()
        return code
    
    def use_referral(self, referrer_code: str, referred_id: int) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users WHERE referral_code = ?', (referrer_code,))
        referrer = cursor.fetchone()
        if referrer:
            cursor.execute('''
                INSERT INTO referrals (referrer_id, referred_id, bonus_given)
                VALUES (?, ?, 1)
            ''', (referrer[0], referred_id))
            cursor.execute('UPDATE users SET bonus_balance = bonus_balance + 5000 WHERE user_id = ?', (referrer[0],))
            cursor.execute('UPDATE users SET bonus_balance = bonus_balance + 3000 WHERE user_id = ?', (referred_id,))
            conn.commit()
            conn.close()
            return True
        conn.close()
        return False
    
    # Логирование ошибок
    def log_error(self, error_message: str, user_id: int = None):
        import logging
        logging.basicConfig(filename='fudly_errors.log', level=logging.ERROR)
        logging.error(f"User {user_id}: {error_message}")
    
    # Бэкап базы данных
    def backup_database(self):
        import shutil
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = f'fudly_backup_{timestamp}.db'
        shutil.copy2(self.db_name, backup_file)
        return backup_file

    def delete_store(self, store_id: int):
        """Полное удаление магазина и всех связанных данных"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Получаем user_id владельца магазина
        cursor.execute('SELECT user_id FROM stores WHERE store_id = ?', (store_id,))
        result = cursor.fetchone()
        if not result:
            conn.close()
            return
        
        user_id = result[0]
        
        # Удаляем рейтинги магазина
        cursor.execute('DELETE FROM ratings WHERE store_id = ?', (store_id,))
        
        # Удаляем бронирования на предложения этого магазина
        cursor.execute('''
            DELETE FROM bookings 
            WHERE offer_id IN (SELECT offer_id FROM offers WHERE store_id = ?)
        ''', (store_id,))
        
        # Удаляем предложения магазина
        cursor.execute('DELETE FROM offers WHERE store_id = ?', (store_id,))
        
        # Удаляем сам магазин
        cursor.execute('DELETE FROM stores WHERE store_id = ?', (store_id,))
        
        # Проверяем, остались ли у пользователя другие магазины
        cursor.execute('SELECT COUNT(*) FROM stores WHERE user_id = ?', (user_id,))
        remaining_stores = cursor.fetchone()[0]
        
        # Если магазинов не осталось - меняем роль на customer
        if remaining_stores == 0:
            cursor.execute('UPDATE users SET role = "customer" WHERE user_id = ?', (user_id,))
        
        conn.commit()
        conn.close()

    @staticmethod
    def get_time_remaining(available_until: str) -> str:
        """
        Возвращает строку с оставшимся временем до окончания акции
        Формат: '🕐 Осталось: 2 часа 15 минут ⏳' или '⏰ Акция закончилась'
        """
        if not available_until:
            return ""
            
        try:
            # Парсим время окончания
            end_time = datetime.strptime(available_until, '%Y-%m-%d %H:%M')
            current_time = datetime.now()
            
            # Если акция уже закончилась
            if end_time <= current_time:
                return "⏰ Акция закончилась"
                
            # Вычисляем разницу
            time_diff = end_time - current_time
            
            # Получаем дни, часы и минуты
            days = time_diff.days
            hours, remainder = divmod(time_diff.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            
            # Формируем строку
            time_parts = []
            
            if days > 0:
                if days == 1:
                    time_parts.append("1 день")
                elif days < 5:
                    time_parts.append(f"{days} дня")
                else:
                    time_parts.append(f"{days} дней")
                    
            if hours > 0:
                if hours == 1:
                    time_parts.append("1 час")
                elif hours < 5:
                    time_parts.append(f"{hours} часа")
                else:
                    time_parts.append(f"{hours} часов")
                    
            if minutes > 0:
                if minutes == 1:
                    time_parts.append("1 минута")
                elif minutes < 5:
                    time_parts.append(f"{minutes} минуты")
                else:
                    time_parts.append(f"{minutes} минут")
            
            # Если осталось меньше минуты
            if not time_parts:
                return "🕐 Осталось: меньше минуты ⏳"
                
            time_str = " ".join(time_parts)
            return f"🕐 Осталось: {time_str} ⏳"
            
        except ValueError:
            # Если формат времени некорректный
            return ""

