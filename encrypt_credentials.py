"""Encrypt plaintext credentials in store_payment_integrations."""
import os
os.environ['SKIP_DB_INIT'] = '1'

from cryptography.fernet import Fernet
from database_pg import Database

def main():
    print("="*80)
    print("🔐 Encrypting payment credentials")
    print("="*80)
    
    # Generate or use existing encryption key
    key = os.getenv('ENCRYPTION_KEY')
    if not key:
        key = Fernet.generate_key().decode()
        print(f"\n⚠️  SAVE THIS KEY TO .env:")
        print(f"ENCRYPTION_KEY={key}")
        print("="*80)
    else:
        key = key.encode() if isinstance(key, str) else key
        
    fernet = Fernet(key)
    db = Database()
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # Get all payment integrations with plaintext credentials
        cursor.execute("""
            SELECT integration_id, store_id, provider, api_key, secret_key
            FROM store_payment_integrations
            WHERE api_key IS NOT NULL OR secret_key IS NOT NULL
        """)
        
        rows = cursor.fetchall()
        print(f"\n📊 Found {len(rows)} integrations to encrypt")
        
        encrypted_count = 0
        for row in rows:
            integration_id, store_id, provider, api_key, secret_key = row
            
            # Skip already encrypted (starts with 'gAAAA' - Fernet signature)
            if api_key and api_key.startswith('gAAAA'):
                continue
            if secret_key and secret_key.startswith('gAAAA'):
                continue
                
            # Encrypt credentials
            encrypted_api = fernet.encrypt(api_key.encode()).decode() if api_key else None
            encrypted_secret = fernet.encrypt(secret_key.encode()).decode() if secret_key else None
            
            cursor.execute("""
                UPDATE store_payment_integrations
                SET api_key = %s, secret_key = %s
                WHERE integration_id = %s
            """, (encrypted_api, encrypted_secret, integration_id))
            
            encrypted_count += 1
            print(f"  ✅ {provider} (store_id={store_id})")
        
        conn.commit()
        
        print(f"\n✅ Encrypted {encrypted_count} integrations")
        print("="*80)

if __name__ == "__main__":
    main()
