-- Setup payment card for delivery orders
-- Run this in Railway PostgreSQL Query console

-- Create payment_settings table if not exists
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

-- Insert default payment card (change values below)
INSERT INTO payment_settings (card_number, card_holder)
VALUES ('8600123456789012', 'Fudly Platform')
ON CONFLICT DO NOTHING;

-- Verify
SELECT * FROM payment_settings;
