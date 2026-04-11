"""
Tests for structured logging - verifies log records are emitted correctly.
No file I/O needed: we capture log records in-memory using caplog.
"""

import logging
import pytest
from unittest.mock import MagicMock

from src.logger import get_logger, JsonFormatter, ConsoleFormatter


class TestGetLogger:
    def test_returns_logger_instance(self):
        log = get_logger("test.module")
        assert isinstance(log, logging.Logger)
        assert log.name == "test.module"

    def test_different_names_return_different_loggers(self):
        log_a = get_logger("module.a")
        log_b = get_logger("module.b")
        assert log_a is not log_b

    def test_same_name_returns_same_logger(self):
        log_a = get_logger("module.same")
        log_b = get_logger("module.same")
        assert log_a is log_b


class TestJsonFormatter:
    def _make_record(self, msg="test message", level=logging.INFO, extra=None):
        record = logging.LogRecord(
            name="test.logger", level=level, pathname="", lineno=0,
            msg=msg, args=(), exc_info=None,
        )
        if extra:
            for k, v in extra.items():
                setattr(record, k, v)
        return record

    def test_output_is_valid_json(self):
        import json
        formatter = JsonFormatter()
        record = self._make_record("hello world")
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["msg"] == "hello world"

    def test_json_contains_required_fields(self):
        import json
        formatter = JsonFormatter()
        record = self._make_record("test")
        parsed = json.loads(formatter.format(record))
        assert "ts" in parsed
        assert "level" in parsed
        assert "logger" in parsed
        assert "msg" in parsed

    def test_json_includes_job_id_when_present(self):
        import json
        formatter = JsonFormatter()
        record = self._make_record("test", extra={"job_id": "abc123"})
        parsed = json.loads(formatter.format(record))
        assert parsed["job_id"] == "abc123"

    def test_json_includes_ip_when_present(self):
        import json
        formatter = JsonFormatter()
        record = self._make_record("test", extra={"ip": "1.2.3.4"})
        parsed = json.loads(formatter.format(record))
        assert parsed["ip"] == "1.2.3.4"

    def test_level_name_is_correct(self):
        import json
        formatter = JsonFormatter()
        record = self._make_record("warn test", level=logging.WARNING)
        parsed = json.loads(formatter.format(record))
        assert parsed["level"] == "WARNING"


class TestConsoleFormatter:
    def _make_record(self, msg="test", level=logging.INFO):
        return logging.LogRecord(
            name="test.logger", level=level, pathname="", lineno=0,
            msg=msg, args=(), exc_info=None,
        )

    def test_output_contains_message(self):
        formatter = ConsoleFormatter()
        record = self._make_record("hello output")
        output = formatter.format(record)
        assert "hello output" in output

    def test_output_contains_level(self):
        formatter = ConsoleFormatter()
        record = self._make_record("msg", level=logging.ERROR)
        output = formatter.format(record)
        assert "ERROR" in output

    def test_output_contains_logger_name(self):
        formatter = ConsoleFormatter()
        record = self._make_record("msg")
        output = formatter.format(record)
        assert "test.logger" in output

    def test_output_includes_job_id_when_present(self):
        formatter = ConsoleFormatter()
        record = self._make_record("msg")
        record.job_id = "xyz789"
        output = formatter.format(record)
        assert "xyz789" in output


class TestAnalyzerLogging:
    """Verify that the analyzer emits log records at key points."""

    def test_analyze_logs_llm_call(self, caplog):
        import json
        from unittest.mock import MagicMock
        from src.analysis.analyzer import ArchitectureAnalyzer
        from src.analysis.llm_client import LLMClient, LLMConfig

        mock_response = json.dumps({
            "project_name": "Test", "description": "desc",
            "tech_stack": ["Python"], "layers": [],
            "good_practices": [], "improvement_points": [],
            "validation_questions": []
        })

        config = LLMConfig(provider="openai", api_key="sk-test", model="gpt-4o")
        client = LLMClient.__new__(LLMClient)
        client.config = config
        client._client = MagicMock()
        client.chat = MagicMock(return_value=mock_response)

        from src.ingestion.context import ProjectContext
        from pathlib import Path
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "main.py").write_text("def main(): pass\n" * 5)
            ctx = ProjectContext.from_path(tmp)

        with caplog.at_level(logging.INFO, logger="src.analysis.analyzer"):
            analyzer = ArchitectureAnalyzer(client=client, language="pt")
            analyzer.analyze(ctx)

        messages = [r.message for r in caplog.records]
        assert any("LLM" in m for m in messages)
