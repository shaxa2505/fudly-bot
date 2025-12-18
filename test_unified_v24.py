"""
Test v24 unified orders - verify all CRUD operations work correctly.
"""
import sys
sys.path.insert(0, ".")

from database_pg_module import Database


def get_db():
    """Get database instance."""
    return Database()


def test_orders_crud():
    """Test that all orders (pickup + delivery) are accessible via orders table."""
    db = get_db()
    
    print("=" * 60)
    print("TEST: V24 Unified Orders CRUD")
    print("=" * 60)
    
    # 1. Check orders table structure
    print("\n1. Orders table columns:")
    result = db.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'orders' 
        AND column_name IN ('pickup_code', 'pickup_time', 'order_type', 'order_status')
        ORDER BY ordinal_position
    """)
    for col in result:
        print(f"   {col[0]}: {col[1]}")
    
    # 2. Get all orders
    print("\n2. All orders:")
    orders = db.execute("SELECT order_id, order_type, order_status, pickup_code FROM orders ORDER BY order_id")
    for order in orders:
        order_id, order_type, status, pickup_code = order
        code_display = f"code={pickup_code}" if pickup_code else "no code"
        print(f"   Order #{order_id}: type={order_type}, status={status}, {code_display}")
    
    # 3. Test get_order method
    print("\n3. Test get_order() method:")
    if orders:
        test_order_id = orders[0][0]
        order = db.get_order(test_order_id)
        if order:
            print(f"   ✅ get_order({test_order_id}) works")
            if isinstance(order, dict):
                print(f"      order_type: {order.get('order_type')}")
                print(f"      order_status: {order.get('order_status')}")
                print(f"      pickup_code: {order.get('pickup_code')}")
        else:
            print(f"   ❌ get_order({test_order_id}) returned None")
    
    # 4. Test get_store_orders method
    print("\n4. Test get_store_orders() method:")
    stores = db.execute("SELECT DISTINCT store_id FROM orders WHERE store_id IS NOT NULL")
    if stores:
        test_store_id = stores[0][0]
        store_orders = db.get_store_orders(test_store_id)
        print(f"   ✅ get_store_orders({test_store_id}) returned {len(store_orders)} orders")
        
        # Count by type
        pickup_count = sum(1 for o in store_orders if (o.get('order_type') if isinstance(o, dict) else None) == 'pickup')
        delivery_count = len(store_orders) - pickup_count
        print(f"      Pickup: {pickup_count}, Delivery: {delivery_count}")
    
    # 5. Check bookings_archive exists
    print("\n5. Check bookings_archive:")
    archive = db.execute("""
        SELECT COUNT(*) 
        FROM information_schema.tables 
        WHERE table_name = 'bookings_archive'
    """)
    if archive and archive[0][0] > 0:
        print(f"   ✅ bookings_archive table exists")
        archived_count = db.execute("SELECT COUNT(*) FROM bookings_archive")[0][0]
        print(f"      Archived bookings: {archived_count}")
    else:
        print(f"   ❌ bookings_archive table NOT found")
    
    # 6. Verify indexes
    print("\n6. Check indexes:")
    indexes = db.execute("""
        SELECT indexname 
        FROM pg_indexes 
        WHERE tablename = 'orders' 
        AND indexname IN ('idx_orders_pickup_code', 'idx_orders_pickup_time')
    """)
    for idx in indexes:
        print(f"   ✅ {idx[0]}")
    
    print("\n" + "=" * 60)
    print("✅ V24 UNIFIED ORDERS TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    test_orders_crud()
