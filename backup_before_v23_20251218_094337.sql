-- Backup created: 2025-12-18 09:43:40.132203
-- Total indexes: 55

-- alembic_version_pkc
CREATE UNIQUE INDEX alembic_version_pkc ON public.alembic_version USING btree (version_num);

-- bookings_pkey
CREATE UNIQUE INDEX bookings_pkey ON public.bookings USING btree (booking_id);

-- favorites_pkey
CREATE UNIQUE INDEX favorites_pkey ON public.favorites USING btree (favorite_id);

-- favorites_user_id_store_id_key
CREATE UNIQUE INDEX favorites_user_id_store_id_key ON public.favorites USING btree (user_id, store_id);

-- fsm_states_pkey
CREATE UNIQUE INDEX fsm_states_pkey ON public.fsm_states USING btree (user_id);

-- idx_bookings_code
CREATE INDEX idx_bookings_code ON public.bookings USING btree (booking_code);

-- idx_bookings_created
CREATE INDEX idx_bookings_created ON public.bookings USING btree (created_at DESC);

-- idx_bookings_offer
CREATE INDEX idx_bookings_offer ON public.bookings USING btree (offer_id);

-- idx_bookings_status
CREATE INDEX idx_bookings_status ON public.bookings USING btree (status);

-- idx_bookings_store
CREATE INDEX idx_bookings_store ON public.bookings USING btree (store_id);

-- idx_bookings_user
CREATE INDEX idx_bookings_user ON public.bookings USING btree (user_id);

-- idx_favorites_store
CREATE INDEX idx_favorites_store ON public.favorites USING btree (store_id);

-- idx_favorites_user
CREATE INDEX idx_favorites_user ON public.favorites USING btree (user_id);

-- idx_notifications_unread
CREATE INDEX idx_notifications_unread ON public.notifications USING btree (user_id, is_read);

-- idx_notifications_user
CREATE INDEX idx_notifications_user ON public.notifications USING btree (user_id);

-- idx_offers_category
CREATE INDEX idx_offers_category ON public.offers USING btree (category);

-- idx_offers_category_status
CREATE INDEX idx_offers_category_status ON public.offers USING btree (category, status);

-- idx_offers_expiry
CREATE INDEX idx_offers_expiry ON public.offers USING btree (expiry_date);

-- idx_offers_status
CREATE INDEX idx_offers_status ON public.offers USING btree (status);

-- idx_offers_status_store
CREATE INDEX idx_offers_status_store ON public.offers USING btree (status, store_id);

-- idx_offers_stock
CREATE INDEX idx_offers_stock ON public.offers USING btree (stock_quantity);

-- idx_offers_store
CREATE INDEX idx_offers_store ON public.offers USING btree (store_id);

-- idx_offers_unit
CREATE INDEX idx_offers_unit ON public.offers USING btree (unit);

-- idx_orders_cancel_reason
CREATE INDEX idx_orders_cancel_reason ON public.orders USING btree (cancel_reason);

-- idx_orders_created
CREATE INDEX idx_orders_created ON public.orders USING btree (created_at DESC);

-- idx_orders_status
CREATE INDEX idx_orders_status ON public.orders USING btree (order_status);

-- idx_orders_store
CREATE INDEX idx_orders_store ON public.orders USING btree (store_id);

-- idx_orders_user
CREATE INDEX idx_orders_user ON public.orders USING btree (user_id);

-- idx_ratings_store
CREATE INDEX idx_ratings_store ON public.ratings USING btree (store_id);

-- idx_ratings_user
CREATE INDEX idx_ratings_user ON public.ratings USING btree (user_id);

-- idx_recently_viewed_user
CREATE INDEX idx_recently_viewed_user ON public.recently_viewed USING btree (user_id);

-- idx_search_history_user
CREATE INDEX idx_search_history_user ON public.search_history USING btree (user_id);

-- idx_stores_city
CREATE INDEX idx_stores_city ON public.stores USING btree (city);

-- idx_stores_city_status
CREATE INDEX idx_stores_city_status ON public.stores USING btree (city, status);

-- idx_stores_owner
CREATE INDEX idx_stores_owner ON public.stores USING btree (owner_id);

-- idx_stores_status
CREATE INDEX idx_stores_status ON public.stores USING btree (status);

-- notifications_pkey
CREATE UNIQUE INDEX notifications_pkey ON public.notifications USING btree (notification_id);

-- offers_pkey
CREATE UNIQUE INDEX offers_pkey ON public.offers USING btree (offer_id);

-- orders_pkey
CREATE UNIQUE INDEX orders_pkey ON public.orders USING btree (order_id);

-- payment_settings_pkey
CREATE UNIQUE INDEX payment_settings_pkey ON public.payment_settings USING btree (store_id);

-- pickup_slots_pkey
CREATE UNIQUE INDEX pickup_slots_pkey ON public.pickup_slots USING btree (store_id, slot_ts);

-- platform_settings_pkey
CREATE UNIQUE INDEX platform_settings_pkey ON public.platform_settings USING btree (key);

-- promo_usage_pkey
CREATE UNIQUE INDEX promo_usage_pkey ON public.promo_usage USING btree (usage_id);

-- promocodes_code_key
CREATE UNIQUE INDEX promocodes_code_key ON public.promocodes USING btree (code);

-- promocodes_pkey
CREATE UNIQUE INDEX promocodes_pkey ON public.promocodes USING btree (promo_id);

-- ratings_pkey
CREATE UNIQUE INDEX ratings_pkey ON public.ratings USING btree (rating_id);

-- recently_viewed_pkey
CREATE UNIQUE INDEX recently_viewed_pkey ON public.recently_viewed USING btree (id);

-- referrals_pkey
CREATE UNIQUE INDEX referrals_pkey ON public.referrals USING btree (referral_id);

-- search_history_pkey
CREATE UNIQUE INDEX search_history_pkey ON public.search_history USING btree (id);

-- store_admins_pkey
CREATE UNIQUE INDEX store_admins_pkey ON public.store_admins USING btree (id);

-- store_admins_store_id_user_id_key
CREATE UNIQUE INDEX store_admins_store_id_user_id_key ON public.store_admins USING btree (store_id, user_id);

-- store_payment_integrations_pkey
CREATE UNIQUE INDEX store_payment_integrations_pkey ON public.store_payment_integrations USING btree (id);

-- store_payment_integrations_store_id_provider_key
CREATE UNIQUE INDEX store_payment_integrations_store_id_provider_key ON public.store_payment_integrations USING btree (store_id, provider);

-- stores_pkey
CREATE UNIQUE INDEX stores_pkey ON public.stores USING btree (store_id);

-- users_pkey
CREATE UNIQUE INDEX users_pkey ON public.users USING btree (user_id);

