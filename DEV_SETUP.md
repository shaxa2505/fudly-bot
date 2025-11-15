# 🛠️ Development Setup Guide

## Быстрый старт для разработчиков

### 1. Установка зависимостей

```powershell
# Активируйте виртуальное окружение (если ещё не активировано)
.\.venv\Scripts\Activate.ps1

# Обновите pip
python -m pip install --upgrade pip

# Установите зависимости для разработки
pip install -e ".[dev]"  # если используете setup.py
# ИЛИ
pip install -r requirements.txt
pip install pytest pytest-cov pytest-asyncio mypy black ruff pre-commit
```

### 2. Настройка Pre-commit Hooks

```powershell
# Установите pre-commit hooks
pre-commit install

# Запустите проверку на всех файлах (опционально)
pre-commit run --all-files
```

### 3. Конфигурация PyCharm/VS Code

#### VS Code (рекомендуется)

Создайте `.vscode/settings.json`:

```json
{
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": false,
  "python.linting.flake8Enabled": false,
  "python.linting.mypyEnabled": true,
  "python.formatting.provider": "black",
  "python.formatting.blackArgs": ["--line-length", "100"],
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports": true
  },
  "[python]": {
    "editor.defaultFormatter": "ms-python.black-formatter"
  }
}
```

#### PyCharm

1. Settings → Tools → Black → Enable black formatter
2. Settings → Tools → External Tools → Add Ruff
3. Settings → Editor → Code Style → Python → Set line length to 100

### 4. Запуск тестов

```powershell
# Запустить все тесты
pytest

# Запустить с coverage
pytest --cov=app --cov=handlers --cov-report=html

# Запустить конкретный файл
pytest tests/test_database.py

# Запустить с verbose output
pytest -v -s
```

### 5. Type Checking

```powershell
# Проверка всех файлов
mypy .

# Проверка конкретного модуля
mypy app/

# Игнорировать импорты (если нужно)
mypy --ignore-missing-imports .
```

### 6. Code Formatting

```powershell
# Форматировать все файлы
black .

# Проверить без изменений
black --check .

# Форматировать конкретную папку
black app/
```

### 7. Linting

```powershell
# Проверить весь проект
ruff check .

# Автоматически исправить проблемы
ruff check --fix .

# Проверить конкретный файл
ruff check bot.py
```

---

## 📁 Новая структура проекта

```
fudly-bot/
├── app/
│   ├── core/
│   │   ├── bootstrap.py       # Инициализация приложения
│   │   ├── cache.py            # Кэш менеджер
│   │   ├── config.py           # Конфигурация (typed)
│   │   ├── database.py         # Database factory
│   │   ├── exceptions.py       # ✨ NEW: Custom exceptions
│   │   ├── security.py         # Security helpers
│   │   └── utils.py            # ✨ NEW: Utility functions
│   │
│   ├── services/
│   │   ├── admin_service.py
│   │   └── offer_service.py
│   │
│   └── keyboards/
│       ├── admin.py
│       └── offers.py
│
├── handlers/
│   ├── common/
│   │   ├── __init__.py         # ✨ NEW
│   │   └── states.py           # ✨ NEW: Централизованные FSM states
│   ├── admin.py
│   ├── offers.py
│   └── registration.py
│
├── tests/
│   ├── test_database.py
│   └── test_security.py
│
├── .pre-commit-config.yaml     # ✨ NEW: Pre-commit hooks
├── pyproject.toml              # ✨ NEW: Dev tools config
├── bot.py                      # Main entry point
├── database.py                 # SQLite implementation
├── database_pg.py              # PostgreSQL implementation
└── database_protocol.py        # Database protocol
```

---

## 🔧 Основные изменения

### 1. Централизованные FSM States

**Раньше:** States дублировались в `bot.py` и `handlers/common.py`

**Теперь:** Все states в `handlers/common/states.py`

```python
# Импорт states
from handlers.common import Registration, CreateOffer, BookOffer

# Использование
@dp.message(Registration.phone)
async def register_phone(message: types.Message, state: FSMContext):
    ...
```

