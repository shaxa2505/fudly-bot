"""
FSM States for all bot workflows.

Organized by domain:
- User: Registration, Profile
- Store: RegisterStore
- Offers: CreateOffer, EditOffer, BulkCreate
- Booking: BookOffer, ConfirmOrder, OrderDelivery
- Browse: Search, Browse, BrowseOffers
- Seller: CourierHandover

Each StatesGroup represents a complete user flow.
"""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup

# =============================================================================
# USER FLOWS
# =============================================================================


class Registration(StatesGroup):
    """
    User registration flow.

    Flow: /start → choose language → enter phone → select city → done
    """

    phone = State()  # Waiting for phone number
    city = State()  # Waiting for city selection


class ChangeCity(StatesGroup):
    """
    City change flow.

    Flow: Profile → Change City → select new city → done
    """

    city = State()  # Waiting for new city selection
    # Alias for backward compatibility
    new_city = State()


# =============================================================================
# STORE FLOWS
# =============================================================================


class RegisterStore(StatesGroup):
    """
    Store registration flow (7 steps).

    Flow: Become Partner → city → category → name → address → description → photo → submit
    """

    city = State()  # Step 1: Select city
    category = State()  # Step 2: Select business category
    name = State()  # Step 3: Enter store name
    address = State()  # Step 4: Enter address
    description = State()  # Step 5: Enter description
    phone = State()  # Step 6: Enter phone (optional)
    photo = State()  # Step 7: Upload photo


# =============================================================================
# OFFER FLOWS
# =============================================================================


class CreateOffer(StatesGroup):
    """
    Offer creation flow (8 steps).

    Flow: Add Offer → category → title → price → discount → unit → quantity → expiry → photo → done
    """

    # Main flow states
    category = State()  # Step 1: Select category
    title = State()  # Step 2: Enter title
    original_price = State()  # Step 3: Enter original price
    discount_price = State()  # Step 4: Enter/select discount
    unit_type = State()  # Step 5: Select unit type (шт/кг)
    quantity = State()  # Step 6: Enter quantity
    expiry_date = State()  # Step 7: Select expiry date
    photo = State()  # Step 8: Upload photo (optional)

    # Legacy/alternative states (for backward compatibility)
    store = State()
    prices = State()
    unit = State()
    available_from = State()
    available_until = State()


class EditOffer(StatesGroup):
    """
    Offer editing flow.

    Flow: My Offers → select offer → edit field → enter value → done
    """

    search_query = State()  # Search for offer
    offer_id = State()  # Selected offer ID
    field = State()  # Field to edit
    value = State()  # New value
    available_from = State()  # Edit availability start
    available_until = State()  # Edit availability end
    photo = State()  # Edit photo


class BulkCreate(StatesGroup):
    """
    Bulk offer creation flow (simplified).

    Flow: Bulk Import → upload file → preview → confirm → done

    Supports CSV/Excel with columns: title, price, discount, quantity, category, expiry
    """

    # Main simplified flow
    store = State()  # Select store
    file = State()  # Upload CSV/Excel file

    # Preview/confirmation
    preview = State()  # Review imported data (new)
    confirm = State()  # Confirm import (new)

    # Legacy states (for backward compatibility with existing handlers)
    count = State()
    titles = State()
    description = State()
    photos = State()
    photo = State()
    original_prices = State()
    original_price = State()
    discount_prices = State()
    discount_price = State()
    quantities = State()
    quantity = State()
    available_from = State()
    available_untils = State()
    available_until = State()
    categories = State()
    units = State()


# =============================================================================
# BOOKING FLOWS
# =============================================================================


class BookOffer(StatesGroup):
    """
    Offer booking flow (pickup or delivery choice).

    Flow: Book → quantity → delivery choice → [address] → confirm → done
    """

    quantity = State()  # Step 1: Enter quantity
    delivery_choice = State()  # Step 2: Pickup or delivery?
    delivery_address = State()  # Step 3a: Enter delivery address (if delivery)
    pickup_time = State()  # Step 3b: Select pickup time (if pickup)
    delivery_receipt = State()  # Step 4: Upload payment receipt (if delivery)


class OrderDelivery(StatesGroup):
    """
    Delivery order flow.

    Flow: Order Delivery → quantity → address → payment method → payment → upload receipt → done
    """

    offer_id = State()  # Selected offer
    quantity = State()  # Step 1: Enter quantity
    address = State()  # Step 2: Enter delivery address
    payment_method_select = State()  # Step 3: Select payment method (click/card)
    payment_proof = State()  # Step 4: Upload payment screenshot (for card)


class ConfirmOrder(StatesGroup):
    """
    Order confirmation flow (for sellers).

    Flow: Scan QR / Enter code → verify → confirm → done
    """

    offer_id = State()  # Offer being confirmed
    booking_code = State()  # Enter booking code
    confirmation = State()  # Confirm completion


class RateBooking(StatesGroup):
    """
    Booking rating flow.

    Flow: Rate (1-5 stars) → [optional text review] → done
    """

    booking_id = State()  # Booking being rated
    rating = State()  # Star rating (1-5)
    review_text = State()  # Optional text review


class CourierHandover(StatesGroup):
    """
    Courier handover flow (seller → courier).

    Flow: Handover → courier name → courier phone → confirm → done
    """

    order_id = State()  # Order being handed over
    courier_name = State()  # Enter courier name
    courier_phone = State()  # Enter courier phone


# =============================================================================
# BROWSE/SEARCH FLOWS
# =============================================================================


class Search(StatesGroup):
    """
    Search flow.

    Flow: Search → enter query → show results
    """

    query = State()  # Waiting for search query


class Browse(StatesGroup):
    """
    Browsing flow states.

    Flow: Browse → select store/category → view items
    """

    viewing_store = State()  # Viewing a specific store
    viewing_category = State()  # Viewing a category


class BrowseOffers(StatesGroup):
    """
    Numbered offer list browsing.

    Flow: Hot Offers → show list → select by number → view details
    """

    offer_list = State()  # List of offer IDs in current view
    store_list = State()  # List of store IDs in current view
    business_type = State()  # Selected business type filter
    category = State()  # Selected category filter
    filter = State()  # Active filter settings
