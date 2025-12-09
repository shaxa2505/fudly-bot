"""Handlers orchestrator for browsing hot offers and stores.

This module now delegates actual handler registration to smaller modules:
- `browse_hot`   – hot offers, categories and generic offer catalog
- `browse_stores` – browsing establishments, stores and store-specific offers
"""
from __future__ import annotations

from typing import Any

from aiogram import Dispatcher

from app.services.offer_service import OfferService
from handlers.common import BrowseOffers  # re-exported for backwards compatibility

from .browse_hot import register_hot
from .browse_stores import register_stores


def setup(
    dp: Dispatcher,
    db: Any,
    offer_service: OfferService,
    logger: Any,
) -> None:
    """Register offer-related handlers on dispatcher.

    This is a thin orchestrator that wires submodules.
    """

    # Hot offers and generic offer catalog
    register_hot(dp, db, offer_service, logger)

    # Establishments, stores and store offers
    register_stores(dp, db, offer_service, logger)
