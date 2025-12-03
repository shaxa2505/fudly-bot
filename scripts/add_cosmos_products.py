"""
Скрипт для массового добавления товаров в магазин COSMOS.
Запуск: python scripts/add_cosmos_products.py

Товары из накладной № 95183 от 18.11.2025
"""
import os
import sys
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database

# ID магазина COSMOS (измените на правильный!)
STORE_ID = None  # <-- УКАЖИТЕ store_id вашего магазина!

# Товары из накладной
# Формат: (название, количество, покупная_цена, продажная_цена, срок_годности, штрихкод)
PRODUCTS = [
    ("TALISMAN ЧАЙ 300Г", 2, 206250, 216500, "30.11.2025", "4627081040549"),
    ("AHMAD TEA (TEA CHEST FOUR 4X10) 80Г", 2, 90000, 94500, "16.01.2026", "054881004817"),
    ("BETFORD ЧАЙ 300Г", 2, 200000, 210000, "03.06.2026", "4612753840664"),
    ("BETFORD ЧАЙ 400Г", 3, 237500, 249500, "01.03.2026", "4630017896066"),
    ("NESCAFE TASTERS CHOICE 397 GR USA", 2, 260000, 273000, "18.01.2026", "028000743079"),
    ("IMPRESSO KOFFEE 100G CT", 10, 46260, 48600, "29.01.2026", "4670016473226"),
    ("MACCOFFEE CREME 300Г", 4, 51250, 53800, "31.12.2025", "8887290140003"),
    ("NESTLE COFFEE MATE 425ГР", 2, 97020, 99000, "30.09.2025", "055000697248"),
    ("MAXWELL HOUSE КОФЕ 100G", 17, 47500, 47500, "30.07.2024", "8711000516706"),  # нет скидки
    ("EGOISTE SPECIAL 50Г CT", 1, 71250, 74000, "02.11.2025", "4260283250332"),
    ("NESQUIK KAKAO 600G", 3, 76570, 76570, "30.10.2025", "7613033214004"),  # нет скидки
    ("TWIX COFFEE 283.4G", 4, 140800, 140800, "17.11.2025", "024515308406"),  # нет скидки
    ("M&M'S COFFEE 283.4G", 6, 140800, 140800, "12.11.2025", "024515308383"),  # нет скидки
    ("MILKY WAY COFFEE 283.4G", 5, 140800, 140800, "12.12.2025", "024515308437"),  # нет скидки
]


def parse_date(date_str: str) -> datetime:
    """Parse DD.MM.YYYY date string."""
    return datetime.strptime(date_str, "%d.%m.%Y")


def add_products(db: Database, store_id: int):
    """Add all products to the store."""
    conn = db.get_connection()
    cursor = conn.cursor()

    added = 0
    for name, qty, discount_price, original_price, expiry_str, barcode in PRODUCTS:
        try:
            expiry_date = parse_date(expiry_str)

            # Вычисляем скидку
            if original_price > discount_price:
                discount_percent = int((1 - discount_price / original_price) * 100)
            else:
                discount_percent = 0

            cursor.execute(
                """
                INSERT INTO offers (
                    store_id, title, description, original_price, discount_price,
                    discount_percent, quantity, expiry_date, status, barcode
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
            """,
                (
                    store_id,
                    name,
                    f"Штрихкод: {barcode}",
                    original_price,
                    discount_price,
                    discount_percent,
                    qty,
                    expiry_date,
                    barcode,
                ),
            )
            added += 1
            print(f"✅ {name} - {qty} шт, {discount_price:,} сум ({discount_percent}% скидка)")

        except Exception as e:
            print(f"❌ Ошибка добавления {name}: {e}")

    conn.commit()
    conn.close()
    print(f"\n📦 Добавлено товаров: {added}/{len(PRODUCTS)}")


def list_stores(db: Database):
    """List all stores."""
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT store_id, name, city, status FROM stores")
    stores = cursor.fetchall()
    conn.close()

    print("\n📍 Доступные магазины:")
    for s in stores:
        print(f"  ID={s[0]}: {s[1]} ({s[2]}) - {s[3]}")
    return stores


def main():
    db = Database()

    if STORE_ID is None:
        print("⚠️  STORE_ID не указан!")
        stores = list_stores(db)

        if stores:
            try:
                store_id = int(input("\nВведите ID магазина для добавления товаров: "))
                add_products(db, store_id)
            except ValueError:
                print("❌ Неверный ID")
        else:
            print("❌ Магазины не найдены. Сначала создайте магазин через бота.")
    else:
        add_products(db, STORE_ID)


if __name__ == "__main__":
    main()
