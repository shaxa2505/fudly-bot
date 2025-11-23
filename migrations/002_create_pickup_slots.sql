-- Migration: create pickup_slots table for slot capacity management
-- Supports SQLite and PostgreSQL

-- PostgreSQL
CREATE TABLE IF NOT EXISTS pickup_slots (
    slot_id SERIAL PRIMARY KEY,
    store_id INTEGER NOT NULL REFERENCES stores(store_id),
    slot_ts TIMESTAMP NOT NULL,
    capacity INTEGER NOT NULL DEFAULT 5,
    reserved INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(store_id, slot_ts)
);
CREATE INDEX IF NOT EXISTS idx_pickup_slots_store_ts ON pickup_slots(store_id, slot_ts);

-- SQLite (the script runner should execute the relevant parts for SQLite)
-- SQLite
CREATE TABLE IF NOT EXISTS pickup_slots (
    slot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER NOT NULL,
    slot_ts TEXT NOT NULL,
    capacity INTEGER NOT NULL DEFAULT 5,
    reserved INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(store_id, slot_ts)
);
CREATE INDEX IF NOT EXISTS idx_pickup_slots_store_ts ON pickup_slots(store_id, slot_ts);
