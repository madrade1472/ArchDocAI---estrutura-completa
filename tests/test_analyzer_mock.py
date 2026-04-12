"""
Tests for ArchitectureAnalyzer using a mocked LLM client.
The LLM is never called - responses are injected via unittest.mock.
"""

import json
from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest

from src.analysis.analyzer import ArchitectureAnalyzer, AnalysisResult
from src.analysis.llm_client import LLMClient, LLMConfig
from src.ingestion.context import ProjectContext


MOCK_ANALYSIS_RESPONSE = json.dumps({
    "project_name": "DataPlatform",
    "description": "A modern data platform on AWS using Medallion architecture.",
    "tech_stack": ["Python", "AWS S3", "Glue", "Terraform"],
    "layers": [
        {
            "id": "layer_1",
            "name": "Ingestion",
            "description": "Reads raw data from sources.",
            "color": "#2d6a4f",
            "components": [
                {"name": "S3 Raw", "description": "Raw data lake", "tech": "AWS S3", "type": "store"}
            ],
            "connections_to": ["layer_2"]
        },
        {
            "id": "layer_2",
            "name": "Processing",
            "description": "Transforms and enriches data.",
            "color": "#1d3557",
            "components": [
                {"name": "AWS Glue", "description": "ETL jobs", "tech": "AWS Glue", "type": "process"}
            ],
            "connections_to": []
        }
    ],
    "good_practices": ["Uses IaC with Terraform", "Medallion architecture"],
    "improvement_points": ["Add data quality checks", "Add unit tests for Glue jobs"],
    "validation_questions": [
        "Is the raw layer partitioned by date?",
        "Are Glue jobs scheduled or event-driven?"
    ]
})


@pytest.fixture
def mock_client() -> LLMClient:
    config = LLMConfig(provider="openai", api_key="sk-test", model="gpt-4o")
    client = LLMClient.__new__(LLMClient)
    client.config = config
    client._client = MagicMock()
    client.chat = MagicMock(return_value=MOCK_ANALYSIS_RESPONSE)
    return client


@pytest.fixture
def sample_context(tmp_path: Path) -> ProjectContext:
    (tmp_path / "main.py").write_text("# entrypoint\n" * 20)
    (tmp_path / "pipeline.sql").write_text("SELECT * FROM raw_events;\n" * 10)
    return ProjectContext.from_path(str(tmp_path), project_name="DataPlatform")


class TestArchitectureAnalyzer:
    def test_analyze_returns_correct_project_name(self, mock_client, sample_context):
        analyzer = ArchitectureAnalyzer(client=mock_client, language="pt")
        result = analyzer.analyze(sample_context)
        assert result.project_name == "DataPlatform"

    def test_analyze_returns_layers(self, mock_client, sample_context):
        analyzer = ArchitectureAnalyzer(client=mock_client, language="pt")
        result = analyzer.analyze(sample_context)
        assert len(result.layers) == 2
        assert result.layers[0]["name"] == "Ingestion"
        assert result.layers[1]["name"] == "Processing"

    def test_analyze_returns_tech_stack(self, mock_client, sample_context):
        analyzer = ArchitectureAnalyzer(client=mock_client, language="pt")
        result = analyzer.analyze(sample_context)
        assert "Python" in result.tech_stack
        assert "Terraform" in result.tech_stack

    def test_analyze_returns_good_practices(self, mock_client, sample_context):
        analyzer = ArchitectureAnalyzer(client=mock_client, language="pt")
        result = analyzer.analyze(sample_context)
        assert len(result.good_practices) > 0

    def test_analyze_returns_improvement_points(self, mock_client, sample_context):
        analyzer = ArchitectureAnalyzer(client=mock_client, language="pt")
        result = analyzer.analyze(sample_context)
        assert len(result.improvement_points) > 0

    def test_analyze_returns_validation_questions(self, mock_client, sample_context):
        analyzer = ArchitectureAnalyzer(client=mock_client, language="pt")
        result = analyzer.analyze(sample_context)
        assert len(result.validation_questions) == 2

    def test_llm_is_called_once(self, mock_client, sample_context):
        analyzer = ArchitectureAnalyzer(client=mock_client, language="pt")
        analyzer.analyze(sample_context)
        mock_client.chat.assert_called_once()

    def test_validate_with_user_calls_llm_again(self, mock_client, sample_context):
        analyzer = ArchitectureAnalyzer(client=mock_client, language="pt")
        result = analyzer.analyze(sample_context)
        answers = {"Is the raw layer partitioned by date?": "Yes, partitioned by year/month/day"}
        updated = analyzer.validate_with_user(result, answers)
        assert mock_client.chat.call_count == 2
        assert len(updated.user_corrections) == 1

    def test_result_stores_raw_json(self, mock_client, sample_context):
        analyzer = ArchitectureAnalyzer(client=mock_client, language="pt")
        result = analyzer.analyze(sample_context)
        assert isinstance(result.raw_json, dict)
        assert result.raw_json["project_name"] == "DataPlatform"

    def test_handles_json_wrapped_in_markdown(self, mock_client, sample_context):
        mock_client.chat.return_value = f"```json\n{MOCK_ANALYSIS_RESPONSE}\n```"
        analyzer = ArchitectureAnalyzer(client=mock_client, language="pt")
        result = analyzer.analyze(sample_context)
        assert result.project_name == "DataPlatform"

    def test_handles_json_with_prose_around(self, mock_client, sample_context):
        mock_client.chat.return_value = f"Sure! Here is the result:\n{MOCK_ANALYSIS_RESPONSE}\nLet me know if you need changes."
        analyzer = ArchitectureAnalyzer(client=mock_client, language="pt")
        result = analyzer.analyze(sample_context)
        assert result.project_name == "DataPlatform"


