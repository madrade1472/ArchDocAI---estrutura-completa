"""
ArchDocAI Web Interface — FastAPI backend + simple HTML frontend.
Analyzes projects directly from a Git URL (shallow clone, no zip needed).
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware


def create_app() -> FastAPI:
    app = FastAPI(title="ArchDocAI", version="1.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    output_dir = Path("./output")
    output_dir.mkdir(exist_ok=True)
    app.mount("/output", StaticFiles(directory=str(output_dir)), name="output")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        html_path = Path(__file__).parent / "templates" / "index.html"
        return HTMLResponse(content=html_path.read_text())

    @app.post("/api/analyze")
    async def analyze(
        provider: str = Form(...),
        api_key: str = Form(...),
        model: str = Form(...),
        language: str = Form("pt"),
        git_url: str = Form(...),
        git_branch: str = Form(""),
        project_name: str = Form(""),
    ):
        """Clone a git repo (shallow) and analyze its architecture."""
        if provider not in ("openai", "anthropic", "custom"):
            raise HTTPException(400, "provider must be openai, anthropic, or custom")

        if not git_url.strip():
            raise HTTPException(400, "git_url is required")

        tmp_dir = tempfile.mkdtemp(prefix="archdoc_")
        try:
            # ── Clone repository (shallow, faster for large repos) ──────────
            clone_dir = Path(tmp_dir) / "repo"
            cmd = ["git", "clone", "--depth=1", "--single-branch"]
            if git_branch.strip():
                cmd += ["--branch", git_branch.strip()]
            cmd += [git_url.strip(), str(clone_dir)]

            result_clone = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120
            )
            if result_clone.returncode != 0:
                err = result_clone.stderr.strip()
                raise HTTPException(400, f"Git clone failed: {err}")

            # ── Detect actual project root ──────────────────────────────────
            project_root = clone_dir
            entries = [e for e in clone_dir.iterdir() if not e.name.startswith(".")]
            if len(entries) == 1 and entries[0].is_dir():
                project_root = entries[0]

            # ── Infer project name from URL if not provided ─────────────────
            inferred_name = project_name.strip() or Path(git_url.rstrip("/")).stem.replace("-", " ").replace("_", " ").title()

            # ── Output dir per run ──────────────────────────────────────────
            run_id = Path(tmp_dir).name
            output_dir_run = Path("./output") / run_id
            output_dir_run.mkdir(parents=True, exist_ok=True)

            # ── LLM config from form (not from .env) ────────────────────────
            os.environ["LLM_PROVIDER"] = provider
            os.environ["LLM_API_KEY"] = api_key
            os.environ["LLM_MODEL"] = model

            from src.ingestion import ProjectContext
            from src.analysis import LLMClient, ArchitectureAnalyzer, DiagramGenerator
            from src.output import DocxGenerator, PdfGenerator
            from src.analysis.llm_client import LLMConfig

            config = LLMConfig(provider=provider, api_key=api_key, model=model)  # type: ignore
            client = LLMClient(config=config)

            ctx = ProjectContext.from_path(str(project_root), project_name=inferred_name)
            analyzer = ArchitectureAnalyzer(client=client, language=language)
            analysis = analyzer.analyze(ctx)

            diagram_gen = DiagramGenerator(output_dir=str(output_dir_run))
            diagram_path = diagram_gen.generate_png(analysis)
            mermaid = diagram_gen.generate_mermaid(analysis)

            docx_gen = DocxGenerator(output_dir=str(output_dir_run), language=language)
            docx_path = docx_gen.generate(analysis, diagram_path=diagram_path)

            pdf_gen = PdfGenerator(output_dir=str(output_dir_run), language=language)
            pdf_path = pdf_gen.generate(analysis, diagram_path=diagram_path)

            def rel(p: str) -> str:
                return "/" + str(Path(p).relative_to("."))

            return JSONResponse({
                "status": "ok",
                "run_id": run_id,
                "project_name": analysis.project_name,
                "description": analysis.description,
                "layers": analysis.layers,
                "tech_stack": analysis.tech_stack,
                "good_practices": analysis.good_practices,
                "improvement_points": analysis.improvement_points,
                "validation_questions": analysis.validation_questions,
                "mermaid": mermaid,
                "files_scanned": ctx.summary()["total_files"],
                "files": {
                    "diagram": rel(diagram_path),
                    "docx": rel(docx_path),
                    "pdf": rel(pdf_path),
                },
            })

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @app.post("/api/validate")
    async def validate_answers(payload: dict):
        """Re-analyze with user corrections (stateless version: returns instructions)."""
        return JSONResponse({"status": "ok", "message": "Use CLI for interactive validation with corrections."})

    return app
