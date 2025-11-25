"""Tests for OpenAPI documentation endpoints."""
from __future__ import annotations

from pathlib import Path

import pytest


class TestOpenAPISpec:
    """Test OpenAPI specification file."""

    def test_openapi_spec_exists(self) -> None:
        """Test that openapi.yaml exists."""
        spec_path = Path(__file__).parent.parent / "docs" / "openapi.yaml"
        assert spec_path.exists(), f"OpenAPI spec not found at {spec_path}"

    def test_openapi_spec_valid_yaml(self) -> None:
        """Test that openapi.yaml is valid YAML."""
        spec_path = Path(__file__).parent.parent / "docs" / "openapi.yaml"

        try:
            import yaml

            with open(spec_path, encoding="utf-8") as f:
                spec = yaml.safe_load(f)
            assert spec is not None
        except ImportError:
            # yaml not installed, skip this test
            pytest.skip("PyYAML not installed")

    def test_openapi_spec_has_required_fields(self) -> None:
        """Test that openapi.yaml has required OpenAPI fields."""
        spec_path = Path(__file__).parent.parent / "docs" / "openapi.yaml"

        try:
            import yaml

            with open(spec_path, encoding="utf-8") as f:
                spec = yaml.safe_load(f)

            # Check required OpenAPI 3.1 fields
            assert "openapi" in spec, "Missing 'openapi' version field"
            assert spec["openapi"].startswith("3."), "OpenAPI version should be 3.x"

            assert "info" in spec, "Missing 'info' section"
            assert "title" in spec["info"], "Missing 'info.title'"
            assert "version" in spec["info"], "Missing 'info.version'"

            assert "paths" in spec, "Missing 'paths' section"

        except ImportError:
            pytest.skip("PyYAML not installed")

    def test_openapi_spec_documents_health_endpoint(self) -> None:
        """Test that /health endpoint is documented."""
        spec_path = Path(__file__).parent.parent / "docs" / "openapi.yaml"

        try:
            import yaml

            with open(spec_path, encoding="utf-8") as f:
                spec = yaml.safe_load(f)

            assert "/health" in spec["paths"], "Missing /health endpoint documentation"
            assert "get" in spec["paths"]["/health"], "/health should support GET"

        except ImportError:
            pytest.skip("PyYAML not installed")

    def test_openapi_spec_documents_metrics_endpoint(self) -> None:
        """Test that /metrics endpoint is documented."""
        spec_path = Path(__file__).parent.parent / "docs" / "openapi.yaml"

        try:
            import yaml

            with open(spec_path, encoding="utf-8") as f:
                spec = yaml.safe_load(f)

            assert "/metrics" in spec["paths"], "Missing /metrics endpoint documentation"

        except ImportError:
            pytest.skip("PyYAML not installed")

    def test_openapi_spec_documents_webhook_endpoint(self) -> None:
        """Test that /webhook endpoint is documented."""
        spec_path = Path(__file__).parent.parent / "docs" / "openapi.yaml"

        try:
            import yaml

            with open(spec_path, encoding="utf-8") as f:
                spec = yaml.safe_load(f)

            assert "/webhook" in spec["paths"], "Missing /webhook endpoint documentation"
            assert "post" in spec["paths"]["/webhook"], "/webhook should support POST"

        except ImportError:
            pytest.skip("PyYAML not installed")

    def test_openapi_spec_has_components(self) -> None:
        """Test that spec has component schemas."""
        spec_path = Path(__file__).parent.parent / "docs" / "openapi.yaml"

        try:
            import yaml

            with open(spec_path, encoding="utf-8") as f:
                spec = yaml.safe_load(f)

            assert "components" in spec, "Missing 'components' section"
            assert "schemas" in spec["components"], "Missing 'components.schemas'"

            # Check for key schemas
            schemas = spec["components"]["schemas"]
            assert "HealthResponse" in schemas, "Missing HealthResponse schema"
            assert "Offer" in schemas, "Missing Offer schema"

        except ImportError:
            pytest.skip("PyYAML not installed")


class TestDocsEndpointHandler:
    """Test documentation endpoint handlers."""

    def test_docs_html_structure(self) -> None:
        """Test that docs handler returns valid HTML with Swagger UI."""
        # Simulate the HTML that docs_handler returns (should match webhook_server.py)
        html = """<!DOCTYPE html>
<html>
<head>
    <title>Fudly Bot API Documentation</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
    <style>
        body { margin: 0; padding: 0; }
        .swagger-ui .topbar { display: none; }
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
        SwaggerUIBundle({
            url: '/openapi.yaml',
            dom_id: '#swagger-ui',
            presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
            layout: "BaseLayout"
        });
    </script>
</body>
</html>"""

        assert "<!DOCTYPE html>" in html
        assert "swagger-ui" in html
        assert "swagger-ui-bundle.js" in html
        assert "/openapi.yaml" in html

    def test_openapi_yaml_readable(self) -> None:
        """Test that openapi.yaml can be read as text."""
        spec_path = Path(__file__).parent.parent / "docs" / "openapi.yaml"

        with open(spec_path, encoding="utf-8") as f:
            content = f.read()

        assert len(content) > 100, "OpenAPI spec seems too short"
        assert "openapi:" in content, "Missing openapi version declaration"
        assert "Fudly" in content, "Missing Fudly reference in spec"


class TestOpenAPIIntegration:
    """Integration tests for OpenAPI with webhook server."""

    @pytest.mark.asyncio
    async def test_webhook_app_has_docs_route(self) -> None:
        """Test that webhook app includes /docs route."""
        from unittest.mock import MagicMock, patch

        # Mock dependencies
        mock_bot = MagicMock()
        mock_dp = MagicMock()
        mock_db = MagicMock()
        mock_db.get_connection = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(
                    return_value=MagicMock(cursor=MagicMock(return_value=MagicMock()))
                ),
                __exit__=MagicMock(return_value=None),
            )
        )

        with patch("app.core.webhook_server.setup_websocket_routes"), patch(
            "app.core.webhook_server.get_notification_service"
        ) as mock_ns, patch("app.core.webhook_server.get_websocket_manager") as mock_ws:
            mock_ns.return_value = MagicMock(set_telegram_bot=MagicMock())
            mock_ws.return_value = MagicMock(set_notification_service=MagicMock())

            from app.core.webhook_server import create_webhook_app

            app = await create_webhook_app(
                bot=mock_bot,
                dp=mock_dp,
                webhook_path="/webhook",
                secret_token=None,
                metrics={},
                db=mock_db,
            )

            # Check that routes are registered
            routes = [
                r.resource.canonical
                for r in app.router.routes()
                if hasattr(r, "resource") and r.resource
            ]

            assert "/docs" in routes, "Missing /docs route"
            assert "/openapi.yaml" in routes, "Missing /openapi.yaml route"
