"""Order-related message builders for bot handlers."""
from __future__ import annotations

from html import escape as esc

from localization import get_text


def build_admin_payment_confirmed_caption(lang: str, admin_name: str) -> str:
    return get_text(lang, "admin_payment_confirmed_caption", admin_name=esc(admin_name))


def build_admin_payment_rejected_caption(lang: str, admin_name: str) -> str:
    return get_text(lang, "admin_payment_rejected_caption", admin_name=esc(admin_name))


def build_customer_payment_confirmed(lang: str, order_id: int, store_name: str) -> str:
    return get_text(
        lang,
        "admin_payment_confirmed_customer",
        order_id=str(order_id),
        store_name=esc(store_name),
    )


def build_customer_payment_rejected(lang: str, order_id: int) -> str:
    return get_text(
        lang,
        "admin_payment_rejected_customer",
        order_id=str(order_id),
    )


def build_seller_payment_confirmed(lang: str) -> tuple[str, str]:
    return (
        get_text(lang, "seller_payment_confirmed"),
        get_text(lang, "seller_payment_next_step"),
    )


def build_seller_payment_rejected(lang: str) -> str:
    return get_text(lang, "seller_payment_rejected")
