"""
Quick fix: Add payment card via Railway PostgreSQL Web Console

1. Open your Railway project: https://railway.app
2. Click on PostgreSQL database
3. Go to "Data" tab
4. Click "Query" button
5. Paste and run this SQL:

CREATE TABLE IF NOT EXISTS payment_settings (
    id SERIAL PRIMARY KEY,
    store_id INTEGER,
    card_number VARCHAR(20) NOT NULL,
    card_holder VARCHAR(100) NOT NULL,
    card_expiry VARCHAR(7),
    payment_instructions TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO payment_settings (card_number, card_holder)
VALUES ('8600123456789012', 'Fudly Platform');

SELECT * FROM payment_settings;

---

Alternatively, use Railway CLI:
$ railway link
$ railway run psql $DATABASE_URL

Then in psql:
postgres=> CREATE TABLE IF NOT EXISTS payment_settings (...);
postgres=> INSERT INTO payment_settings (card_number, card_holder) VALUES ('8600123456789012', 'Fudly Platform');
postgres=> SELECT * FROM payment_settings;
"""

print(__doc__)
