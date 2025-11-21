import os
import psycopg

conn = psycopg.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

# Check stores with active offers
cur.execute("""
SELECT s.store_id, s.name, s.city, s.business_type, s.status, COUNT(o.offer_id) as cnt 
FROM stores s 
INNER JOIN offers o ON s.store_id = o.store_id 
    AND o.status = 'active' 
    AND o.quantity > 0 
WHERE (s.status = 'active' OR s.status = 'approved') 
    AND LOWER(s.business_type) = LOWER('supermarket')
GROUP BY s.store_id 
LIMIT 5
""")

rows = cur.fetchall()
print(f'Total supermarket stores with active offers: {len(rows)}')
for i, r in enumerate(rows):
    print(f'{i+1}. ID={r[0]}, Name={r[1]}, City={r[2]}, Type={r[3]}, Status={r[4]}, Offers={r[5]}')

# Check with city filter
print("\n--- With city filter 'Самарканд' ---")
cur.execute("""
SELECT s.store_id, s.name, s.city, s.business_type, s.status, COUNT(o.offer_id) as cnt 
FROM stores s 
INNER JOIN offers o ON s.store_id = o.store_id 
    AND o.status = 'active' 
    AND o.quantity > 0 
WHERE (s.status = 'active' OR s.status = 'approved') 
    AND LOWER(s.business_type) = LOWER('supermarket')
    AND (LOWER(s.city) = LOWER(%s) OR s.city ILIKE %s OR s.city IS NULL)
GROUP BY s.store_id 
LIMIT 5
""", ('Самарканд', '%Самарканд%'))

rows = cur.fetchall()
print(f'Total stores: {len(rows)}')
for i, r in enumerate(rows):
    print(f'{i+1}. ID={r[0]}, Name={r[1]}, City={r[2]}, Type={r[3]}, Status={r[4]}, Offers={r[5]}')

conn.close()
