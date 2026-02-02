"""Shared pytest fixtures for database-backed tests."""
from __future__ import annotations

import os
from urllib.parse import urlparse
from unittest import mock
from unittest.mock import MagicMock

import pytest
from psycopg import sql

from database_pg import Database


def _get_test_db_url() -> str | None:
    return os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")


def _is_safe_db_url(db_url: str) -> bool:
    """Allow only local/test hosts unless explicitly overridden."""
    parsed = urlparse(db_url)
    host = (parsed.hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "postgres", "db"}


def _truncate_all_tables(db: Database) -> None:
    """Remove all rows from public tables to keep tests isolated."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        rows = cursor.fetchall()
        tables = [row[0] for row in rows]
        if not tables:
            return
        table_list = sql.SQL(", ").join(sql.Identifier(name) for name in tables)
        cursor.execute(sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(table_list))


@pytest.fixture(scope="session")
def postgres_db() -> Database:
    """Session-scoped PostgreSQL database handle for tests."""
    db_url = _get_test_db_url()
    if not db_url:
        pytest.skip("TEST_DATABASE_URL (or DATABASE_URL) is required for DB tests")
    if not _is_safe_db_url(db_url) and os.getenv("ALLOW_TEST_DB_RESET") != "1":
        pytest.skip(
            "Refusing to run DB tests against non-local database. "
            "Set ALLOW_TEST_DB_RESET=1 to override."
        )

    # Ensure schema is initialized for tests
    os.environ["RUN_DB_MIGRATIONS"] = "1"

    db = Database(db_url)
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass


@pytest.fixture()
def db(postgres_db: Database) -> Database:
    """Function-scoped database fixture with clean tables."""
    _truncate_all_tables(postgres_db)
    return postgres_db


@pytest.fixture(scope="session", autouse=True)
def _test_env_vars() -> None:
    """Provide minimal env vars required for imports in tests."""
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        os.environ["TELEGRAM_BOT_TOKEN"] = "TEST_TOKEN"
    if not os.getenv("ADMIN_ID"):
        os.environ["ADMIN_ID"] = "1"


@pytest.fixture()
async def aiohttp_client():
    """Minimal aiohttp_client fixture to avoid pytest-aiohttp dependency."""
    clients: list[object] = []

    async def _make_client(app):
        from aiohttp.test_utils import TestClient, TestServer

        server = TestServer(app)
        client = TestClient(server)
        await client.start_server()
        clients.append(client)
        return client

    try:
        yield _make_client
    finally:
        for client in clients:
            await client.close()


@pytest.fixture()
async def app():
    """Webhook app fixture for Mini App API tests."""
    from unittest.mock import patch

    import app.core.webhook_server as webhook_server
    from app.core.webhook_server import create_webhook_app

    prev_auth = getattr(webhook_server, "_get_authenticated_user_id", None)

    def _default_auth(_request):
        return 123

    webhook_server._get_authenticated_user_id = _default_auth

    orig_build = webhook_server.build_authenticated_user_id

    def _build_authenticated_user_id(_bot_token: str):
        def _get_authenticated_user_id(request):
            func = getattr(webhook_server, "_get_authenticated_user_id", None)
            if callable(func):
                return func(request)
            return None

        return _get_authenticated_user_id

    webhook_server.build_authenticated_user_id = _build_authenticated_user_id

    bot = MagicMock()
    bot.token = os.getenv("TELEGRAM_BOT_TOKEN", "TEST_TOKEN")
    dp = MagicMock()
    db_mock = MagicMock()

    # Stub DB connection for health check
    cursor = MagicMock()
    cursor.execute.return_value = None
    cursor.fetchone.return_value = (1,)
    conn = MagicMock()
    conn.cursor.return_value = cursor
    ctx = MagicMock()
    ctx.__enter__.return_value = conn
    ctx.__exit__.return_value = None
    db_mock.get_connection.return_value = ctx

    with patch("app.core.webhook_server.setup_websocket_routes"), patch(
        "app.core.webhook_server.get_notification_service"
    ) as mock_ns, patch("app.core.webhook_server.get_websocket_manager") as mock_ws:
        mock_ns.return_value = MagicMock(set_telegram_bot=MagicMock())
        mock_ws.return_value = MagicMock(set_notification_service=MagicMock())

        app_instance = await create_webhook_app(
            bot=bot,
            dp=dp,
            webhook_path="/webhook",
            secret_token=None,
            metrics={},
            db=db_mock,
        )

        try:
            yield app_instance
        finally:
            webhook_server.build_authenticated_user_id = orig_build
            if prev_auth is None:
                delattr(webhook_server, "_get_authenticated_user_id")
            else:
                webhook_server._get_authenticated_user_id = prev_auth


class _Mocker:
    """Minimal pytest-mock replacement for this test suite."""

    Mock = mock.Mock
    AsyncMock = mock.AsyncMock

    def __init__(self) -> None:
        self._patches: list[mock._patch] = []

    def patch(self, target: str, *args, **kwargs):
        patcher = mock.patch(target, *args, **kwargs)
        started = patcher.start()
        self._patches.append(patcher)
        return started

    def stopall(self) -> None:
        for patcher in reversed(self._patches):
            patcher.stop()
        self._patches = []


@pytest.fixture()
def mocker():
    """Fixture compatible with pytest-mock's mocker for local tests."""
    instance = _Mocker()
    try:
        yield instance
    finally:
        instance.stopall()
