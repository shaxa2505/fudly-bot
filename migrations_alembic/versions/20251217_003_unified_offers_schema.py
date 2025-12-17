"""unified_offers_schema

Revision ID: 20251217_003
Revises: 20251126_002
Create Date: 2025-12-17 00:00:00.000000

This migration unifies the offers schema to fix incompatibilities between
bot and Partner Panel systems:
- Changes available_from/until from VARCHAR to TIME
- Changes expiry_date from VARCHAR to DATE  
- Changes prices from FLOAT to INTEGER (stored in cents/kopeks)
- Adds CHECK constraints for data validation
- Preserves existing data with proper type conversion
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003_unified_schema'
down_revision: Union[str, None] = '002_add_fts'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade schema to unified types with data migration.
    
    Steps:
    1. Add temporary columns with correct types
    2. Migrate data from old columns to new columns
    3. Drop old columns
    4. Rename new columns to original names
    5. Add CHECK constraints
    """
    
    # Step 1: Add temporary columns with correct types
    op.add_column('offers', sa.Column('available_from_new', sa.Time(), nullable=True))
    op.add_column('offers', sa.Column('available_until_new', sa.Time(), nullable=True))
    op.add_column('offers', sa.Column('expiry_date_new', sa.Date(), nullable=True))
    op.add_column('offers', sa.Column('original_price_new', sa.Integer(), nullable=True))
    op.add_column('offers', sa.Column('discount_price_new', sa.Integer(), nullable=True))
    
    # Step 2: Migrate data with type conversion
    # This SQL handles both formats: "HH:MM" and ISO timestamps
    op.execute("""
        UPDATE offers
        SET 
            -- Convert time fields (handles both "08:00" and ISO "2024-12-17T08:00:00")
            available_from_new = CASE
                WHEN available_from ~ '^[0-9]{2}:[0-9]{2}$' THEN available_from::TIME
                WHEN available_from ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN SUBSTRING(available_from FROM 12 FOR 8)::TIME
                ELSE NULL
            END,
            available_until_new = CASE
                WHEN available_until ~ '^[0-9]{2}:[0-9]{2}$' THEN available_until::TIME
                WHEN available_until ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN SUBSTRING(available_until FROM 12 FOR 8)::TIME
                ELSE NULL
            END,
            -- Convert date field (handles "YYYY-MM-DD" and "DD.MM.YYYY" and ISO)
            expiry_date_new = CASE
                WHEN expiry_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN SUBSTRING(expiry_date FROM 1 FOR 10)::DATE
                WHEN expiry_date ~ '^[0-9]{2}\\.[0-9]{2}\\.[0-9]{4}' THEN TO_DATE(expiry_date, 'DD.MM.YYYY')
                ELSE NULL
            END,
            -- Convert prices from rubles (FLOAT) to kopeks (INTEGER)
            -- Multiply by 100 and round to handle float precision
            original_price_new = CASE
                WHEN original_price IS NOT NULL THEN ROUND(original_price * 100)::INTEGER
                ELSE NULL
            END,
            discount_price_new = CASE
                WHEN discount_price IS NOT NULL THEN ROUND(discount_price * 100)::INTEGER
                ELSE NULL
            END
        WHERE 
            available_from IS NOT NULL OR
            available_until IS NOT NULL OR
            expiry_date IS NOT NULL OR
            original_price IS NOT NULL OR
            discount_price IS NOT NULL
    """)
    
    # Step 3: Drop old columns
    op.drop_column('offers', 'available_from')
    op.drop_column('offers', 'available_until')
    op.drop_column('offers', 'expiry_date')
    op.drop_column('offers', 'original_price')
    op.drop_column('offers', 'discount_price')
    
    # Step 4: Rename new columns to original names
    op.alter_column('offers', 'available_from_new', new_column_name='available_from')
    op.alter_column('offers', 'available_until_new', new_column_name='available_until')
    op.alter_column('offers', 'expiry_date_new', new_column_name='expiry_date')
    op.alter_column('offers', 'original_price_new', new_column_name='original_price')
    op.alter_column('offers', 'discount_price_new', new_column_name='discount_price')
    
    # Step 5: Add CHECK constraints for data validation
    op.create_check_constraint(
        'check_prices_positive',
        'offers',
        'original_price IS NULL OR original_price >= 0'
    )
    op.create_check_constraint(
        'check_discount_valid',
        'offers',
        'discount_price IS NULL OR (discount_price >= 0 AND discount_price <= original_price)'
    )
    op.create_check_constraint(
        'check_quantity_positive',
        'offers',
        'quantity > 0'
    )
    op.create_check_constraint(
        'check_time_order',
        'offers',
        'available_from IS NULL OR available_until IS NULL OR available_from < available_until'
    )
    op.create_check_constraint(
        'check_expiry_future',
        'offers',
        'expiry_date IS NULL OR expiry_date >= CURRENT_DATE'
    )


def downgrade() -> None:
    """
    Downgrade back to original VARCHAR/FLOAT schema.
    
    Note: Some data precision may be lost in prices (kopeks → rubles).
    """
    
    # Step 1: Drop CHECK constraints
    op.drop_constraint('check_expiry_future', 'offers', type_='check')
    op.drop_constraint('check_time_order', 'offers', type_='check')
    op.drop_constraint('check_quantity_positive', 'offers', type_='check')
    op.drop_constraint('check_discount_valid', 'offers', type_='check')
    op.drop_constraint('check_prices_positive', 'offers', type_='check')
    
    # Step 2: Add temporary columns with old types
    op.add_column('offers', sa.Column('available_from_old', sa.VARCHAR(50), nullable=True))
    op.add_column('offers', sa.Column('available_until_old', sa.VARCHAR(50), nullable=True))
    op.add_column('offers', sa.Column('expiry_date_old', sa.VARCHAR(50), nullable=True))
    op.add_column('offers', sa.Column('original_price_old', sa.Float(), nullable=True))
    op.add_column('offers', sa.Column('discount_price_old', sa.Float(), nullable=True))
    
    # Step 3: Migrate data back (with precision loss in prices)
    op.execute("""
        UPDATE offers
        SET 
            available_from_old = available_from::VARCHAR,
            available_until_old = available_until::VARCHAR,
            expiry_date_old = expiry_date::VARCHAR,
            -- Convert kopeks back to rubles (divide by 100)
            original_price_old = CASE
                WHEN original_price IS NOT NULL THEN original_price::FLOAT / 100
                ELSE NULL
            END,
            discount_price_old = CASE
                WHEN discount_price IS NOT NULL THEN discount_price::FLOAT / 100
                ELSE NULL
            END
        WHERE 
            available_from IS NOT NULL OR
            available_until IS NOT NULL OR
            expiry_date IS NOT NULL OR
            original_price IS NOT NULL OR
            discount_price IS NOT NULL
    """)
    
    # Step 4: Drop new columns
    op.drop_column('offers', 'available_from')
    op.drop_column('offers', 'available_until')
    op.drop_column('offers', 'expiry_date')
    op.drop_column('offers', 'original_price')
    op.drop_column('offers', 'discount_price')
    
    # Step 5: Rename old columns back
    op.alter_column('offers', 'available_from_old', new_column_name='available_from')
    op.alter_column('offers', 'available_until_old', new_column_name='available_until')
    op.alter_column('offers', 'expiry_date_old', new_column_name='expiry_date')
    op.alter_column('offers', 'original_price_old', new_column_name='original_price')
    op.alter_column('offers', 'discount_price_old', new_column_name='discount_price')
