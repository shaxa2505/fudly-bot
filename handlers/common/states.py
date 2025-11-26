"""FSM States for all bot workflows."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    """User registration flow states."""

    phone = State()
    city = State()


class RegisterStore(StatesGroup):
    """Store registration flow states."""

    city = State()
    category = State()
    name = State()
    address = State()
    description = State()
    phone = State()
    photo = State()


class CreateOffer(StatesGroup):
    """Offer creation flow states."""

    store = State()
    title = State()
    photo = State()
    prices = State()
    original_price = State()
    discount_price = State()
    quantity = State()
    unit = State()
    category = State()
    available_from = State()
    expiry_date = State()
    available_until = State()


class BulkCreate(StatesGroup):
    """Bulk offer creation flow states."""

    store = State()
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
    file = State()


class ChangeCity(StatesGroup):
    """City change flow states."""

    new_city = State()
    city = State()


class EditOffer(StatesGroup):
    """Offer editing flow states."""

    offer_id = State()
    field = State()
    value = State()
    available_from = State()
    available_until = State()
    search_query = State()  # For seller's offer search


class ConfirmOrder(StatesGroup):
    """Order confirmation flow states."""

    offer_id = State()
    booking_code = State()
    confirmation = State()


class BookOffer(StatesGroup):
    """Offer booking flow states."""

    quantity = State()
    delivery_choice = State()
    delivery_address = State()
    delivery_receipt = State()
    pickup_time = State()


class BrowseOffers(StatesGroup):
    """States for browsing numbered offer lists."""

    offer_list = State()
    store_list = State()
    business_type = State()
    category = State()
    filter = State()


class OrderDelivery(StatesGroup):
    """Delivery order flow states."""

    offer_id = State()
    quantity = State()
    address = State()
    payment_method = State()
    payment_proof = State()


class CourierHandover(StatesGroup):
    """Courier handover flow states (seller to taxi/courier)."""

    order_id = State()
    courier_name = State()
    courier_phone = State()


class Search(StatesGroup):
    """Search flow states."""

    query = State()


class Browse(StatesGroup):
    """Browsing flow states."""

    viewing_store = State()
    viewing_category = State()