### 2. Utility Functions

**Раньше:** Helper функции дублировались в `bot.py`

**Теперь:** Централизованы в `app/core/utils.py`

```python
from app.core.utils import get_user_field, get_store_field

# Работает с dict (PostgreSQL) и tuple (SQLite)
user_name = get_user_field(user, 'first_name', 'Unknown')
store_city = get_store_field(store, 'city', 'Ташкент')
```

### 3. Custom Exceptions

**Раньше:** Голые `except Exception:`

**Теперь:** Специфичные исключения в `app/core/exceptions.py`

```python
from app.core.exceptions import UserNotFoundException, DatabaseException

try:
    user = db.get_user(user_id)
    if not user:
        raise UserNotFoundException(user_id)
except DatabaseException as e:
    logger.error(f"Database error: {e}")
```

### 4. Cache Refactoring

**Раньше:** Словарь `user_cache` в `bot.py`

**Теперь:** `CacheManager` в `app/core/cache.py`

```python
# В bot.py
from app.core.cache import CacheManager

# Использование
user_data = cache.get_user_data(user_id)
cache.invalidate_user(user_id)
```

---

## ⚙️ Команды разработки

### Форматирование + Проверки (всё сразу)

```powershell
# 1. Форматирование
black .

# 2. Линтинг с автофиксом
ruff check --fix .

# 3. Type checking
mypy .

# 4. Тесты
pytest --cov
```

### Pre-commit (автоматически при коммите)

```powershell
# Проверка перед коммитом
git add .
git commit -m "Your message"
# pre-commit hooks запустятся автоматически

# Пропустить hooks (не рекомендуется)
git commit --no-verify -m "Skip hooks"
```

---

## 🐛 Troubleshooting

### Ошибка: "pre-commit command not found"

```powershell
pip install pre-commit
pre-commit install
```

### Ошибка: "black command not found"

```powershell
pip install black
```

### Ошибка: "mypy не находит модули"

```powershell
# Установите typing stubs
pip install types-requests

# Или игнорируйте missing imports
mypy --ignore-missing-imports .
```

### Ошибка при импорте handlers.common

```powershell
# Убедитесь что __init__.py существует
ls handlers/common/__init__.py

# Если нет - создайте
New-Item -ItemType File handlers/common/__init__.py
```

---

## 📊 Проверка качества кода

### Coverage Report

```powershell
pytest --cov --cov-report=html
# Откройте htmlcov/index.html в браузере
```

### MyPy Strict Mode

```powershell
mypy --strict app/
```

### Ruff Statistics

```powershell
ruff check --statistics .
```

---

## 🎯 Best Practices

1. **Всегда используйте type annotations**
   ```python
   def get_user(user_id: int) -> Optional[Dict[str, Any]]:
       ...
   ```

2. **Используйте custom exceptions**
   ```python
   raise UserNotFoundException(user_id)
   # Вместо: raise Exception("User not found")
   ```

3. **Документируйте функции**
   ```python
   def calculate_discount(price: float, percent: int) -> float:
       """Calculate discounted price.
       
       Args:
           price: Original price
           percent: Discount percentage (0-100)
           
       Returns:
           Discounted price
           
       Raises:
           ValueError: If percent is invalid
       """
       ...
   ```

4. **Запускайте тесты перед коммитом**
   ```powershell
   pytest && git commit
   ```

5. **Используйте pre-commit hooks**
   - Форматирование автоматически
   - Линтинг перед коммитом
   - Type checking в CI

---

## 📚 Дополнительные ресурсы

- [Black Documentation](https://black.readthedocs.io/)
- [Ruff Documentation](https://beta.ruff.rs/)
- [MyPy Documentation](https://mypy.readthedocs.io/)
- [Pytest Documentation](https://docs.pytest.org/)
- [Pre-commit Documentation](https://pre-commit.com/)

---

**Last updated:** 2025-11-15
