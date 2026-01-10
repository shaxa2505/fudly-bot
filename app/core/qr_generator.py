"""
QR Code generator for booking confirmations.
Generates QR codes that link to bot for easy order verification.
"""
from __future__ import annotations

import io
import os

try:
    import qrcode
    from qrcode.image.styledpil import StyledPilImage
    from qrcode.image.styles.moduledrawers import RoundedModuleDrawer

    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


# Bot username for deep links - can be overridden via parameter
DEFAULT_BOT_USERNAME = os.environ.get("BOT_USERNAME", "fudlyuzbot")


def generate_booking_qr(
    booking_code: str, booking_id: int, bot_username: str | None = None
) -> io.BytesIO | None:
    """
    Generate QR code for a booking.

    The QR contains a deep link: t.me/BotName?start=pickup_BOOKINGCODE
    When scanned, it opens the bot and triggers pickup confirmation flow.

    Args:
        booking_code: The booking code (e.g., "SYNO0M")
        booking_id: The booking ID for reference
        bot_username: Bot username for deep link (without @). If None, uses DEFAULT_BOT_USERNAME

    Returns:
        BytesIO with PNG image data, or None if QR generation fails
    """
    if not QR_AVAILABLE:
        logger.warning("QR code generation not available - qrcode package not installed")
        return None

    username = bot_username or DEFAULT_BOT_USERNAME
    logger.info(
        f"🔗 QR generating for booking {booking_code} with bot_username: '{username}' (passed: '{bot_username}', default: '{DEFAULT_BOT_USERNAME}')"
    )

    try:
        # Create deep link for Telegram bot
        # Format: t.me/BotName?start=pickup_CODE
        deep_link = f"https://t.me/{username}?start=pickup_{booking_code}"
        logger.info(f"🔗 QR deep link: {deep_link}")

        # Create QR code with nice styling
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(deep_link)
        qr.make(fit=True)

        # Create styled image
        try:
            img = qr.make_image(
                image_factory=StyledPilImage,
                module_drawer=RoundedModuleDrawer(),
                fill_color="#2E7D32",  # Green color matching Fudly brand
                back_color="white",
            )
        except Exception:
            # Fallback to simple image if styled fails
            img = qr.make_image(fill_color="black", back_color="white")

        # Save to BytesIO
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        logger.info(f"Generated QR for booking {booking_id} ({booking_code})")
        return buffer

    except Exception as e:
        logger.error(f"Failed to generate QR code: {e}")
        return None


def generate_simple_qr(data: str) -> io.BytesIO | None:
    """
    Generate a simple QR code with any data.

    Args:
        data: Any string to encode in QR

    Returns:
        BytesIO with PNG image data, or None if generation fails
    """
    if not QR_AVAILABLE:
        return None

    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=8,
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        return buffer

    except Exception as e:
        logger.error(f"Failed to generate simple QR: {e}")
        return None
