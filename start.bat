@echo off
chcp 65001 > nul
echo ========================================
echo   Too Good To Go Bot - Запуск
echo ========================================
echo.

REM Проверка наличия Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден!
    echo Установите Python с https://www.python.org/
    pause
    exit /b 1
)

echo [OK] Python найден
echo.

REM Проверка зависимостей
echo Проверка зависимостей...
pip show aiogram >nul 2>&1
if errorlevel 1 (
    echo [!] Установка aiogram...
    pip install aiogram
)

pip show python-dotenv >nul 2>&1
if errorlevel 1 (
    echo [!] Установка python-dotenv...
    pip install python-dotenv
)

echo [OK] Все зависимости установлены
echo.

REM Проверка .env файла
if not exist ".env" (
    echo [ОШИБКА] Файл .env не найден!
    echo Создайте файл .env с вашим токеном бота
    pause
    exit /b 1
)

echo [OK] Файл .env найден
echo.

echo ========================================
echo   Запуск бота...
echo ========================================
echo.
echo Для остановки нажмите Ctrl+C
echo.

python bot.py

pause
