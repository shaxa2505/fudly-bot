"""
Payment integrations for Uzbekistan payment systems.

Supports:
- Click (https://click.uz)
- Payme (https://payme.uz)

Supports both:
- Platform-level credentials (env vars)
- Per-store credentials (database)

To enable platform payments, set environment variables:
- CLICK_MERCHANT_ID
- CLICK_SERVICE_ID
- CLICK_SECRET_KEY
- PAYME_MERCHANT_ID
- PAYME_SECRET_KEY
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from datetime import datetime
from enum import Enum
from typing import Any
from urllib.parse import urlencode

import aiohttp

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class PaymentProvider(Enum):
    """Supported payment providers."""

    CLICK = "click"
    PAYME = "payme"
    CARD = "card"  # Manual card transfer (default)


class PaymentStatus(Enum):
    """Payment statuses."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class StorePaymentCredentials:
    """Payment credentials for a specific store."""

    def __init__(
        self,
        provider: str,
        merchant_id: str,
        secret_key: str,
        service_id: str | None = None,
        merchant_user_id: str | None = None,
    ):
        self.provider = provider
        self.merchant_id = merchant_id
        self.secret_key = secret_key
        self.service_id = service_id  # Only for Click
        self.merchant_user_id = merchant_user_id  # Only for Click API Auth


