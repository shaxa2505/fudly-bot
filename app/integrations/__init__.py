"""Integrations package - интеграции с внешними системами."""

from app.integrations.onec_integration import (
    OneCConfig,
    OneCHttpService,
    OneCIntegration,
    OneCProduct,
    create_1c_config_from_env,
)

__all__ = [
    "OneCConfig",
    "OneCIntegration",
    "OneCHttpService",
    "OneCProduct",
    "create_1c_config_from_env",
]
