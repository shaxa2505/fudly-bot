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

import hashlib
import os
from datetime import datetime
from enum import Enum
from typing import Any
from urllib.parse import urlencode

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
    ):
        self.provider = provider
        self.merchant_id = merchant_id
        self.secret_key = secret_key
        self.service_id = service_id  # Only for Click


class PaymentService:
    """Service for handling online payments."""

    def __init__(self):
        # Platform-level Click credentials (fallback)
        self.click_merchant_id = os.getenv("CLICK_MERCHANT_ID")
        self.click_service_id = os.getenv("CLICK_SERVICE_ID")
        self.click_secret_key = os.getenv("CLICK_SECRET_KEY")

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
        data = f"{click_trans_id}{service_id}{secret_key}{merchant_trans_id}{amount}{action}{sign_time}"
        expected_sign = hashlib.md5(data.encode()).hexdigest()

        return expected_sign == sign_string

    async def process_click_prepare(
        self,
        click_trans_id: str,
        merchant_trans_id: str,
        amount: float,
        action: str,
        sign_time: str,
        sign_string: str,
    ) -> dict:
        """
        Process Click PREPARE request.

        Returns response dict for Click.
        """
        # Verify signature
        if not self.verify_click_signature(
            click_trans_id,
            self.click_service_id,
            merchant_trans_id,
            str(int(amount)),
            action,
            sign_time,
            sign_string,
        ):
            return {"error": -1, "error_note": "Invalid signature"}

        # Here you would validate the order exists and amount matches
        # For now, return success
        return {
            "click_trans_id": click_trans_id,
            "merchant_trans_id": merchant_trans_id,
            "merchant_prepare_id": merchant_trans_id,
            "error": 0,
            "error_note": "Success",
        }

    async def process_click_complete(
        self,
        click_trans_id: str,
        merchant_trans_id: str,
        merchant_prepare_id: str,
        amount: float,
        action: str,
        sign_time: str,
        sign_string: str,
        error: int,
    ) -> dict:
        """
        Process Click COMPLETE request.

        Returns response dict for Click.
        """
        # Verify signature
        if not self.verify_click_signature(
            click_trans_id,
            self.click_service_id,
            merchant_trans_id,
            str(int(amount)),
            action,
            sign_time,
            sign_string,
        ):
            return {"error": -1, "error_note": "Invalid signature"}

        if error != 0:
            # Payment failed or cancelled
            return {
                "click_trans_id": click_trans_id,
                "merchant_trans_id": merchant_trans_id,
                "merchant_confirm_id": merchant_trans_id,
                "error": error,
                "error_note": "Payment failed",
            }

        # Payment successful
        # Here you would update order status in database
        logger.info(f"Click payment completed: order={merchant_trans_id}, amount={amount}")

        return {
            "click_trans_id": click_trans_id,
            "merchant_trans_id": merchant_trans_id,
            "merchant_confirm_id": merchant_trans_id,
            "error": 0,
            "error_note": "Success",
        }

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
