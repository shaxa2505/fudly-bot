"""Initial schema - all tables

Revision ID: 001_initial
Revises: 
Create Date: 2025-11-26

This migration creates all tables for the Fudly Bot database.
It represents the baseline schema and should be applied to new databases.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # === Users table ===
    op.create_table(
        'users',
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.String(255), nullable=True),
        sa.Column('first_name', sa.String(255), nullable=True),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('city', sa.String(100), server_default='Ташкент', nullable=True),
        sa.Column('language', sa.String(10), server_default='ru', nullable=True),
        sa.Column('role', sa.String(20), server_default='customer', nullable=True),
        sa.Column('is_admin', sa.Integer(), server_default='0', nullable=True),
        sa.Column('notifications_enabled', sa.Integer(), server_default='1', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('user_id')
    )
    op.create_index('ix_users_city', 'users', ['city'])
    op.create_index('ix_users_role', 'users', ['role'])
    op.create_index('ix_users_phone', 'users', ['phone'])

    # === Stores table ===
    op.create_table(
        'stores',
        sa.Column('store_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('owner_id', sa.BigInteger(), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('city', sa.String(100), nullable=False),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(100), server_default='Ресторан', nullable=True),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('status', sa.String(20), server_default='pending', nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('business_type', sa.String(50), server_default='supermarket', nullable=True),
        sa.Column('delivery_enabled', sa.Integer(), server_default='1', nullable=True),
        sa.Column('delivery_price', sa.Integer(), server_default='15000', nullable=True),
        sa.Column('min_order_amount', sa.Integer(), server_default='30000', nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['users.user_id']),
        sa.PrimaryKeyConstraint('store_id')
    )
    op.create_index('ix_stores_city', 'stores', ['city'])
    op.create_index('ix_stores_status', 'stores', ['status'])
    op.create_index('ix_stores_owner', 'stores', ['owner_id'])

    # === Offers table ===
    op.create_table(
        'offers',
        sa.Column('offer_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('original_price', sa.Float(), nullable=True),
        sa.Column('discount_price', sa.Float(), nullable=True),
        sa.Column('quantity', sa.Integer(), server_default='1', nullable=True),
        sa.Column('available_from', sa.String(50), nullable=True),
        sa.Column('available_until', sa.String(50), nullable=True),
        sa.Column('expiry_date', sa.String(50), nullable=True),
        sa.Column('photo_id', sa.String(255), nullable=True),
        sa.Column('status', sa.String(20), server_default='active', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('unit', sa.String(20), server_default='шт', nullable=True),
        sa.Column('category', sa.String(50), server_default='other', nullable=True),
        sa.ForeignKeyConstraint(['store_id'], ['stores.store_id']),
        sa.PrimaryKeyConstraint('offer_id')
    )
    op.create_index('ix_offers_store', 'offers', ['store_id'])
    op.create_index('ix_offers_status', 'offers', ['status'])
    op.create_index('ix_offers_category', 'offers', ['category'])

    # === Bookings table ===
    op.create_table(
        'bookings',
        sa.Column('booking_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('offer_id', sa.Integer(), nullable=True),
        sa.Column('store_id', sa.Integer(), nullable=True),
        sa.Column('quantity', sa.Integer(), server_default='1', nullable=True),
        sa.Column('booking_code', sa.String(50), nullable=True),
        sa.Column('pickup_time', sa.String(50), nullable=True),
        sa.Column('status', sa.String(20), server_default='active', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id']),
        sa.ForeignKeyConstraint(['offer_id'], ['offers.offer_id']),
        sa.ForeignKeyConstraint(['store_id'], ['stores.store_id']),
        sa.PrimaryKeyConstraint('booking_id')
    )
    op.create_index('ix_bookings_user', 'bookings', ['user_id'])
    op.create_index('ix_bookings_store', 'bookings', ['store_id'])
    op.create_index('ix_bookings_status', 'bookings', ['status'])
    op.create_index('ix_bookings_code', 'bookings', ['booking_code'])

    # === Orders table ===
    op.create_table(
        'orders',
        sa.Column('order_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('offer_id', sa.Integer(), nullable=True),
        sa.Column('store_id', sa.Integer(), nullable=True),
        sa.Column('delivery_address', sa.Text(), nullable=True),
        sa.Column('payment_method', sa.String(50), server_default='card', nullable=True),
        sa.Column('payment_status', sa.String(20), server_default='pending', nullable=True),
        sa.Column('payment_proof_photo_id', sa.String(255), nullable=True),
        sa.Column('order_status', sa.String(20), server_default='pending', nullable=True),
        sa.Column('quantity', sa.Integer(), server_default='1', nullable=True),
        sa.Column('total_price', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id']),
        sa.ForeignKeyConstraint(['offer_id'], ['offers.offer_id']),
        sa.ForeignKeyConstraint(['store_id'], ['stores.store_id']),
        sa.PrimaryKeyConstraint('order_id')
    )
    op.create_index('ix_orders_user', 'orders', ['user_id'])
    op.create_index('ix_orders_store', 'orders', ['store_id'])
    op.create_index('ix_orders_status', 'orders', ['order_status'])

    # === Payment settings table ===
    op.create_table(
        'payment_settings',
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('card_number', sa.String(50), nullable=True),
        sa.Column('card_holder', sa.String(255), nullable=True),
        sa.Column('card_expiry', sa.String(10), nullable=True),
        sa.Column('payment_instructions', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['store_id'], ['stores.store_id']),
        sa.PrimaryKeyConstraint('store_id')
    )

    # === Notifications table ===
    op.create_table(
        'notifications',
        sa.Column('notification_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('type', sa.String(50), nullable=True),
        sa.Column('title', sa.String(255), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('is_read', sa.Integer(), server_default='0', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id']),
        sa.PrimaryKeyConstraint('notification_id')
    )
    op.create_index('ix_notifications_user', 'notifications', ['user_id'])
    op.create_index('ix_notifications_read', 'notifications', ['is_read'])

    # === Ratings table ===
    op.create_table(
        'ratings',
        sa.Column('rating_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('booking_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('store_id', sa.Integer(), nullable=True),
        sa.Column('order_id', sa.Integer(), nullable=True),
        sa.Column('rating', sa.Integer(), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.booking_id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id']),
        sa.ForeignKeyConstraint(['store_id'], ['stores.store_id']),
        sa.ForeignKeyConstraint(['order_id'], ['orders.order_id']),
        sa.CheckConstraint('rating >= 1 AND rating <= 5', name='check_rating_range'),
        sa.PrimaryKeyConstraint('rating_id')
    )
    op.create_index('ix_ratings_store', 'ratings', ['store_id'])
    op.create_index('ix_ratings_user', 'ratings', ['user_id'])

    # === Favorites table ===
    op.create_table(
        'favorites',
        sa.Column('favorite_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('store_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id']),
        sa.ForeignKeyConstraint(['store_id'], ['stores.store_id']),
        sa.UniqueConstraint('user_id', 'store_id', name='uq_favorites_user_store'),
        sa.PrimaryKeyConstraint('favorite_id')
    )

    # === Promocodes table ===
    op.create_table(
        'promocodes',
        sa.Column('promo_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('discount_percent', sa.Integer(), nullable=True),
        sa.Column('discount_amount', sa.Float(), nullable=True),
        sa.Column('max_uses', sa.Integer(), server_default='0', nullable=True),
        sa.Column('current_uses', sa.Integer(), server_default='0', nullable=True),
        sa.Column('valid_from', sa.DateTime(), nullable=True),
        sa.Column('valid_until', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Integer(), server_default='1', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.UniqueConstraint('code'),
        sa.PrimaryKeyConstraint('promo_id')
    )
    op.create_index('ix_promocodes_code', 'promocodes', ['code'])
    op.create_index('ix_promocodes_active', 'promocodes', ['is_active'])

    # === Promo usage table ===
    op.create_table(
        'promo_usage',
        sa.Column('usage_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('promo_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('order_id', sa.Integer(), nullable=True),
        sa.Column('used_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['promo_id'], ['promocodes.promo_id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id']),
        sa.ForeignKeyConstraint(['order_id'], ['orders.order_id']),
        sa.PrimaryKeyConstraint('usage_id')
    )

    # === Referrals table ===
    op.create_table(
        'referrals',
        sa.Column('referral_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('referrer_user_id', sa.BigInteger(), nullable=True),
        sa.Column('referred_user_id', sa.BigInteger(), nullable=True),
        sa.Column('bonus_amount', sa.Float(), server_default='0', nullable=True),
        sa.Column('status', sa.String(20), server_default='pending', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['referrer_user_id'], ['users.user_id']),
        sa.ForeignKeyConstraint(['referred_user_id'], ['users.user_id']),
        sa.PrimaryKeyConstraint('referral_id')
    )
    op.create_index('ix_referrals_referrer', 'referrals', ['referrer_user_id'])
    op.create_index('ix_referrals_referred', 'referrals', ['referred_user_id'])

    # === FSM states table ===
    op.create_table(
        'fsm_states',
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('state', sa.String(255), nullable=True),
        sa.Column('data', postgresql.JSONB(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('user_id')
    )

    # === Platform settings table ===
    op.create_table(
        'platform_settings',
        sa.Column('key', sa.String(100), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('key')
    )

    # === Pickup slots table ===
    op.create_table(
        'pickup_slots',
        sa.Column('slot_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=True),
        sa.Column('day_of_week', sa.Integer(), nullable=True),
        sa.Column('start_time', sa.String(10), nullable=True),
        sa.Column('end_time', sa.String(10), nullable=True),
        sa.Column('max_bookings', sa.Integer(), server_default='10', nullable=True),
        sa.Column('is_active', sa.Integer(), server_default='1', nullable=True),
        sa.ForeignKeyConstraint(['store_id'], ['stores.store_id']),
        sa.PrimaryKeyConstraint('slot_id')
    )
    op.create_index('ix_pickup_slots_store', 'pickup_slots', ['store_id'])


def downgrade() -> None:
    # Drop tables in reverse order (respecting foreign keys)
    op.drop_table('pickup_slots')
    op.drop_table('platform_settings')
    op.drop_table('fsm_states')
    op.drop_table('referrals')
    op.drop_table('promo_usage')
    op.drop_table('promocodes')
    op.drop_table('favorites')
    op.drop_table('ratings')
    op.drop_table('notifications')
    op.drop_table('payment_settings')
    op.drop_table('orders')
    op.drop_table('bookings')
    op.drop_table('offers')
    op.drop_table('stores')
    op.drop_table('users')
