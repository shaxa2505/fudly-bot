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

    Flow: /start → choose language → enter phone → select city → select district → done
    """

    phone = State()  # Waiting for phone number
    city = State()  # Waiting for city selection
    district = State()  # Waiting for district selection


class ChangeCity(StatesGroup):
    """
    City change flow.

    Flow: Profile → Change City → select new city → select district → done
    """

    city = State()  # Waiting for new city selection
    district = State()  # Waiting for district selection


# =============================================================================
# STORE FLOWS
# =============================================================================


class RegisterStore(StatesGroup):
    """
    Store registration flow (8 steps).

    Flow: Become Partner → city → category → name → address → location → description → phone → photo
    """

    city = State()  # Step 1: Select city
    category = State()  # Step 2: Select business category
    name = State()  # Step 3: Enter store name
    address = State()  # Step 4: Enter address
    location = State()  # Step 5: Share store location (required)
    description = State()  # Step 6: Enter description
    phone = State()  # Step 7: Enter phone (required)
    photo = State()  # Step 8: Upload photo


# =============================================================================
# OFFER FLOWS
# =============================================================================


class CreateOffer(StatesGroup):
    """
    Offer creation flow (5 steps).

    Flow: Add Offer → [store] → category → title → original price → discount price → quantity → expiry → photo → confirm
    Legacy: description/unit_type/quick_input remain for backward compatibility.
    """

    # Main flow states
    store = State()  # Optional: Select store when multiple are available
    category = State()  # Step 1: Select category
    title = State()  # Step 2: Enter title
    description = State()  # Legacy: optional description
    original_price = State()  # Step 2: Enter original price
    discount_price = State()  # Step 2: Enter discount price
    unit_type = State()  # Legacy: unit selection
    quantity = State()  # Step 3: Enter quantity
    expiry_date = State()  # Step 3: Select expiry date
    photo = State()  # Step 4: Upload photo (required)
    confirm = State()  # Step 5: Confirm & publish
    quick_input = State()  # Legacy: quick add input


class EditOffer(StatesGroup):
    """
    Offer editing flow.

    Flow: My Offers → select offer → edit field → enter value → done
    """

    browse = State()  # Browsing offers list (allows quick text search)
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

    Flow: Order Delivery → quantity → address → payment method → payment → done
    """

    offer_id = State()  # Selected offer
    quantity = State()  # Step 1: Enter quantity
    address = State()  # Step 2: Enter delivery address
    payment_method_select = State()  # Step 3: Select payment method (Click)
    payment_proof = State()  # Legacy manual payment proof (unused in current flow)


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

    Flow: Handover → courier phone → confirm → done
    """

    order_id = State()  # Order being handed over
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