class TestDiagramGenerator:
    def test_generates_png(self, mock_client, sample_context, tmp_path):
        from src.analysis.diagram import DiagramGenerator
        from src.analysis.analyzer import ArchitectureAnalyzer

        analyzer = ArchitectureAnalyzer(client=mock_client, language="pt")
        result = analyzer.analyze(sample_context)

        gen = DiagramGenerator(output_dir=str(tmp_path))
        path = gen.generate_png(result)
        assert Path(path).exists()
        assert path.endswith(".png")

    def test_generates_mermaid_markup(self, mock_client, sample_context):
        from src.analysis.diagram import DiagramGenerator
        from src.analysis.analyzer import ArchitectureAnalyzer

        analyzer = ArchitectureAnalyzer(client=mock_client, language="pt")
        result = analyzer.analyze(sample_context)

        gen = DiagramGenerator()
        mermaid = gen.generate_mermaid(result)
        assert "flowchart" in mermaid
        assert "Ingestion" in mermaid

    def test_raises_with_no_layers(self, mock_client, sample_context):
        from src.analysis.diagram import DiagramGenerator
        from src.analysis.analyzer import AnalysisResult

        result = AnalysisResult(
            raw_json={}, project_name="Empty", description="",
            tech_stack=[], layers=[], good_practices=[],
            improvement_points=[], validation_questions=[]
        )
        gen = DiagramGenerator()
        with pytest.raises(ValueError, match="No layers"):
            gen.generate_png(result)


class TestDocumentGenerators:
    def test_docx_is_created(self, mock_client, sample_context, tmp_path):
        from src.analysis.analyzer import ArchitectureAnalyzer
        from src.output.docx_gen import DocxGenerator

        analyzer = ArchitectureAnalyzer(client=mock_client, language="pt")
        result = analyzer.analyze(sample_context)

        gen = DocxGenerator(output_dir=str(tmp_path), language="pt")
        path = gen.generate(result)
        assert Path(path).exists()
        assert path.endswith(".docx")

    def test_pdf_is_created(self, mock_client, sample_context, tmp_path):
        from src.analysis.analyzer import ArchitectureAnalyzer
        from src.output.pdf_gen import PdfGenerator

        analyzer = ArchitectureAnalyzer(client=mock_client, language="pt")
        result = analyzer.analyze(sample_context)

        gen = PdfGenerator(output_dir=str(tmp_path), language="pt")
        path = gen.generate(result)
        assert Path(path).exists()
        assert path.endswith(".pdf")
