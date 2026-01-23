CREATE TABLE IF NOT EXISTS click_transactions (
    id SERIAL PRIMARY KEY,
    click_trans_id BIGINT UNIQUE NOT NULL,
    merchant_trans_id TEXT,
    merchant_prepare_id TEXT,
    service_id TEXT,
    amount TEXT,
    status TEXT DEFAULT 'prepared',
    error_code INTEGER,
    error_note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
