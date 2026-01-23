ALTER TABLE click_transactions
ADD COLUMN IF NOT EXISTS click_paydoc_id TEXT;
