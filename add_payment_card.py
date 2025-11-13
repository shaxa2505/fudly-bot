#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для добавления платформенной платёжной карты
"""

import sqlite3
import sys

def add_payment_card():
    """Добавляет платёжную карту платформы в базу данных"""
    
    # Реквизиты для добавления (пример - замените на реальные)
    card_number = "8600 1234 5678 9012"
    card_holder = "FUDLY PLATFORM"
    bank_name = "Uzcard"
    
    try:
        conn = sqlite3.connect('fudly.db')
        cursor = conn.cursor()
        
        # Проверяем есть ли уже активная карта
        cursor.execute("SELECT * FROM payment_settings WHERE is_active = 1")
        existing = cursor.fetchone()
        
        if existing:
            print(f"⚠️  Активная карта уже существует: {existing[1]}")
            print("Хотите заменить её? (y/n): ", end='')
            response = input().strip().lower()
            
            if response != 'y':
                print("❌ Отменено")
                conn.close()
                return
            
            # Деактивируем старую карту
            cursor.execute("UPDATE payment_settings SET is_active = 0 WHERE is_active = 1")
        
        # Добавляем новую карту
        cursor.execute("""
            INSERT INTO payment_settings (card_number, card_holder, bank_name, is_active)
            VALUES (?, ?, ?, 1)
        """, (card_number, card_holder, bank_name))
        
        conn.commit()
        print(f"✅ Платёжная карта добавлена успешно!")
        print(f"💳 Номер: {card_number}")
        print(f"👤 Держатель: {card_holder}")
        print(f"🏦 Банк: {bank_name}")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"❌ Ошибка базы данных: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("=" * 50)
    print("Добавление платёжной карты платформы")
    print("=" * 50)
    print()
    
    add_payment_card()
    
    print()
    print("✅ Готово!")
