"""Application-wide constants and configuration values.

Centralizes magic numbers and configuration to avoid duplication
and make changes easier.
"""

# ============== TIME CONSTANTS (seconds) ==============
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
SECONDS_PER_DAY = 86400

# Cache TTL
CACHE_TTL_SHORT = 60  # 1 minute - for frequently changing data
CACHE_TTL_MEDIUM = 300  # 5 minutes - for semi-stable data
CACHE_TTL_LONG = 3600  # 1 hour - for stable data
CACHE_TTL_DAY = 86400  # 24 hours - for rarely changing data

# ============== PAGINATION ==============
DEFAULT_PAGE_SIZE = 5
MAX_PAGE_SIZE = 20
OFFERS_PER_PAGE = 5
STORES_PER_PAGE = 10
ORDERS_PER_PAGE = 10

# ============== BOOKING/ORDER ==============
BOOKING_EXPIRY_HOURS = 24
BOOKING_REMINDER_HOURS = 2
ORDER_CANCEL_WINDOW_MINUTES = 30

# ============== DELIVERY ==============
DEFAULT_DELIVERY_PRICE = 15000  # 15,000 sum
MIN_DELIVERY_PRICE = 10000
DEFAULT_DELIVERY_RADIUS_KM = 10
MAX_DELIVERY_RADIUS_KM = 100

# ============== VALIDATION ==============
MIN_OFFER_PRICE = 1000  # 1,000 sum minimum
MAX_OFFER_PRICE = 100_000_000  # 100 million sum maximum
MIN_QUANTITY = 1
MAX_QUANTITY = 1000
MIN_PHONE_DIGITS = 9
MAX_TITLE_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 1000

# ============== RATE LIMITING ==============
RATE_LIMIT_REQUESTS = 30
RATE_LIMIT_WINDOW_SECONDS = 60

# ============== API TIMEOUTS ==============
API_TIMEOUT_SECONDS = 30
TELEGRAM_API_TIMEOUT = 60

# ============== WORKER INTERVALS ==============
BOOKING_WORKER_INTERVAL_SECONDS = 300  # 5 minutes
DISCOUNT_UPDATE_INTERVAL_SECONDS = 3600  # 1 hour

# ============== MESSAGE LIMITS ==============
MAX_CALLBACK_DATA_LENGTH = 64
MAX_INLINE_BUTTONS_PER_ROW = 8
MAX_KEYBOARD_BUTTONS = 100

# ============== CURRENCY ==============
CURRENCY_UZ = "so'm"
CURRENCY_RU = "сум"


# ============== STATUS VALUES ==============
class OrderStatus:
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    READY = "ready"
    IN_DELIVERY = "in_delivery"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class BookingStatus:
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class StoreStatus:
    PENDING = "pending"
    ACTIVE = "active"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class OfferStatus:
    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"


class PaymentStatus:
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    REFUNDED = "refunded"
