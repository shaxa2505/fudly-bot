import pytest

from database import Database as SqliteDatabase


@pytest.fixture()
def temp_db_path(tmp_path):
    p = tmp_path / "test_db.sqlite"
    return str(p)


@pytest.fixture()
def db_instance(temp_db_path):
    # Use SQLite Database implementation directly
    db = SqliteDatabase(temp_db_path)
    # Ensure expiry_time and reminder_sent columns exist for test
    with db.get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("ALTER TABLE bookings ADD COLUMN expiry_time TEXT")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE bookings ADD COLUMN reminder_sent INTEGER DEFAULT 0")
        except Exception:
            pass
        conn.commit()
    yield db
    try:
        db.close()
    except Exception:
        pass


@pytest.mark.asyncio
async def test_booking_expiry_and_reminder(db_instance, monkeypatch):
    db = db_instance

    # Create a user and store and offer
    user_id = 11111
    db.add_user(user_id, "tester", "Tester")
    store_id = db.add_store(user_id, "Test Store", "Test City")
    offer_id = db.add_offer(store_id, "Test Item", "Desc", 100, 50, 5, "", "", None, None)

    # Create a booking manually with expiry_time 70 minutes from now
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO bookings (user_id, offer_id, quantity, booking_code, status, expiry_time, reminder_sent) VALUES (?, ?, ?, ?, 'pending', datetime('now', '+70 minutes'), 0)",
            (user_id, offer_id, 1, "TEST01"),
        )
        booking_id = cursor.lastrowid
        conn.commit()

    # Run the reminder query from the worker logic: bookings expiring within 1 hour
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT booking_id FROM bookings WHERE reminder_sent = 0 AND expiry_time IS NOT NULL AND expiry_time > datetime('now') AND expiry_time <= datetime('now', '+1 hour')"
        )
        rows = cursor.fetchall()
        assert len(rows) == 0  # 70 minutes away -> no reminder yet

    # Update expiry_time to 50 minutes from now so reminder should trigger
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE bookings SET expiry_time = datetime('now', '+50 minutes') WHERE booking_id = ?",
            (booking_id,),
        )
        conn.commit()

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT booking_id FROM bookings WHERE reminder_sent = 0 AND expiry_time IS NOT NULL AND expiry_time > datetime('now') AND expiry_time <= datetime('now', '+1 hour')"
        )
        rows = cursor.fetchall()
        assert len(rows) == 1

    # Simulate reminder_sent marking
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE bookings SET reminder_sent = 1 WHERE booking_id = ?", (booking_id,))
        conn.commit()

    # Now set expiry_time to past to simulate expiration
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE bookings SET expiry_time = datetime('now', '-1 minute') WHERE booking_id = ?",
            (booking_id,),
        )
        conn.commit()

    # Call cancel_booking and ensure status updated and offer quantity incremented
    old_offer = db.get_offer(offer_id)
    # quantity is at index 6 in SQLite get_offer tuple
    old_qty = old_offer[6] if isinstance(old_offer, (list, tuple)) else old_offer.get("quantity")

    # Cancel booking — cancel_booking now returns reserved quantity to the offer atomically
    db.cancel_booking(booking_id)

    updated_offer = db.get_offer(offer_id)
    new_qty = (
        updated_offer[6]
        if isinstance(updated_offer, (list, tuple))
        else updated_offer.get("quantity")
    )

    assert new_qty == old_qty + 1
