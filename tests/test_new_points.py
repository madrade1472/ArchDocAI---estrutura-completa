"""
Tests for the improvements from the second review round:
- Pydantic schema validation
- LLM retry logic
- Log rotation config
- Repo size helper
"""

import json
import logging
import time
from unittest.mock import MagicMock, patch, call
import pytest


# ---------------------------------------------------------------------------
# Pydantic schema validation
# ---------------------------------------------------------------------------

class TestLLMResponseSchema:
    def _schema(self):
        from src.analysis.analyzer import LLMResponseSchema
        return LLMResponseSchema

    def test_valid_full_response(self):
        Schema = self._schema()
        data = {
            "project_name": "MyApp",
            "description": "A test app",
            "tech_stack": ["Python"],
            "layers": [
                {
                    "id": "l1", "name": "Ingestion", "description": "reads data",
                    "color": "#2d6a4f",
                    "components": [
                        {"name": "Scanner", "description": "scans", "tech": "Python", "type": "process"}
                    ],
                    "connections_to": []
                }
            ],
            "good_practices": ["Uses IaC"],
            "improvement_points": ["Add tests"],
            "validation_questions": ["Is layer 1 correct?"],
        }
        result = Schema.model_validate(data)
        assert result.project_name == "MyApp"
        assert len(result.layers) == 1
        assert result.layers[0].components[0].type == "process"

    def test_invalid_color_is_replaced_with_default(self):
        Schema = self._schema()
        data = {
            "project_name": "X",
            "layers": [{"id": "l1", "name": "L1", "color": "notacolor", "components": [], "connections_to": []}]
        }
        result = Schema.model_validate(data)
        assert result.layers[0].color == "#4578a0"

    def test_missing_optional_fields_use_defaults(self):
        Schema = self._schema()
        result = Schema.model_validate({})
        assert result.project_name == "Unknown Project"
        assert result.tech_stack == []
        assert result.layers == []

    def test_invalid_component_type_raises(self):
        from pydantic import ValidationError
        Schema = self._schema()
        with pytest.raises(ValidationError):
            Schema.model_validate({
                "layers": [{"id": "l1", "name": "L", "components": [
                    {"name": "X", "type": "invalid_type"}
                ]}]
            })

    def test_build_result_uses_pydantic(self):
        from src.analysis.analyzer import ArchitectureAnalyzer
        from src.analysis.llm_client import LLMClient, LLMConfig

        config = LLMConfig(provider="openai", api_key="sk-test", model="gpt-4o")
        client = LLMClient.__new__(LLMClient)
        client.config = config
        client.chat = MagicMock(return_value=json.dumps({
            "project_name": "Validated",
            "layers": [{"id": "l1", "name": "Layer A", "color": "bad", "components": []}],
        }))

        from src.ingestion.context import ProjectContext
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "app.py").write_text("x = 1\n" * 20)
            ctx = ProjectContext.from_path(tmp)

        az = ArchitectureAnalyzer(client=client, language="pt")
        result = az.analyze(ctx)
        # Color was invalid - should have been coerced to default
        assert result.layers[0]["color"] == "#4578a0"


# ---------------------------------------------------------------------------
# LLM retry with backoff
# ---------------------------------------------------------------------------

class TestLLMRetry:
    def _make_client(self):
        from src.analysis.llm_client import LLMClient, LLMConfig
        config = LLMConfig(provider="openai", api_key="sk-test", model="gpt-4o")
        client = LLMClient.__new__(LLMClient)
        client.config = config
        client._client = MagicMock()
        return client

    def test_succeeds_on_first_try(self):
        client = self._make_client()
        client._call = MagicMock(return_value="ok response")
        result = client.chat("system", "user")
        assert result == "ok response"
        assert client._call.call_count == 1

    def test_retries_on_429(self):
        from src.analysis.llm_client import LLMClient, LLMConfig

        class FakeRateLimit(Exception):
            status_code = 429

        client = self._make_client()
        client._call = MagicMock(side_effect=[FakeRateLimit(), FakeRateLimit(), "ok on third"])

        with patch("time.sleep"):
            result = client.chat("system", "user")

        assert result == "ok on third"
        assert client._call.call_count == 3

    def test_raises_immediately_on_non_retryable_error(self):
        class FakeAuthError(Exception):
            status_code = 401

        client = self._make_client()
        client._call = MagicMock(side_effect=FakeAuthError())

        with pytest.raises(FakeAuthError):
            client.chat("system", "user")

        assert client._call.call_count == 1

    def test_raises_after_max_retries_exhausted(self):
        from src.analysis.llm_client import _MAX_RETRIES

        class FakeServerError(Exception):
            status_code = 503

        client = self._make_client()
        client._call = MagicMock(side_effect=FakeServerError())

        with patch("time.sleep"):
            with pytest.raises(FakeServerError):
                client.chat("system", "user")

        assert client._call.call_count == _MAX_RETRIES

    def test_api_key_not_in_error_message(self, caplog):
        class FakeBadRequest(Exception):
            status_code = 400
            def __str__(self): return "bad request error"

        client = self._make_client()
        client._call = MagicMock(side_effect=FakeBadRequest())

        with caplog.at_level(logging.ERROR):
            with pytest.raises(FakeBadRequest):
                client.chat("system", "user")

        for record in caplog.records:
            assert "sk-test" not in record.getMessage()