class PaymentService:
    """Service for handling online payments."""

    def __init__(self):
        # Platform-level Click credentials (fallback)
        self.click_merchant_id = os.getenv("CLICK_MERCHANT_ID")
        self.click_service_id = os.getenv("CLICK_SERVICE_ID")
        self.click_secret_key = os.getenv("CLICK_SECRET_KEY")
        self.click_merchant_user_id = os.getenv("CLICK_MERCHANT_USER_ID")

        # Platform-level Payme credentials (fallback)
        self.payme_merchant_id = os.getenv("PAYME_MERCHANT_ID")
        self.payme_secret_key = os.getenv("PAYME_SECRET_KEY")

        # Base URLs
        self.click_api_url = "https://api.click.uz/v2/merchant"
        self.payme_checkout_url = "https://checkout.paycom.uz"

        # Database reference (set later)
        self._db = None

    def set_database(self, db):
        """Set database reference for store-level credentials."""
        self._db = db

    @property
    def click_enabled(self) -> bool:
        """Check if platform-level Click integration is configured."""
        return all([self.click_merchant_id, self.click_service_id, self.click_secret_key])

    @property
    def payme_enabled(self) -> bool:
        """Check if platform-level Payme integration is configured."""
        return all([self.payme_merchant_id, self.payme_secret_key])

    def get_store_credentials(
        self, store_id: int | None, provider: str
    ) -> StorePaymentCredentials | None:
        """Get payment credentials for a specific store."""
        if not self._db or not store_id:
            return None

        try:
            integration = self._db.get_store_payment_integration(store_id, provider)
            if integration:
                return StorePaymentCredentials(
                    provider=integration["provider"],
                    merchant_id=integration["merchant_id"],
                    secret_key=integration["secret_key"],
                    service_id=integration.get("service_id"),
                    merchant_user_id=integration.get("merchant_user_id"),
                )
        except Exception as e:
            logger.error(f"Error getting store credentials: {e}")

        return None

    def get_available_providers(self, store_id: int = None) -> list[str]:
        """Get list of available payment providers."""
        providers = ["card"]  # Card is always available

        # Check store-specific providers first
        if store_id and self._db:
            try:
                integrations = self._db.get_store_payment_integrations(store_id)
                for integration in integrations:
                    if integration["provider"] not in providers:
                        providers.append(integration["provider"])
            except Exception as e:
                logger.error(f"Error checking store providers: {e}")

        # Fallback to platform providers
        if self.click_enabled and "click" not in providers:
            providers.append("click")
        if self.payme_enabled and "payme" not in providers:
            providers.append("payme")

        return providers

    def get_available_providers_for_store(self, store_id: int) -> list[dict]:
        """Get detailed info about available providers for a store."""
        result = [{"provider": "card", "name": "Karta orqali", "is_store_level": False}]

        if self._db:
            try:
                integrations = self._db.get_store_payment_integrations(store_id)
                for integration in integrations:
                    result.append(
                        {
                            "provider": integration["provider"],
                            "name": "Click" if integration["provider"] == "click" else "Payme",
                            "is_store_level": True,
                            "merchant_id": integration["merchant_id"][:8] + "...",  # Masked
                        }
                    )
            except Exception as e:
                logger.error(f"Error checking store providers: {e}")

        # Add platform providers if store doesn't have own
        store_providers = [p["provider"] for p in result]
        if self.click_enabled and "click" not in store_providers:
            result.append(
                {"provider": "click", "name": "Click (platform)", "is_store_level": False}
            )
        if self.payme_enabled and "payme" not in store_providers:
            result.append(
                {"provider": "payme", "name": "Payme (platform)", "is_store_level": False}
            )

        return result

    # ===================== CLICK INTEGRATION =====================

    def generate_click_url(
        self,
        order_id: int,
        amount: int,
        return_url: str | None = None,
        user_id: int | None = None,
        store_id: int | None = None,
    ) -> str:
        """
        Generate Click payment URL.

        Args:
            order_id: Unique order/booking ID
            amount: Amount in UZS (tiyins will be added)
            return_url: URL to redirect after payment
            user_id: Telegram user ID for tracking
            store_id: Store ID to use store-specific credentials

        Returns:
            Click payment URL
        """
        # Try store credentials first
        creds = None
        if store_id:
            creds = self.get_store_credentials(store_id, "click")

        merchant_id = creds.merchant_id if creds else self.click_merchant_id
        service_id = creds.service_id if creds else self.click_service_id

        if not merchant_id or not service_id:
            raise ValueError("Click integration not configured")

        params = {
            "merchant_id": merchant_id,
            "service_id": service_id,
            "amount": str(amount),
            "transaction_param": str(order_id),
        }

        if return_url:
            params["return_url"] = return_url

        if user_id:
            params["merchant_user_id"] = str(user_id)

        return f"https://my.click.uz/services/pay?{urlencode(params)}"

    def verify_click_signature(
        self,
        click_trans_id: str,
        service_id: str,
        merchant_trans_id: str,
        amount: str,
        action: str,
        sign_time: str,
        sign_string: str,
        merchant_prepare_id: str | None = None,
        store_id: int = None,
    ) -> bool:
        """
        Verify Click callback signature.

        Returns True if signature is valid.
        """
        # Try store credentials first
        secret_key = None
        if store_id:
            creds = self.get_store_credentials(store_id, "click")
            if creds:
                secret_key = creds.secret_key

        if not secret_key:
            secret_key = self.click_secret_key

        if not secret_key:
            return False

        # Generate expected signature
        if merchant_prepare_id:
            data = (
                f"{click_trans_id}{service_id}{secret_key}{merchant_trans_id}"
                f"{merchant_prepare_id}{amount}{action}{sign_time}"
            )
        else:
            data = (
                f"{click_trans_id}{service_id}{secret_key}{merchant_trans_id}"
                f"{amount}{action}{sign_time}"
            )
        expected_sign = hashlib.md5(data.encode()).hexdigest()

        return expected_sign == str(sign_string).lower()

    @staticmethod
    def _env_flag(name: str, default: bool = False) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _amount_to_tiyin(amount: Any) -> int:
        """Convert amount to tiyin based on PRICE_STORAGE_UNIT env."""
        price_unit = os.getenv("PRICE_STORAGE_UNIT", "sums").strip().lower()
        try:
            value = float(amount or 0)
        except (TypeError, ValueError):
            return 0
        if price_unit in {"kopeks", "tiyin"}:
            return int(round(value))
        return int(round(value * 100))

    @staticmethod
    def _build_click_auth_header(merchant_user_id: str, secret_key: str) -> str:
        """Build Click Auth header: merchant_user_id:sha1(timestamp+secret_key):timestamp."""
        ts = int(time.time())
        digest = hashlib.sha1(f"{ts}{secret_key}".encode()).hexdigest()
        return f"{merchant_user_id}:{digest}:{ts}"

    @staticmethod
    def _normalize_click_amount(amount: Any) -> int:
        """Normalize Click amount (sums) to match stored order units."""
        price_unit = os.getenv("PRICE_STORAGE_UNIT", "sums").strip().lower()
        try:
            value = float(amount)
        except (TypeError, ValueError):
            return 0
        if price_unit in {"kopeks", "tiyin"}:
            return int(round(value * 100))
        return int(round(value))

    def _amounts_match(self, order_total: Any, click_amount: Any) -> bool:
        if order_total is None:
            return False
        expected = self._safe_int(order_total, 0)
        received = self._normalize_click_amount(click_amount)
        return expected == received

    @staticmethod
    def _click_response(
        *,
        click_trans_id: str,
        merchant_trans_id: str,
        error: int,
        error_note: str,
        merchant_prepare_id: str | None = None,
        merchant_confirm_id: str | None = None,
    ) -> dict:
        payload = {
            "click_trans_id": click_trans_id,
            "merchant_trans_id": merchant_trans_id,
            "error": int(error),
            "error_note": error_note,
        }
        if merchant_prepare_id is not None:
            payload["merchant_prepare_id"] = merchant_prepare_id
        if merchant_confirm_id is not None:
            payload["merchant_confirm_id"] = merchant_confirm_id
        return payload

    def _get_click_fiscal_config(self) -> dict[str, Any]:
        return {
            "enabled": self._env_flag("CLICK_FISCALIZATION_ENABLED", default=True),
            "items_mode": os.getenv("CLICK_FISCAL_ITEMS_MODE", "single").strip().lower(),
            "item_name": os.getenv("CLICK_FISCAL_ITEM_NAME", "Fudly service").strip()
            or "Fudly service",
            "item_unit_label": os.getenv("CLICK_FISCAL_ITEM_UNIT_LABEL", "unit").strip()
            or "unit",
            "spic": os.getenv("CLICK_FISCAL_SPIC"),
            "units_code": os.getenv("CLICK_FISCAL_UNITS_CODE"),
            "package_code": os.getenv("CLICK_FISCAL_PACKAGE_CODE", "DEFAULT"),
            "vat_percent": self._safe_int(os.getenv("CLICK_FISCAL_VAT_PERCENT", "0"), 0),
            "tin": os.getenv("CLICK_FISCAL_TIN"),
            "pinfl": os.getenv("CLICK_FISCAL_PINFL"),
            "fetch_qrcode": self._env_flag("CLICK_FISCAL_FETCH_QRCODE", default=True),
        }

    @staticmethod
    def _format_item_name(base_name: str, unit_label: str) -> str:
        name = base_name.strip()
        if unit_label:
            if not name.endswith(unit_label):
                name = f"{name} {unit_label}".strip()
        if len(name) > 63:
            name = name[:63]
        return name

    def _collect_order_items(self, order: Any) -> list[dict[str, Any]]:
        cart_items = None
        if isinstance(order, dict):
            cart_items = order.get("cart_items")
        else:
            cart_items = getattr(order, "cart_items", None)

        if cart_items:
            if isinstance(cart_items, str):
                try:
                    return json.loads(cart_items)
                except json.JSONDecodeError:
                    return []
            if isinstance(cart_items, list):
                return cart_items

        # Fallback to single-offer order
        offer_id = order.get("offer_id") if isinstance(order, dict) else getattr(order, "offer_id", None)
        if offer_id:
            quantity = (
                order.get("quantity", 1) if isinstance(order, dict) else getattr(order, "quantity", 1)
            )
            return [
                {"offer_id": offer_id, "quantity": quantity, "price": None, "title": None}
            ]

        return []

    def _get_click_order(self, merchant_trans_id: str) -> tuple[Any | None, int | None]:
        if not self._db or not hasattr(self._db, "get_order"):
            return (None, None)
        try:
            order_id = int(str(merchant_trans_id))
        except (TypeError, ValueError):
            return (None, None)
        try:
            order = self._db.get_order(order_id)
        except Exception:
            order = None
        return (order, order_id if order else None)

    def _resolve_click_credentials(self, order: Any, service_id: str | None) -> tuple[str | None, str | None]:
        """Resolve Click service_id and secret_key based on order/store."""
        store_id = None
        if isinstance(order, dict):
            store_id = order.get("store_id")
        else:
            store_id = getattr(order, "store_id", None)
        creds = None
        if store_id:
            creds = self.get_store_credentials(int(store_id), "click")
        expected_service_id = creds.service_id if creds else self.click_service_id
        secret_key = creds.secret_key if creds else self.click_secret_key
        if service_id and expected_service_id and str(service_id) != str(expected_service_id):
            return (None, None)
        return (expected_service_id, secret_key)

    def _build_click_items_payload(
        self, order: Any, config: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], int]:
        """Build Click fiscal items and return (items, received_card_tiyin)."""
        if not self._db:
            return ([], 0)

        spic = config.get("spic")
        units_code_raw = config.get("units_code")
        package_code = config.get("package_code") or "DEFAULT"
        vat_percent = int(config.get("vat_percent") or 0)

        if not spic or not units_code_raw:
            logger.warning("Click fiscalization config missing SPIC or Units code")
            return ([], 0)

        units_code = self._safe_int(units_code_raw, 0)
        if units_code <= 0:
            logger.warning("Click fiscalization config has invalid Units code")
            return ([], 0)

        items_mode = config.get("items_mode") or "single"
        order_items = self._collect_order_items(order)

        original_total = 0
        discounted_total = 0
        per_item_payloads: list[dict[str, Any]] = []

        for item in order_items:
            offer_id = self._safe_int(item.get("offer_id"))
            quantity = max(self._safe_int(item.get("quantity", 1), 1), 1)
            item_price = self._safe_int(item.get("price", 0), 0)
            title = (item.get("title") or "").strip()

            offer = None
            if offer_id and hasattr(self._db, "get_offer"):
                try:
                    offer = self._db.get_offer(int(offer_id))
                except Exception:
                    offer = None

            if not title and offer:
                title = offer.get("title", "") if isinstance(offer, dict) else ""

            unit_label = None
            if offer:
                unit_label = offer.get("unit") if isinstance(offer, dict) else getattr(offer, "unit", None)
            if not unit_label:
                unit_label = config.get("item_unit_label") or "unit"

            original_price = 0
            discounted_price = 0
            if offer and isinstance(offer, dict):
                original_price = self._safe_int(offer.get("original_price"), 0)
                discounted_price = self._safe_int(offer.get("discount_price"), 0)
            if not discounted_price:
                discounted_price = item_price
            if not original_price:
                original_price = discounted_price or item_price

            original_total += original_price * quantity
            discounted_total += discounted_price * quantity

            if items_mode == "per_item":
                name = self._format_item_name(title or config.get("item_name", "Item"), unit_label)
                price_total = original_price * quantity
                discount_total = max(original_price - discounted_price, 0) * quantity
                vat_amount = int(round(price_total * vat_percent / 100)) if vat_percent else 0
                payload = {
                    "Name": name,
                    "SPIC": str(spic),
                    "Units": int(units_code),
                    "PackageCode": str(package_code),
                    "GoodPrice": int(original_price),
                    "Price": int(price_total),
                    "Amount": int(quantity),
                    "VAT": int(vat_amount),
                    "VATPercent": int(vat_percent),
                }
                if discount_total > 0:
                    payload["Discount"] = int(discount_total)
                per_item_payloads.append(payload)

        order_total = None
        if isinstance(order, dict):
            order_total = order.get("total_price")
        else:
            order_total = getattr(order, "total_price", None)

        if order_total is not None:
            order_total_int = self._safe_int(order_total, 0)
            if order_total_int > 0:
                discounted_total = order_total_int
                if original_total < discounted_total:
                    original_total = discounted_total

        if discounted_total <= 0:
            return ([], 0)

        if items_mode == "per_item" and per_item_payloads:
            items_payload = per_item_payloads
        else:
            name = self._format_item_name(
                config.get("item_name", "Fudly service"), config.get("item_unit_label", "unit")
            )
            discount_total = max(original_total - discounted_total, 0)
            vat_amount = int(round(original_total * vat_percent / 100)) if vat_percent else 0
            items_payload = [
                {
                    "Name": name,
                    "SPIC": str(spic),
                    "Units": int(units_code),
                    "PackageCode": str(package_code),
                    "GoodPrice": int(original_total),
                    "Price": int(original_total),
                    "Amount": 1,
                    "VAT": int(vat_amount),
                    "VATPercent": int(vat_percent),
                    "Discount": int(discount_total) if discount_total > 0 else 0,
                }
            ]

        # Convert amounts to tiyin
        for payload in items_payload:
            for field in ("GoodPrice", "Price", "Amount", "VAT", "VATPercent", "Discount"):
                if field not in payload:
                    continue
                if field in {"Amount", "VATPercent"}:
                    payload[field] = int(payload[field])
                else:
                    payload[field] = self._amount_to_tiyin(payload[field])

        return (items_payload, self._amount_to_tiyin(discounted_total))

    async def submit_click_fiscal_items(
        self,
        order_id: int,
        payment_id: str,
        service_id: str | None = None,
    ) -> None:
        """Submit fiscalized items to Click (OFD)."""
        config = self._get_click_fiscal_config()
        if not config.get("enabled"):
            return

        if not self._db or not hasattr(self._db, "get_order"):
            logger.warning("Click fiscalization skipped: database not available")
            return

        order = self._db.get_order(int(order_id))
        if not order:
            logger.warning("Click fiscalization skipped: order %s not found", order_id)
            return

        if hasattr(self._db, "get_click_fiscalization"):
            try:
                existing = self._db.get_click_fiscalization(int(order_id), str(payment_id))
                if existing and str(existing.get("status", "")).lower() == "success":
                    return
            except Exception:
                pass

        store_id = order.get("store_id") if isinstance(order, dict) else getattr(order, "store_id", None)
        creds = None
        if store_id:
            creds = self.get_store_credentials(int(store_id), "click")

        if creds and creds.merchant_user_id:
            merchant_user_id = creds.merchant_user_id
            secret_key = creds.secret_key
        else:
            merchant_user_id = self.click_merchant_user_id
            secret_key = self.click_secret_key
        service_id_val = service_id or (creds.service_id if creds else self.click_service_id)

        if not merchant_user_id or not secret_key or not service_id_val:
            logger.warning("Click fiscalization skipped: missing merchant_user_id/secret_key/service_id")
            return

        if not config.get("spic") or not config.get("units_code") or not (
            config.get("pinfl") or config.get("tin")
        ):
            logger.warning("Click fiscalization skipped: missing SPIC/Units/TIN/PINFL")
            return

        items_payload, received_card = self._build_click_items_payload(order, config)
        if not items_payload:
            logger.warning("Click fiscalization skipped: no items payload")
            return

        commission_info = {}
        pinfl = config.get("pinfl")
        tin = config.get("tin")
        if pinfl:
            commission_info["PINFL"] = str(pinfl)
        elif tin:
            commission_info["TIN"] = str(tin)

        if not commission_info:
            logger.warning("Click fiscalization skipped: missing CommissionInfo (TIN/PINFL)")
            return

        for item in items_payload:
            item["CommissionInfo"] = commission_info

        payment_id_val = self._safe_int(payment_id, 0)
        if payment_id_val <= 0:
            payment_id_val = str(payment_id)

        payload = {
            "service_id": self._safe_int(service_id_val, 0),
            "payment_id": payment_id_val,
            "items": items_payload,
            "received_ecash": 0,
            "received_cash": 0,
            "received_card": int(received_card),
        }

        if hasattr(self._db, "upsert_click_fiscalization"):
            try:
                self._db.upsert_click_fiscalization(
                    order_id=int(order_id),
                    payment_id=str(payment_id),
                    service_id=str(service_id_val),
                    status="pending",
                    request_payload=payload,
                )
            except Exception:
                pass

        auth_header = self._build_click_auth_header(merchant_user_id, secret_key)
        url = f"{self.click_api_url}/payment/ofd_data/submit_items"
        timeout = aiohttp.ClientTimeout(total=15)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    url,
                    json=payload,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "Auth": auth_header,
                    },
                ) as resp:
                    text = await resp.text()
                    try:
                        data = json.loads(text) if text else {}
                    except json.JSONDecodeError:
                        data = {"error_code": -1, "error_note": text}

                    error_code = self._safe_int(data.get("error_code", -1), -1)
                    status = "success" if error_code == 0 else "failed"

                    if hasattr(self._db, "upsert_click_fiscalization"):
                        try:
                            self._db.upsert_click_fiscalization(
                                order_id=int(order_id),
                                payment_id=str(payment_id),
                                service_id=str(service_id_val),
                                status=status,
                                error_code=error_code,
                                error_note=str(data.get("error_note", "")),
                                response_payload=data,
                            )
                        except Exception:
                            pass

                    if error_code == 0 and config.get("fetch_qrcode"):
                        await self.fetch_click_fiscal_data(
                            order_id=int(order_id),
                            payment_id=str(payment_id),
                            service_id=str(service_id_val),
                            merchant_user_id=merchant_user_id,
                            secret_key=secret_key,
                        )
        except Exception as e:
            logger.warning(f"Click fiscalization submit_items failed: {e}")

    async def fetch_click_fiscal_data(
        self,
        order_id: int,
        payment_id: str,
        service_id: str,
        merchant_user_id: str,
        secret_key: str,
    ) -> None:
        """Fetch fiscal QR data from Click."""
        auth_header = self._build_click_auth_header(merchant_user_id, secret_key)
        url = f"{self.click_api_url}/payment/ofd_data/{service_id}/{payment_id}"
        timeout = aiohttp.ClientTimeout(total=15)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    url,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "Auth": auth_header,
                    },
                ) as resp:
                    text = await resp.text()
                    try:
                        data = json.loads(text) if text else {}
                    except json.JSONDecodeError:
                        data = {}

                    qr_url = data.get("qrCodeURL")
                    if qr_url and hasattr(self._db, "upsert_click_fiscalization"):
                        try:
                            self._db.upsert_click_fiscalization(
                                order_id=int(order_id),
                                payment_id=str(payment_id),
                                service_id=str(service_id),
                                status="success",
                                qr_code_url=str(qr_url),
                                response_payload=data,
                            )
                        except Exception:
                            pass
        except Exception as e:
            logger.warning(f"Click fiscalization fetch failed: {e}")

    async def process_click_prepare(
        self,
        click_trans_id: str,
        click_paydoc_id: str | None,
        merchant_trans_id: str,
        amount: Any,
        action: str,
        sign_time: str,
        sign_string: str,
        service_id: str | None = None,
    ) -> dict:
        """
        Process Click PREPARE request.

        Returns response dict for Click.
        """
        if str(action) != "0":
            return self._click_response(
                click_trans_id=click_trans_id,
                merchant_trans_id=merchant_trans_id,
                merchant_prepare_id=merchant_trans_id,
                error=-3,
                error_note="Action not found",
            )

        order, order_id = self._get_click_order(merchant_trans_id)
        if not order:
            return self._click_response(
                click_trans_id=click_trans_id,
                merchant_trans_id=merchant_trans_id,
                merchant_prepare_id=merchant_trans_id,
                error=-5,
                error_note="User does not exist",
            )

        expected_service_id, _ = self._resolve_click_credentials(order, service_id)
        if not expected_service_id:
            return self._click_response(
                click_trans_id=click_trans_id,
                merchant_trans_id=merchant_trans_id,
                merchant_prepare_id=merchant_trans_id,
                error=-8,
                error_note="Error in request from click",
            )

        # Verify signature
        store_id = (
            order.get("store_id") if isinstance(order, dict) else getattr(order, "store_id", None)
        )
        if not self.verify_click_signature(
            click_trans_id,
            expected_service_id,
            merchant_trans_id,
            str(amount),
            action,
            sign_time,
            sign_string,
            store_id=store_id,
        ):
            return self._click_response(
                click_trans_id=click_trans_id,
                merchant_trans_id=merchant_trans_id,
                merchant_prepare_id=merchant_trans_id,
                error=-1,
                error_note="SIGN CHECK FAILED!",
            )

        order_status = str(
            order.get("order_status") if isinstance(order, dict) else getattr(order, "order_status", "")
        ).lower()
        payment_status = str(
            order.get("payment_status") if isinstance(order, dict) else getattr(order, "payment_status", "")
        ).lower()
        if payment_status == "confirmed":
            return self._click_response(
                click_trans_id=click_trans_id,
                merchant_trans_id=merchant_trans_id,
                merchant_prepare_id=merchant_trans_id,
                error=-4,
                error_note="Already paid",
            )
        if order_status in ("cancelled", "rejected"):
            return self._click_response(
                click_trans_id=click_trans_id,
                merchant_trans_id=merchant_trans_id,
                merchant_prepare_id=merchant_trans_id,
                error=-5,
                error_note="Order cancelled",
            )

        order_total = order.get("total_price") if isinstance(order, dict) else getattr(order, "total_price", None)
        if not self._amounts_match(order_total, amount):
            return self._click_response(
                click_trans_id=click_trans_id,
                merchant_trans_id=merchant_trans_id,
                merchant_prepare_id=merchant_trans_id,
                error=-2,
                error_note="Incorrect parameter amount",
            )

        tx = None
        if self._db and hasattr(self._db, "get_click_transaction"):
            try:
                tx = self._db.get_click_transaction(int(click_trans_id))
            except Exception:
                tx = None

        if tx:
            status = str(tx.get("status", "")).lower()
            merchant_prepare_id = str(tx.get("merchant_prepare_id") or merchant_trans_id)
            if status == "confirmed":
                return self._click_response(
                    click_trans_id=click_trans_id,
                    merchant_trans_id=merchant_trans_id,
                    merchant_prepare_id=merchant_prepare_id,
                    error=-4,
                    error_note="Already paid",
                )
            if status == "cancelled":
                return self._click_response(
                    click_trans_id=click_trans_id,
                    merchant_trans_id=merchant_trans_id,
                    merchant_prepare_id=merchant_prepare_id,
                    error=-9,
                    error_note="Transaction cancelled",
                )
            return self._click_response(
                click_trans_id=click_trans_id,
                merchant_trans_id=merchant_trans_id,
                merchant_prepare_id=merchant_prepare_id,
                error=0,
                error_note="Success",
            )

        if self._db and hasattr(self._db, "upsert_click_transaction") and order_id:
            try:
                self._db.upsert_click_transaction(
                    click_trans_id=int(click_trans_id),
                    click_paydoc_id=str(click_paydoc_id) if click_paydoc_id else None,
                    merchant_trans_id=str(merchant_trans_id),
                    merchant_prepare_id=str(merchant_trans_id),
                    service_id=str(expected_service_id),
                    amount=str(amount),
                    status="prepared",
                )
            except Exception:
                pass

        return self._click_response(
            click_trans_id=click_trans_id,
            merchant_trans_id=merchant_trans_id,
            merchant_prepare_id=merchant_trans_id,
            error=0,
            error_note="Success",
        )

    async def process_click_complete(
        self,
        click_trans_id: str,
        click_paydoc_id: str | None,
        merchant_trans_id: str,
        merchant_prepare_id: str,
        amount: Any,
        action: str,
        sign_time: str,
        sign_string: str,
        error: int,
        service_id: str | None = None,
    ) -> dict:
        """
        Process Click COMPLETE request.

        Returns response dict for Click.
        """
        if str(action) != "1":
            return self._click_response(
                click_trans_id=click_trans_id,
                merchant_trans_id=merchant_trans_id,
                merchant_confirm_id=merchant_trans_id,
                error=-3,
                error_note="Action not found",
            )

        order, order_id = self._get_click_order(merchant_trans_id)
        if not order:
            return self._click_response(
                click_trans_id=click_trans_id,
                merchant_trans_id=merchant_trans_id,
                merchant_confirm_id=merchant_trans_id,
                error=-5,
                error_note="User does not exist",
            )

        expected_service_id, _ = self._resolve_click_credentials(order, service_id)
        if not expected_service_id:
            return self._click_response(
                click_trans_id=click_trans_id,
                merchant_trans_id=merchant_trans_id,
                merchant_confirm_id=merchant_trans_id,
                error=-8,
                error_note="Error in request from click",
            )

        # Verify signature (includes merchant_prepare_id)
        store_id = (
            order.get("store_id") if isinstance(order, dict) else getattr(order, "store_id", None)
        )
        if not self.verify_click_signature(
            click_trans_id,
            expected_service_id,
            merchant_trans_id,
            str(amount),
            action,
            sign_time,
            sign_string,
            merchant_prepare_id=str(merchant_prepare_id),
            store_id=store_id,
        ):
            return self._click_response(
                click_trans_id=click_trans_id,
                merchant_trans_id=merchant_trans_id,
                merchant_confirm_id=merchant_trans_id,
                error=-1,
                error_note="SIGN CHECK FAILED!",
            )

        order_total = order.get("total_price") if isinstance(order, dict) else getattr(order, "total_price", None)
        if not self._amounts_match(order_total, amount):
            return self._click_response(
                click_trans_id=click_trans_id,
                merchant_trans_id=merchant_trans_id,
                merchant_confirm_id=merchant_trans_id,
                error=-2,
                error_note="Incorrect parameter amount",
            )

        order_status = str(
            order.get("order_status") if isinstance(order, dict) else getattr(order, "order_status", "")
        ).lower()
        if order_status in ("cancelled", "rejected"):
            return self._click_response(
                click_trans_id=click_trans_id,
                merchant_trans_id=merchant_trans_id,
                merchant_confirm_id=merchant_trans_id,
                error=-9,
                error_note="Transaction cancelled",
            )

        tx = None
        if self._db and hasattr(self._db, "get_click_transaction"):
            try:
                tx = self._db.get_click_transaction(int(click_trans_id))
            except Exception:
                tx = None

        if not tx:
            if error != 0:
                return self._click_response(
                    click_trans_id=click_trans_id,
                    merchant_trans_id=merchant_trans_id,
                    merchant_confirm_id=merchant_trans_id,
                    error=-9,
                    error_note="Transaction cancelled",
                )
            if str(merchant_prepare_id) != str(merchant_trans_id):
                return self._click_response(
                    click_trans_id=click_trans_id,
                    merchant_trans_id=merchant_trans_id,
                    merchant_confirm_id=merchant_trans_id,
                    error=-6,
                    error_note="Transaction does not exist",
                )
            # Allow confirm even if Prepare wasn't recorded (e.g. retry/timeout scenarios)
            if self._db and hasattr(self._db, "upsert_click_transaction"):
                try:
                    self._db.upsert_click_transaction(
                        click_trans_id=int(click_trans_id),
                        click_paydoc_id=str(click_paydoc_id) if click_paydoc_id else None,
                        merchant_trans_id=str(merchant_trans_id),
                        merchant_prepare_id=str(merchant_prepare_id),
                        service_id=str(expected_service_id),
                        amount=str(amount),
                        status="confirmed",
                    )
                except Exception:
                    pass
            tx = {"status": "confirmed"}

        stored_prepare_id = str(tx.get("merchant_prepare_id") or "")
        if stored_prepare_id and str(merchant_prepare_id) != stored_prepare_id:
            return self._click_response(
                click_trans_id=click_trans_id,
                merchant_trans_id=merchant_trans_id,
                merchant_confirm_id=merchant_trans_id,
                error=-6,
                error_note="Transaction does not exist",
            )

        tx_status = str(tx.get("status", "")).lower()
        if tx_status == "confirmed":
            return self._click_response(
                click_trans_id=click_trans_id,
                merchant_trans_id=merchant_trans_id,
                merchant_confirm_id=merchant_trans_id,
                error=-4,
                error_note="Already paid",
            )
        if tx_status == "cancelled":
            return self._click_response(
                click_trans_id=click_trans_id,
                merchant_trans_id=merchant_trans_id,
                merchant_confirm_id=merchant_trans_id,
                error=-9,
                error_note="Transaction cancelled",
            )

        if error != 0:
            if self._db and hasattr(self._db, "upsert_click_transaction"):
                try:
                    self._db.upsert_click_transaction(
                        click_trans_id=int(click_trans_id),
                        click_paydoc_id=str(click_paydoc_id) if click_paydoc_id else None,
                        merchant_trans_id=str(merchant_trans_id),
                        merchant_prepare_id=str(merchant_prepare_id),
                        service_id=str(expected_service_id),
                        amount=str(amount),
                        status="cancelled",
                        error_code=error,
                        error_note="Cancelled by Click",
                    )
                except Exception:
                    pass
            if order_id and self._db and hasattr(self._db, "update_payment_status"):
                try:
                    self._db.update_payment_status(int(order_id), "rejected")
                except Exception:
                    pass
            if order_id:
                try:
                    from app.services.unified_order_service import get_unified_order_service

                    order_service = get_unified_order_service()
                    if order_service:
                        await order_service.cancel_order(int(order_id), "order")
                    elif self._db and hasattr(self._db, "update_order_status"):
                        self._db.update_order_status(int(order_id), "cancelled")
                except Exception:
                    pass
            return self._click_response(
                click_trans_id=click_trans_id,
                merchant_trans_id=merchant_trans_id,
                merchant_confirm_id=merchant_trans_id,
                error=-9,
                error_note="Transaction cancelled",
            )

        # Payment successful
        logger.info(f"Click payment completed: order={merchant_trans_id}, amount={amount}")

        if order_id:
            try:
                from app.services.unified_order_service import get_unified_order_service

                order_service = get_unified_order_service()
                if order_service:
                    await order_service.confirm_payment(order_id)
                elif hasattr(self._db, "update_payment_status"):
                    self._db.update_payment_status(order_id, "confirmed")
            except Exception as e:
                logger.warning(f"Failed to confirm payment for order #{order_id}: {e}")

        if self._db and hasattr(self._db, "upsert_click_transaction"):
            try:
                self._db.upsert_click_transaction(
                    click_trans_id=int(click_trans_id),
                    click_paydoc_id=str(click_paydoc_id) if click_paydoc_id else None,
                    merchant_trans_id=str(merchant_trans_id),
                    merchant_prepare_id=str(merchant_prepare_id),
                    service_id=str(expected_service_id),
                    amount=str(amount),
                    status="confirmed",
                )
            except Exception:
                pass

        # Fire-and-forget fiscalization (do not block Click callback)
        if order_id:
            try:
                fiscal_payment_id = (
                    str(click_paydoc_id) if click_paydoc_id else str(click_trans_id)
                )
                asyncio.create_task(
                    self.submit_click_fiscal_items(
                        order_id=int(order_id),
                        payment_id=fiscal_payment_id,
                        service_id=expected_service_id,
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to schedule Click fiscalization: {e}")

        return self._click_response(
            click_trans_id=click_trans_id,
            merchant_trans_id=merchant_trans_id,
            merchant_confirm_id=merchant_trans_id,
            error=0,
            error_note="Success",
        )

    # ===================== PAYME INTEGRATION =====================

    def generate_payme_url(
        self,
        order_id: int,
        amount: int,
        return_url: str | None = None,
        store_id: int | None = None,
    ) -> str:
        """
        Generate Payme checkout URL.

        Args:
            order_id: Unique order/booking ID
            amount: Amount in UZS (will be converted to tiyins)
            return_url: URL to redirect after payment
            store_id: Store ID to use store-specific credentials

        Returns:
            Payme checkout URL
        """
        import base64

        # Try store credentials first
        creds = None
        if store_id:
            creds = self.get_store_credentials(store_id, "payme")

        merchant_id = creds.merchant_id if creds else self.payme_merchant_id

        if not merchant_id:
            raise ValueError("Payme integration not configured")

        # Payme requires amount in tiyins (1 UZS = 100 tiyin)
        amount_tiyin = amount * 100

        # Build params
        params = f"m={merchant_id};ac.order_id={order_id};a={amount_tiyin}"

        if return_url:
            params += f";c={return_url}"

        # Encode to base64
        encoded = base64.b64encode(params.encode()).decode()

        return f"{self.payme_checkout_url}/{encoded}"

    def verify_payme_signature(self, auth_header: str, store_id: int = None) -> bool:
        """
        Verify Payme Authorization header.

        Returns True if signature is valid.
        """
        if not auth_header:
            return False

        import base64

        try:
            # Format: "Basic <base64(merchant_id:secret_key)>"
            if not auth_header.startswith("Basic "):
                return False

            encoded = auth_header[6:]  # Remove "Basic "
            decoded = base64.b64decode(encoded).decode()
            merchant_id, secret_key = decoded.split(":")

            # Try store credentials first
            if store_id:
                creds = self.get_store_credentials(store_id, "payme")
                if creds:
                    return merchant_id == creds.merchant_id and secret_key == creds.secret_key

            # Fallback to platform credentials
            return merchant_id == self.payme_merchant_id and secret_key == self.payme_secret_key
        except Exception:
            return False

    async def process_payme_request(self, method: str, params: dict, request_id: Any) -> dict:
        """
        Process Payme JSON-RPC request.

        Returns JSON-RPC response dict.
        """
        if method == "CheckPerformTransaction":
            return await self._payme_check_perform(params, request_id)
        elif method == "CreateTransaction":
            return await self._payme_create_transaction(params, request_id)
        elif method == "PerformTransaction":
            return await self._payme_perform_transaction(params, request_id)
        elif method == "CancelTransaction":
            return await self._payme_cancel_transaction(params, request_id)
        elif method == "CheckTransaction":
            return await self._payme_check_transaction(params, request_id)
        else:
            return {"error": {"code": -32601, "message": "Method not found"}, "id": request_id}

    async def _payme_check_perform(self, params: dict, request_id: Any) -> dict:
        """Check if transaction can be performed."""
        # Validate account
        order_id = params.get("account", {}).get("order_id")
        # amount could be validated against order

        if not order_id:
            return {"error": {"code": -31050, "message": "Order not found"}, "id": request_id}

        # Here you would validate order exists and amount matches
        # For now, return allow
        return {"result": {"allow": True}, "id": request_id}

    async def _payme_create_transaction(self, params: dict, request_id: Any) -> dict:
        """Create transaction."""
        transaction_id = params.get("id")
        account = params.get("account", {})
        order_id = account.get("order_id")
        amount = params.get("amount", 0)

        # Here you would create transaction in database
        logger.info(
            f"Payme transaction created: {transaction_id} for order {order_id}, amount: {amount}"
        )

        return {
            "result": {
                "create_time": int(datetime.now().timestamp() * 1000),
                "transaction": str(order_id),
                "state": 1,
            },
            "id": request_id,
        }

    async def _payme_perform_transaction(self, params: dict, request_id: Any) -> dict:
        """Perform (complete) transaction."""
        transaction_id = params.get("id")

        # Here you would complete transaction in database
        logger.info(f"Payme transaction performed: {transaction_id}")

        return {
            "result": {
                "perform_time": int(datetime.now().timestamp() * 1000),
                "transaction": transaction_id,
                "state": 2,
            },
            "id": request_id,
        }

    async def _payme_cancel_transaction(self, params: dict, request_id: Any) -> dict:
        """Cancel transaction."""
        transaction_id = params.get("id")
        reason = params.get("reason")

        # Here you would cancel transaction in database
        logger.info(f"Payme transaction cancelled: {transaction_id}, reason: {reason}")

        return {
            "result": {
                "cancel_time": int(datetime.now().timestamp() * 1000),
                "transaction": transaction_id,
                "state": -1,
            },
            "id": request_id,
        }

    async def _payme_check_transaction(self, params: dict, request_id: Any) -> dict:
        """Check transaction status."""
        transaction_id = params.get("id")

        # Here you would check transaction in database
        return {
            "result": {
                "create_time": int(datetime.now().timestamp() * 1000),
                "perform_time": 0,
                "cancel_time": 0,
                "transaction": transaction_id,
                "state": 1,
                "reason": None,
            },
            "id": request_id,
        }


# Singleton instance
_payment_service: PaymentService | None = None


def get_payment_service() -> PaymentService:
    """Get payment service singleton."""
    global _payment_service
    if _payment_service is None:
        _payment_service = PaymentService()
    return _payment_service
