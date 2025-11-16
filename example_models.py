"""Example of using domain models."""
from datetime import datetime, timedelta

from app.domain import User, Store, Offer, Booking
from app.domain import Language, UserRole, StoreStatus, BookingStatus


def example_user_model():
    """Example: Creating and using User model."""
    print("=== User Model Example ===\n")
    
    # Create user from data
    user = User(
        user_id=123456789,
        username="john_doe",
        first_name="John",
        phone="+998901234567",
        city="Ташкент",
        language=Language.RUSSIAN,
        role=UserRole.CUSTOMER,
    )
    
    print(f"User: {user.display_name}")
    print(f"City: {user.city}")
    print(f"Language: {user.language}")
    print(f"Is seller: {user.is_seller}")
    print(f"Is admin: {user.is_admin}")
    
    # Convert to dict for database
    print(f"\nDict: {user.to_dict()}")
    
    # Create from database tuple
    db_row = (123456789, "john_doe", "John", "+998901234567", "Ташкент", "ru", "customer", True, None)
    user_from_db = User.from_db_row(db_row)
    print(f"\nFrom DB: {user_from_db.first_name} ({user_from_db.city})")


def example_store_model():
    """Example: Creating and using Store model."""
    print("\n\n=== Store Model Example ===\n")
    
    store = Store(
        store_id=1,
        owner_id=123456789,
        name="Вкусная пекарня",
        address="ул. Навои, 15",
        city="Ташкент",
        category="bakery",
        status=StoreStatus.ACTIVE,
        phone="+998901111111",
        delivery_enabled=True,
        delivery_price=15000,
        min_order_amount=30000,
    )
    
    print(f"Store: {store.name}")
    print(f"Status: {store.status}")
    print(f"Is active: {store.is_active}")
    print(f"Delivery: {store.delivery_enabled} (price: {store.delivery_price} sum)")


def example_offer_model():
    """Example: Creating and using Offer model."""
    print("\n\n=== Offer Model Example ===\n")
    
    offer = Offer(
        offer_id=1,
        store_id=1,
        title="Свежий хлеб",
        description="Вчерашний хлеб со скидкой 50%",
        original_price=5000,
        discounted_price=2500,
        quantity=20,
        unit="шт",
        category="Хлеб и выпечка",
        expires_at=datetime.now() + timedelta(hours=2),
    )
    
    print(f"Offer: {offer.title}")
    print(f"Price: {offer.original_price} → {offer.discounted_price} sum")
    print(f"Discount: {offer.discount_percentage}%")
    print(f"Available: {offer.quantity} {offer.unit}")
    print(f"Is available: {offer.is_available}")
    print(f"Is expired: {offer.is_expired}")
    
    # Reduce quantity
    offer.reduce_quantity(3)
    print(f"\nAfter booking 3: {offer.quantity} {offer.unit} left")


def example_booking_model():
    """Example: Creating and using Booking model."""
    print("\n\n=== Booking Model Example ===\n")
    
    # Create new booking
    booking = Booking.create(
        user_id=123456789,
        offer_id=1,
        store_id=1,
        quantity=3,
        total_price=7500,
    )
    
    print(f"Booking #{booking.booking_id or 'NEW'}")
    print(f"Status: {booking.status}")
    print(f"Quantity: {booking.quantity}")
    print(f"Total: {booking.total_price} sum")
    print(f"Is active: {booking.is_active}")
    print(f"Can be rated: {booking.can_be_rated}")
    
    # Complete booking
    booking.complete()
    print(f"\nAfter completion:")
    print(f"Status: {booking.status}")
    print(f"Is completed: {booking.is_completed}")
    print(f"Can be rated: {booking.can_be_rated}")
    
    # Rate booking
    booking.rate(5)
    print(f"\nRating: {booking.rating}/5")


def example_validation():
    """Example: Validation in models."""
    print("\n\n=== Validation Example ===\n")
    
    try:
        # Invalid phone
        user = User(
            user_id=123,
            first_name="Test",
            phone="invalid",
            city="Ташкент",
        )
    except Exception as e:
        print(f"❌ Invalid phone: {e}")
    
    try:
        # Discounted price >= original price
        offer = Offer(
            store_id=1,
            title="Test",
            original_price=5000,
            discounted_price=6000,  # Invalid!
            quantity=10,
        )
    except Exception as e:
        print(f"❌ Invalid discount: {e}")
    
    try:
        # Invalid rating
        booking = Booking(
            user_id=123,
            offer_id=1,
            store_id=1,
            quantity=1,
            total_price=1000,
        )
        booking.complete()
        booking.rate(10)  # Invalid!
    except Exception as e:
        print(f"❌ Invalid rating: {e}")


if __name__ == "__main__":
    example_user_model()
    example_store_model()
    example_offer_model()
    example_booking_model()
    example_validation()
    
    print("\n\n✅ All examples completed!")
