"""Add full-text search columns and indexes

Revision ID: 002_add_fts
Revises: 001_initial_schema
Create Date: 2025-11-26

This migration adds PostgreSQL Full-Text Search (FTS) support:
- tsvector columns for searchable content
- GIN indexes for fast FTS queries
- Triggers for automatic tsvector updates
"""
from alembic import op

# revision identifiers
revision = '002_add_fts'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add FTS columns, indexes, and triggers."""

    # Add tsvector columns
    op.execute("""
        ALTER TABLE offers 
        ADD COLUMN IF NOT EXISTS search_vector tsvector;
    """)

    op.execute("""
        ALTER TABLE stores 
        ADD COLUMN IF NOT EXISTS search_vector tsvector;
    """)

    # Create GIN indexes for fast FTS
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_offers_search 
        ON offers USING GIN(search_vector);
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_stores_search 
        ON stores USING GIN(search_vector);
    """)

    # Create function to update offers search vector
    op.execute("""
        CREATE OR REPLACE FUNCTION offers_search_vector_update() 
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.search_vector := 
                setweight(to_tsvector('russian', COALESCE(NEW.title, '')), 'A') ||
                setweight(to_tsvector('russian', COALESCE(NEW.description, '')), 'B') ||
                setweight(to_tsvector('russian', COALESCE(NEW.category, '')), 'C');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create function to update stores search vector
    op.execute("""
        CREATE OR REPLACE FUNCTION stores_search_vector_update() 
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.search_vector := 
                setweight(to_tsvector('russian', COALESCE(NEW.name, '')), 'A') ||
                setweight(to_tsvector('russian', COALESCE(NEW.description, '')), 'B') ||
                setweight(to_tsvector('russian', COALESCE(NEW.category, '')), 'C') ||
                setweight(to_tsvector('russian', COALESCE(NEW.address, '')), 'D');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create triggers
    op.execute("""
        DROP TRIGGER IF EXISTS offers_search_vector_trigger ON offers;
        CREATE TRIGGER offers_search_vector_trigger
        BEFORE INSERT OR UPDATE OF title, description, category
        ON offers
        FOR EACH ROW
        EXECUTE FUNCTION offers_search_vector_update();
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS stores_search_vector_trigger ON stores;
        CREATE TRIGGER stores_search_vector_trigger
        BEFORE INSERT OR UPDATE OF name, description, category, address
        ON stores
        FOR EACH ROW
        EXECUTE FUNCTION stores_search_vector_update();
    """)

    # Update existing rows
    op.execute("""
        UPDATE offers SET search_vector = 
            setweight(to_tsvector('russian', COALESCE(title, '')), 'A') ||
            setweight(to_tsvector('russian', COALESCE(description, '')), 'B') ||
            setweight(to_tsvector('russian', COALESCE(category, '')), 'C')
        WHERE search_vector IS NULL;
    """)

    op.execute("""
        UPDATE stores SET search_vector = 
            setweight(to_tsvector('russian', COALESCE(name, '')), 'A') ||
            setweight(to_tsvector('russian', COALESCE(description, '')), 'B') ||
            setweight(to_tsvector('russian', COALESCE(category, '')), 'C') ||
            setweight(to_tsvector('russian', COALESCE(address, '')), 'D')
        WHERE search_vector IS NULL;
    """)


def downgrade() -> None:
    """Remove FTS columns, indexes, and triggers."""

    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS offers_search_vector_trigger ON offers;")
    op.execute("DROP TRIGGER IF EXISTS stores_search_vector_trigger ON stores;")

    # Drop functions
    op.execute("DROP FUNCTION IF EXISTS offers_search_vector_update();")
    op.execute("DROP FUNCTION IF EXISTS stores_search_vector_update();")

    # Drop indexes
    op.execute("DROP INDEX IF EXISTS idx_offers_search;")
    op.execute("DROP INDEX IF EXISTS idx_stores_search;")

    # Drop columns
    op.execute("ALTER TABLE offers DROP COLUMN IF EXISTS search_vector;")
    op.execute("ALTER TABLE stores DROP COLUMN IF EXISTS search_vector;")
