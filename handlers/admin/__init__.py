"""
Admin handlers package - модуль admin разделен на:
- panel: главная админ-панель (/admin, Dashboard, Exit)
- stats: статистика (пользователи, магазины, товары, бронирования)
- dashboard: админ-панель и статистика с callback'ами  
- legacy: легаси обработчики (модерация, команды, просмотр данных)
"""
from . import dashboard, legacy, panel, stats

__all__ = ['dashboard', 'legacy', 'panel', 'stats']
