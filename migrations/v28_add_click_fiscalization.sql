ALTER TABLE store_payment_integrations
ADD COLUMN IF NOT EXISTS merchant_user_id TEXT;

CREATE TABLE IF NOT EXISTS click_fiscalization (
    id SERIAL PRIMARY KEY,
    order_id INTEGER,
    payment_id TEXT NOT NULL,
    service_id TEXT,
    status TEXT DEFAULT 'pending',
    error_code INTEGER,
    error_note TEXT,
    request_payload JSONB,
    response_payload JSONB,
    qr_code_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(order_id, payment_id),
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);
