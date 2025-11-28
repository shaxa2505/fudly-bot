-- Migration: Add favorites functionality
-- Created: 2025-11-29
-- Description: Add table for storing user favorite offers

-- Create user_favorites table
CREATE TABLE IF NOT EXISTS user_favorites (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    offer_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Foreign key to users table
    CONSTRAINT fk_user_favorites_user
        FOREIGN KEY (user_id)
        REFERENCES users(telegram_id)
        ON DELETE CASCADE,

    -- Foreign key to offers table (assuming you have offers table)
    -- CONSTRAINT fk_user_favorites_offer
    --     FOREIGN KEY (offer_id)
    --     REFERENCES offers(id)
    --     ON DELETE CASCADE,

    -- Unique constraint to prevent duplicate favorites
    CONSTRAINT unique_user_offer
        UNIQUE (user_id, offer_id)
);

-- Create index for faster queries
CREATE INDEX idx_user_favorites_user_id ON user_favorites(user_id);
CREATE INDEX idx_user_favorites_offer_id ON user_favorites(offer_id);
CREATE INDEX idx_user_favorites_created_at ON user_favorites(created_at DESC);

-- Add comments
COMMENT ON TABLE user_favorites IS 'Stores user favorite offers for Mini App';
COMMENT ON COLUMN user_favorites.user_id IS 'Telegram user ID';
COMMENT ON COLUMN user_favorites.offer_id IS 'ID of the favorited offer';
COMMENT ON COLUMN user_favorites.created_at IS 'When the favorite was added';

-- Grant permissions (adjust as needed)
-- GRANT SELECT, INSERT, DELETE ON user_favorites TO your_app_user;
-- GRANT USAGE, SELECT ON SEQUENCE user_favorites_id_seq TO your_app_user;
