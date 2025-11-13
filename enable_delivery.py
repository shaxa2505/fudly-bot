#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для включения доставки у тестовых магазинов
"""

import sqlite3

def enable_delivery_for_stores():
    """Включает доставку для всех активных магазинов"""
    
    try:
        conn = sqlite3.connect('fudly.db')
        cursor = conn.cursor()
        
        # Получаем список магазинов
        cursor.execute("SELECT store_id, name, delivery_enabled, delivery_price, min_order_amount FROM stores")
        stores = cursor.fetchall()
        
        print(f"Найдено магазинов: {len(stores)}\n")
        
        # Обновляем настройки доставки для всех магазинов
        updated_count = 0
        for store in stores:
            store_id, name, delivery_enabled, delivery_price, min_order_amount = store
            
            if not delivery_enabled:
                # Включаем доставку с параметрами по умолчанию
                cursor.execute("""
                    UPDATE stores 
                    SET delivery_enabled = 1, 
                        delivery_price = 15000,
                        min_order_amount = 30000
                    WHERE store_id = ?
                """, (store_id,))
                print(f"✅ {name}: доставка включена (15,000 сум, мин. заказ 30,000 сум)")
                updated_count += 1
            else:
                print(f"ℹ️  {name}: доставка уже включена ({delivery_price:,} сум, мин. {min_order_amount:,} сум)")
        
        conn.commit()
        conn.close()
        
        print(f"\n✅ Обновлено магазинов: {updated_count}")
        
    except sqlite3.Error as e:
        print(f"❌ Ошибка базы данных: {e}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    print("=" * 50)
    print("Включение доставки для магазинов")
    print("=" * 50)
    print()
    
    enable_delivery_for_stores()
    
    print()
    print("✅ Готово!")
