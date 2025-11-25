#!/usr/bin/env python3
"""
Check bookings for a user - run on Railway console or locally with DB access.

Usage: python scripts/check_bookings.py <user_id>
"""
import os
import sys

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/check_bookings.py <user_id>")
        print("Example: python scripts/check_bookings.py 123456789")
        sys.exit(1)
    
    user_id = int(sys.argv[1])
    
    # Try PostgreSQL connection
    try:
        import psycopg_pool
        from psycopg.rows import dict_row
        
        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            print("ERROR: DATABASE_URL not set")
            sys.exit(1)
        
        pool = psycopg_pool.ConnectionPool(DATABASE_URL, min_size=1, max_size=2)
        
        with pool.connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            
            # Check all bookings for user
            cursor.execute('''
                SELECT b.booking_id, b.offer_id, b.user_id, b.status, b.booking_code,
                       b.quantity, b.created_at,
                       o.title, o.discount_price,
                       s.name as store_name
                FROM bookings b
                LEFT JOIN offers o ON b.offer_id = o.offer_id
                LEFT JOIN stores s ON o.store_id = s.store_id
                WHERE b.user_id = %s
                ORDER BY b.created_at DESC
            ''', (user_id,))
            
            bookings = cursor.fetchall()
            
            print(f"\n=== Bookings for user {user_id} ===\n")
            print(f"Total: {len(bookings)}")
            
            active = [b for b in bookings if b['status'] in ('pending', 'confirmed', 'active')]
            print(f"Active (pending/confirmed): {len(active)}")
            
            print("\n--- All bookings ---")
            for b in bookings:
                status_emoji = "⏳" if b['status'] == 'pending' else "✅" if b['status'] == 'confirmed' else "❌"
                print(f"{status_emoji} #{b['booking_id']} | {b['status']:12} | {b['title'] or 'N/A'} | code: {b['booking_code']} | {b['created_at']}")
            
            if not bookings:
                print("  (no bookings found)")
            
            # Check user exists
            cursor.execute('SELECT user_id, first_name, username, phone, city FROM users WHERE user_id = %s', (user_id,))
            user = cursor.fetchone()
            print(f"\n--- User info ---")
            if user:
                print(f"ID: {user['user_id']}, Name: {user['first_name']}, Username: {user['username']}, Phone: {user['phone']}, City: {user['city']}")
            else:
                print(f"  User {user_id} NOT FOUND in database!")
        
        pool.close()
        
    except ImportError:
        print("psycopg not installed - this script requires DATABASE_URL connection")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
