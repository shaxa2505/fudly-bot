-- SQL Script to Make User a Seller/Partner
-- Run this in your PostgreSQL database

-- Option 1: Update YOUR user to be a seller
UPDATE users 
SET role = 'seller' 
WHERE telegram_id = 253445521;

-- Option 2: Check current users and their roles
SELECT telegram_id, first_name, username, role, city 
FROM users 
ORDER BY created_at DESC 
LIMIT 10;

-- Option 3: Create a test seller if user doesn't exist
INSERT INTO users (telegram_id, first_name, username, role, city, language)
VALUES (253445521, 'Test Partner', 'testpartner', 'seller', 'Ташкент', 'ru')
ON CONFLICT (telegram_id) DO UPDATE 
SET role = 'seller';

-- Option 4: List all sellers
SELECT telegram_id, first_name, role, city 
FROM users 
WHERE role = 'seller';
