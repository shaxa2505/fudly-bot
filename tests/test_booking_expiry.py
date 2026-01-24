import pytest


@pytest.mark.asyncio
async def test_booking_expiry_and_reminder(db, monkeypatch):

    # Create a user and store and offer
    user_id = 11111
    db.add_user(user_id=user_id, username="tester", first_name="Tester")
    store_id = db.add_store(owner_id=user_id, name="Test Store", city="Test City")
    offer_id = db.add_offer(
        store_id=store_id,
        title="Test Item",
        description="Desc",
        original_price=100,
        discount_price=50,
        quantity=5,
    )

    # Create a booking manually with expiry_time 70 minutes from now
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO bookings (
                user_id, offer_id, store_id, quantity, booking_code, status, expiry_time, reminder_sent
            )
            VALUES (%s, %s, %s, %s, %s, 'pending', NOW() + INTERVAL '70 minutes', 0)
            RETURNING booking_id
            """,
            (user_id, offer_id, store_id, 1, "TEST01"),
        )
        booking_id = cursor.fetchone()[0]

    # Run the reminder query from the worker logic: bookings expiring within 1 hour
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT booking_id
            FROM bookings
            WHERE reminder_sent = 0
              AND expiry_time IS NOT NULL
              AND expiry_time > NOW()
              AND expiry_time <= NOW() + INTERVAL '1 hour'
            """
        )
        rows = cursor.fetchall()
        assert len(rows) == 0  # 70 minutes away -> no reminder yet

    # Update expiry_time to 50 minutes from now so reminder should trigger
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE bookings SET expiry_time = NOW() + INTERVAL '50 minutes' WHERE booking_id = %s",
            (booking_id,),
        )

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT booking_id
            FROM bookings
            WHERE reminder_sent = 0
              AND expiry_time IS NOT NULL
              AND expiry_time > NOW()
              AND expiry_time <= NOW() + INTERVAL '1 hour'
            """
        )
        rows = cursor.fetchall()
        assert len(rows) == 1

    # Simulate reminder_sent marking
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE bookings SET reminder_sent = 1 WHERE booking_id = %s", (booking_id,))

    # Now set expiry_time to past to simulate expiration
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE bookings SET expiry_time = NOW() - INTERVAL '1 minute' WHERE booking_id = %s",
            (booking_id,),
        )

    # Call cancel_booking and ensure status updated and offer quantity incremented
    old_offer = db.get_offer(offer_id)
    old_qty = old_offer.get("quantity")

    # Cancel booking — cancel_booking now returns reserved quantity to the offer atomically
    db.cancel_booking(booking_id)

    updated_offer = db.get_offer(offer_id)
    new_qty = updated_offer.get("quantity")

    assert new_qty == old_qty + 1
