"""
Tests for Alembic migrations.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Check if optional dependencies are available
try:
    import sqlalchemy

    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

try:
    from alembic.config import Config  # noqa: F401

    HAS_ALEMBIC = True
except ImportError:
    HAS_ALEMBIC = False


def load_local_models():
    """Load models from local migrations_alembic folder to avoid conflict with alembic package."""
    if not HAS_SQLALCHEMY:
        pytest.skip("sqlalchemy not installed")
    models_path = PROJECT_ROOT / "migrations_alembic" / "models.py"
    spec = importlib.util.spec_from_file_location("local_models", models_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load models from {models_path}")
    models = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(models)
    return models


class TestAlembicStructure:
    """Test that Alembic structure is correct."""

    def test_alembic_ini_exists(self):
        """Test alembic.ini exists."""
        ini_path = PROJECT_ROOT / "alembic.ini"
        assert ini_path.exists(), "alembic.ini not found"

    def test_alembic_env_exists(self):
        """Test migrations_alembic/env.py exists."""
        env_path = PROJECT_ROOT / "migrations_alembic" / "env.py"
        assert env_path.exists(), "migrations_alembic/env.py not found"

    def test_alembic_models_exists(self):
        """Test migrations_alembic/models.py exists."""
        models_path = PROJECT_ROOT / "migrations_alembic" / "models.py"
        assert models_path.exists(), "migrations_alembic/models.py not found"

    def test_versions_directory_exists(self):
        """Test migrations_alembic/versions directory exists."""
        versions_path = PROJECT_ROOT / "migrations_alembic" / "versions"
        assert versions_path.exists(), "migrations_alembic/versions directory not found"

    def test_initial_migration_exists(self):
        """Test that at least one migration exists."""
        versions_path = PROJECT_ROOT / "migrations_alembic" / "versions"
        migrations = list(versions_path.glob("*.py"))
        assert len(migrations) > 0, "No migrations found"


class TestAlembicModels:
    """Test SQLAlchemy models are importable."""

    def test_models_import(self):
        """Test models can be imported."""
        models = load_local_models()
        assert hasattr(models, "Base")
        assert models.Base is not None

    def test_all_tables_defined(self):
        """Test all expected tables are defined."""
        models = load_local_models()

        expected_models = [
            "User",
            "Store",
            "Offer",
            "Order",
            "Booking",
            "PaymentSettings",
            "Notification",
            "Rating",
            "Favorite",
            "Promocode",
            "PromoUsage",
            "Referral",
            "FSMState",
            "PlatformSettings",
            "PickupSlot",
        ]

        for model_name in expected_models:
            assert hasattr(models, model_name), f"Model {model_name} not found"
            model_class = getattr(models, model_name)
            assert hasattr(model_class, "__tablename__"), f"{model_name} missing __tablename__"

    def test_user_model_columns(self):
        """Test User model has expected columns."""
        models = load_local_models()
        columns = [c.name for c in models.User.__table__.columns]

        expected = ["user_id", "username", "city", "role", "language", "notifications_enabled"]
        for col in expected:
            assert col in columns, f"User missing column: {col}"

    def test_store_model_columns(self):
        """Test Store model has expected columns."""
        models = load_local_models()
        columns = [c.name for c in models.Store.__table__.columns]

        expected = ["store_id", "owner_id", "name", "category", "city", "address", "status"]
        for col in expected:
            assert col in columns, f"Store missing column: {col}"

    def test_offer_model_columns(self):
        """Test Offer model has expected columns."""
        models = load_local_models()
        columns = [c.name for c in models.Offer.__table__.columns]

        expected = ["offer_id", "store_id", "title", "original_price", "discount_price", "quantity"]
        for col in expected:
            assert col in columns, f"Offer missing column: {col}"

    def test_booking_model_columns(self):
        """Test Booking model has expected columns."""
        models = load_local_models()
        columns = [c.name for c in models.Booking.__table__.columns]

        expected = ["booking_id", "user_id", "offer_id", "booking_code", "status"]
        for col in expected:
            assert col in columns, f"Booking missing column: {col}"


class TestMigrationScript:
    """Test migration helper script."""

    def test_migrate_script_exists(self):
        """Test scripts/migrate.py exists."""
        from pathlib import Path

        script_path = Path(__file__).parent.parent / "scripts" / "migrate.py"
        assert script_path.exists(), "scripts/migrate.py not found"

    @pytest.mark.skipif(not HAS_ALEMBIC, reason="alembic not installed")
    def test_migrate_script_importable(self):
        """Test migration script is importable."""
        from scripts.migrate import (
            current,
            downgrade,
            get_alembic_config,
            heads,
            history,
            main,
            revision,
            stamp,
            upgrade,
        )

        assert callable(get_alembic_config)
        assert callable(upgrade)
        assert callable(downgrade)
        assert callable(current)
        assert callable(history)
        assert callable(revision)
        assert callable(stamp)
        assert callable(heads)
        assert callable(main)


class TestAlembicConfig:
    """Test Alembic configuration."""

    @pytest.mark.skipif(not HAS_ALEMBIC, reason="alembic not installed")
    def test_alembic_config_loadable(self):
        """Test alembic.ini can be loaded."""
        from alembic.config import Config  # type: ignore

        ini_path = PROJECT_ROOT / "alembic.ini"
        config = Config(str(ini_path))

        assert config is not None
        assert config.get_main_option("script_location") == "migrations_alembic"

    @pytest.mark.skipif(not HAS_ALEMBIC, reason="alembic not installed")
    def test_env_handles_postgres_url(self):
        """Test env.py handles postgres:// URLs."""
        import os

        original = os.environ.get("DATABASE_URL")

        try:
            # Set postgres:// URL (Railway format)
            os.environ["DATABASE_URL"] = "postgres://user:pass@host:5432/db"

            from scripts.migrate import get_alembic_config

            config = get_alembic_config()

            # Should be converted to postgresql://
            url = config.get_main_option("sqlalchemy.url")
            if url:  # Only check if URL was set
                assert not url.startswith(
                    "postgres://"
                ), "Should convert postgres:// to postgresql://"
        finally:
            if original:
                os.environ["DATABASE_URL"] = original
            elif "DATABASE_URL" in os.environ:
                del os.environ["DATABASE_URL"]


class TestInitialMigration:
    """Test initial migration content."""

    def test_initial_migration_has_tables(self):
        """Test initial migration creates all tables."""
        from pathlib import Path

        versions_path = Path(__file__).parent.parent / "migrations_alembic" / "versions"
        migrations = list(versions_path.glob("*initial*.py"))

        assert len(migrations) > 0, "Initial migration not found"

        content = migrations[0].read_text()

        # Check key tables are created
        tables = ["users", "stores", "offers", "bookings", "ratings", "favorites", "notifications"]

        for table in tables:
            assert (
                f"'{table}'" in content or f'"{table}"' in content
            ), f"Table {table} not found in initial migration"

    def test_initial_migration_has_upgrade_downgrade(self):
        """Test migration has upgrade and downgrade functions."""
        from pathlib import Path

        versions_path = Path(__file__).parent.parent / "migrations_alembic" / "versions"
        migrations = list(versions_path.glob("*initial*.py"))

        assert len(migrations) > 0

        content = migrations[0].read_text()

        assert "def upgrade()" in content, "upgrade() function not found"
        assert "def downgrade()" in content, "downgrade() function not found"
