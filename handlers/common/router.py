"""
Common router - aggregates all common handlers.
"""
from aiogram import Router

from handlers.common import commands, help, registration, support

router = Router(name="common")

# Include sub-routers
router.include_router(support.router)
router.include_router(commands.router)
router.include_router(registration.router)
router.include_router(help.router)
