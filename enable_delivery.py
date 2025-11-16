"""Enable delivery for all stores in database."""
import sqlite3

conn = sqlite3.connect('fudly.db')
cursor = conn.cursor()

# Enable delivery for all stores
cursor.execute('''
    UPDATE stores 
    SET delivery_enabled = 1, 
        delivery_price = 0, 
        min_order_amount = 0 
    WHERE delivery_enabled = 0 OR delivery_enabled IS NULL
''')
conn.commit()
updated = cursor.rowcount

# Check results
cursor.execute('SELECT COUNT(*) FROM stores WHERE delivery_enabled = 1')
total_enabled = cursor.fetchone()[0]

cursor.execute('SELECT store_id, name, delivery_enabled, delivery_price, min_order_amount FROM stores')
stores = cursor.fetchall()

print(f'\nUpdated: {updated} stores')
print(f'Total with delivery enabled: {total_enabled}\n')
print('All stores:')
for store in stores:
    print(f'  ID: {store[0]}, Name: {store[1]}, Delivery: {store[2]}, Price: {store[3]}, Min order: {store[4]}')

conn.close()