# ---------------------------------------------------------------------------
# Log rotation
# ---------------------------------------------------------------------------

class TestLogRotation:
    def test_setup_uses_rotating_file_handler(self, tmp_path):
        import logging.handlers
        from src.logger import setup_logging, _configured
        import src.logger as lg

        # Reset configured flag for this test
        lg._configured = False
        setup_logging(log_dir=str(tmp_path))

        root = logging.getLogger()
        handler_types = [type(h).__name__ for h in root.handlers]
        assert "RotatingFileHandler" in handler_types

        # Cleanup: reset for other tests
        lg._configured = False
        for h in root.handlers[:]:
            root.removeHandler(h)


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_health_returns_ok(self):
        from fastapi.testclient import TestClient
        from web.app import create_app
        app = create_app()
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_quota_endpoint_returns_limit_info(self):
        from fastapi.testclient import TestClient
        from web.app import create_app
        app = create_app()
        client = TestClient(app)
        resp = client.get("/api/quota")
        assert resp.status_code == 200
        data = resp.json()
        assert "remaining" in data
        assert "limit" in data


# ---------------------------------------------------------------------------
# git_url validation
# ---------------------------------------------------------------------------

class TestGitUrlValidation:
    def _post_analyze(self, git_url: str, extra_data: dict | None = None):
        from fastapi.testclient import TestClient
        from web.app import create_app
        app = create_app()
        client = TestClient(app)
        data = {
            "provider": "openai",
            "api_key": "sk-test",
            "model": "gpt-4o",
            "git_url": git_url,
        }
        if extra_data:
            data.update(extra_data)
        return client.post("/api/analyze", data=data)

    def test_https_url_is_accepted(self):
        resp = self._post_analyze("https://github.com/user/repo.git")
        # 202 = queued, not 400 validation error
        assert resp.status_code == 202

    def test_ssh_url_is_accepted(self):
        resp = self._post_analyze("git@github.com:user/repo.git")
        assert resp.status_code == 202

    def test_file_scheme_is_rejected(self):
        resp = self._post_analyze("file:///etc/passwd")
        assert resp.status_code == 400

    def test_local_path_is_rejected(self):
        resp = self._post_analyze("/home/user/myrepo")
        assert resp.status_code == 400

    def test_empty_url_is_rejected(self):
        resp = self._post_analyze("   ")
        assert resp.status_code == 400

    def test_custom_provider_without_base_url_is_rejected(self):
        resp = self._post_analyze(
            "https://github.com/user/repo.git",
            {"provider": "custom"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Mermaid colors
# ---------------------------------------------------------------------------

class TestMermaidColors:
    def _make_result(self, layers):
        from src.analysis.analyzer import AnalysisResult
        return AnalysisResult(
            raw_json={},
            project_name="Test",
            description="",
            tech_stack=[],
            layers=layers,
            good_practices=[],
            improvement_points=[],
            validation_questions=[],
        )

    def test_mermaid_includes_style_for_each_layer(self):
        from src.analysis.diagram import DiagramGenerator
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            gen = DiagramGenerator(output_dir=tmp)
            result = self._make_result([
                {"id": "l1", "name": "Ingestion", "color": "#2d6a4f", "components": [], "connections_to": []},
                {"id": "l2", "name": "Processing", "color": "#457b9d", "components": [], "connections_to": []},
            ])
            mermaid = gen.generate_mermaid(result)
        assert "style l1 fill:#2d6a4f" in mermaid
        assert "style l2 fill:#457b9d" in mermaid

    def test_mermaid_components_get_tinted_style(self):
        from src.analysis.diagram import DiagramGenerator
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            gen = DiagramGenerator(output_dir=tmp)
            result = self._make_result([
                {"id": "l1", "name": "Layer", "color": "#2d6a4f",
                 "components": [{"name": "Scanner", "description": "", "tech": "", "type": "process"}],
                 "connections_to": []},
            ])
            mermaid = gen.generate_mermaid(result)
        # ID format: {layer_id}_{index}_{slug}
        assert "style l1_0_scanner" in mermaid
        assert "#2d6a4f99" in mermaid

    def test_mermaid_fallback_color_when_missing(self):
        from src.analysis.diagram import DiagramGenerator, DEFAULT_COLORS
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            gen = DiagramGenerator(output_dir=tmp)
            result = self._make_result([
                {"id": "l1", "name": "Layer", "color": None, "components": [], "connections_to": []},
            ])
            mermaid = gen.generate_mermaid(result)
        assert f"style l1 fill:{DEFAULT_COLORS[0]}" in mermaid
