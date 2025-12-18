"""Encrypt plaintext credentials in store_payment_integrations.

This is a one-time maintenance script to move stored secrets to encrypted-at-rest
format (Fernet). It updates `store_payment_integrations.secret_key` in-place.

Usage (PowerShell):
  $env:ENCRYPTION_KEY = "<base64-fernet-key>"  # optional; will be generated if missing
  python .\\encrypt_credentials.py
"""

from __future__ import annotations

import os

os.environ["SKIP_DB_INIT"] = "1"

from cryptography.fernet import Fernet

from database_pg import Database


def main() -> None:
    print("=" * 80)
    print("Encrypting payment credentials (store_payment_integrations.secret_key)")
    print("=" * 80)

    # Generate or use existing encryption key
    key = (os.getenv("ENCRYPTION_KEY") or "").strip()
    if not key:
        key = Fernet.generate_key().decode("utf-8")
        print("\nSAVE THIS KEY TO .env (and production environment):")
        print(f"ENCRYPTION_KEY={key}")
        print("=" * 80)

    fernet = Fernet(key.encode("utf-8"))
    db = Database()

    with db.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, store_id, provider, secret_key
            FROM store_payment_integrations
            WHERE secret_key IS NOT NULL AND secret_key <> ''
            """
        )

        rows = cursor.fetchall()
        print(f"\nFound {len(rows)} integrations to check")

        encrypted_count = 0
        for integration_id, store_id, provider, secret_key in rows:
            # Skip already encrypted (starts with 'gAAAA' - Fernet signature)
            if isinstance(secret_key, str) and secret_key.startswith("gAAAA"):
                continue

            encrypted_secret = (
                fernet.encrypt(secret_key.encode("utf-8")).decode("utf-8") if secret_key else None
            )

            cursor.execute(
                """
                UPDATE store_payment_integrations
                SET secret_key = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (encrypted_secret, integration_id),
            )

            encrypted_count += 1
            print(f"  - Encrypted {provider} (store_id={store_id})")

        conn.commit()

        print(f"\nEncrypted {encrypted_count} integrations")
        print("=" * 80)


if __name__ == "__main__":
    main()
