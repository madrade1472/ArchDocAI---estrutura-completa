"""
Smoke tests for DocxGenerator and PdfGenerator.
Verifies that both generators can be imported, instantiated, and produce
output files without errors using a minimal AnalysisResult fixture.
These tests catch ImportError / missing-dependency regressions early.
"""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def minimal_result():
    from src.analysis.analyzer import AnalysisResult
    return AnalysisResult(
        raw_json={},
        project_name="TestProject",
        description="A minimal project for testing.",
        tech_stack=["Python"],
        layers=[
            {
                "id": "l1",
                "name": "Ingestion",
                "description": "Reads data",
                "color": "#2d6a4f",
                "components": [
                    {"name": "Scanner", "description": "Scans files", "tech": "Python", "type": "process"}
                ],
                "connections_to": [],
            }
        ],
        good_practices=["Uses type hints"],
        improvement_points=["Add more tests"],
        validation_questions=["Is layer 1 correct?"],
    )


class TestDocxGenerator:
    def test_import(self):
        from src.output import DocxGenerator
        assert DocxGenerator is not None

    def test_instantiates(self, tmp_path):
        from src.output import DocxGenerator
        gen = DocxGenerator(output_dir=str(tmp_path))
        assert gen.output_dir == str(tmp_path)

    def test_generate_creates_docx_file(self, tmp_path, minimal_result):
        from src.output import DocxGenerator
        gen = DocxGenerator(output_dir=str(tmp_path), language="en")
        path = gen.generate(minimal_result)
        assert Path(path).exists()
        assert path.endswith(".docx")

    def test_generate_pt_creates_docx_file(self, tmp_path, minimal_result):
        from src.output import DocxGenerator
        gen = DocxGenerator(output_dir=str(tmp_path), language="pt")
        path = gen.generate(minimal_result)
        assert Path(path).exists()

    def test_generate_with_diagram_path(self, tmp_path, minimal_result):
        """Should not crash if diagram_path points to a non-existent file."""
        from src.output import DocxGenerator
        gen = DocxGenerator(output_dir=str(tmp_path))
        # diagram_path is optional; generators should handle None gracefully
        path = gen.generate(minimal_result, diagram_path=None)
        assert Path(path).exists()


class TestPdfGenerator:
    def test_import(self):
        from src.output import PdfGenerator
        assert PdfGenerator is not None

    def test_instantiates(self, tmp_path):
        from src.output import PdfGenerator
        gen = PdfGenerator(output_dir=str(tmp_path))
        assert gen.output_dir == str(tmp_path)

    def test_generate_creates_pdf_file(self, tmp_path, minimal_result):
        from src.output import PdfGenerator
        gen = PdfGenerator(output_dir=str(tmp_path), language="en")
        path = gen.generate(minimal_result)
        assert Path(path).exists()
        assert path.endswith(".pdf")

    def test_generate_pt_creates_pdf_file(self, tmp_path, minimal_result):
        from src.output import PdfGenerator
        gen = PdfGenerator(output_dir=str(tmp_path), language="pt")
        path = gen.generate(minimal_result)
        assert Path(path).exists()
