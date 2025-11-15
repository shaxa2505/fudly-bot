"""
Admin handlers package - модуль admin разделен на:
- dashboard: админ-панель и статистика с callback'ами  
- legacy: легаси обработчики (модерация, команды, просмотр данных)
"""
from . import dashboard, legacy

__all__ = ['dashboard', 'legacy']
