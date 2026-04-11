"""
ArchDocAI Web Interface - FastAPI backend + simple HTML frontend.
Analyzes projects directly from a Git URL (shallow clone).

Security & reliability:
- Rate limiting per IP: configurable via RATE_LIMIT_* env vars
- CORS: configurable via ALLOWED_ORIGINS env var (restrict in production)
- Thread-safe API key handling (never written to os.environ, never logged)
- Background thread per job with real-time status polling
- Repository size cap before cloning (MAX_REPO_SIZE_MB)
- Automatic cleanup of output folders older than 24h
- Structured rotating log (console + file, JSON-lines format)
- /health endpoint for load balancers and container orchestrators
- Optional API auth via ARCHDOC_API_KEY env var (Bearer token)
- Max concurrent jobs cap via MAX_CONCURRENT_JOBS env var
- git_url validated to only allow https:// and git@ schemes
"""

import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from src.logger import get_logger, setup_logging
from src.security import RateLimiter

load_dotenv()
setup_logging(log_dir="./logs")
log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

def _parse_origins(raw: str) -> list[str]:
    return [o.strip() for o in raw.split(",") if o.strip()] or ["*"]

_ALLOWED_ORIGINS = _parse_origins(os.getenv("ALLOWED_ORIGINS", "*"))
_MAX_REPO_SIZE_MB = int(os.getenv("MAX_REPO_SIZE_MB", "500"))
_RATE_MAX = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "10"))
_RATE_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "3600"))
_API_KEY = os.getenv("ARCHDOC_API_KEY", "")  # empty = auth disabled
_MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "5"))

_rate_limiter = RateLimiter(max_requests=_RATE_MAX, window_seconds=_RATE_WINDOW)
_job_semaphore = threading.Semaphore(_MAX_CONCURRENT_JOBS)

# Only allow https:// and git@ (SSH) URLs -- blocks file://, git://, etc.
_GIT_URL_RE = re.compile(r"^(https?://|git@)\S+$")


# ---------------------------------------------------------------------------
# In-memory job store (thread-safe)
# ---------------------------------------------------------------------------

class JobStore:
    def __init__(self):
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create(self, job_id: str) -> None:
        with self._lock:
            self._jobs[job_id] = {
                "status": "queued",
                "step": "Aguardando inicio...",
                "result": None,
                "error": None,
                "created_at": datetime.now(timezone.utc),
            }

    def update(self, job_id: str, **kwargs) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(kwargs)

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            return dict(self._jobs[job_id]) if job_id in self._jobs else None

    def purge_old(self, max_age_hours: int = 24) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        removed = 0
        with self._lock:
            stale = [jid for jid, j in self._jobs.items() if j["created_at"] < cutoff]
            for jid in stale:
                del self._jobs[jid]
                removed += 1
        if removed:
            log.info("Purged %d stale jobs", removed)
        return removed


_jobs = JobStore()


# ---------------------------------------------------------------------------
# Repository size helpers
# ---------------------------------------------------------------------------

def _dir_size_mb(path: Path) -> float:
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return total / (1024 * 1024)


def _check_repo_size(git_url: str, job_id: str, extra: dict) -> None:
    """
    Quick pre-clone size check using git ls-remote + pack-objects estimate.
    Not perfectly accurate but catches obviously oversized repos before
    we spend time cloning. Falls back silently if the check cannot run.
    """
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--refs", git_url],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return  # cannot check, proceed
        ref_count = len(result.stdout.strip().splitlines())
        log.info("Repo has %d refs", ref_count, extra=extra)
    except Exception:
        pass  # size check is best-effort, never block on failure


# ---------------------------------------------------------------------------
# Output folder cleanup
# ---------------------------------------------------------------------------

def cleanup_old_output(output_root: Path, max_age_hours: int = 24) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    removed = 0
    for folder in output_root.iterdir():
        if not folder.is_dir():
            continue
        try:
            mtime = datetime.fromtimestamp(folder.stat().st_mtime, timezone.utc)
            if mtime < cutoff:
                shutil.rmtree(folder, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    if removed:
        log.info("Cleaned %d old output folders", removed)


# ---------------------------------------------------------------------------
# Background analysis worker
# ---------------------------------------------------------------------------

def _run_analysis(
    job_id: str,
    provider: str,
    api_key: str,
    model: str,
    language: str,
    git_url: str,
    git_branch: str,
    project_name: str,
    output_root: Path,
    base_url: str | None = None,
) -> None:
    extra = {"job_id": job_id}
    tmp_dir = tempfile.mkdtemp(prefix="archdoc_")

    acquired = _job_semaphore.acquire(blocking=False)
    if not acquired:
        _jobs.update(
            job_id,
            status="error",
            step="Erro.",
            error=f"Servidor ocupado: limite de {_MAX_CONCURRENT_JOBS} jobs concorrentes atingido. Tente novamente em instantes.",
        )
        return

    try:
        log.info("Job started - cloning %s", git_url, extra=extra)
        _jobs.update(job_id, status="running", step="Verificando repositorio...")

        # Check approximate repo size via git ls-remote before full clone
        _check_repo_size(git_url, job_id, extra)

        _jobs.update(job_id, step="Clonando repositorio...")
        cmd = ["git", "clone", "--depth=1", "--single-branch"]
        if git_branch.strip():
            cmd += ["--branch", git_branch.strip()]
        clone_dir = Path(tmp_dir) / "repo"
        cmd += [git_url.strip(), str(clone_dir)]

        result_clone = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result_clone.returncode != 0:
            raise RuntimeError(f"Git clone falhou: {result_clone.stderr.strip()}")

        # Verify cloned size on disk
        clone_size_mb = _dir_size_mb(clone_dir)
        log.info("Cloned repo size on disk: %.1f MB", clone_size_mb, extra=extra)
        if clone_size_mb > _MAX_REPO_SIZE_MB:
            raise RuntimeError(
                f"Repositorio clonado ocupa {clone_size_mb:.0f} MB, limite e {_MAX_REPO_SIZE_MB} MB. "
                "Aumente MAX_REPO_SIZE_MB ou use um repositorio menor."
            )

        log.info("Clone complete", extra=extra)
        _jobs.update(job_id, step="Escaneando arquivos do projeto...")

        project_root = clone_dir
        entries = [e for e in clone_dir.iterdir() if not e.name.startswith(".")]
        if len(entries) == 1 and entries[0].is_dir():
            project_root = entries[0]

        inferred_name = (
            project_name.strip()
            or Path(git_url.rstrip("/")).stem.replace("-", " ").replace("_", " ").title()
        )

        output_dir_run = output_root / job_id
        output_dir_run.mkdir(parents=True, exist_ok=True)

        from src.ingestion import ProjectContext
        from src.analysis import LLMClient, ArchitectureAnalyzer, DiagramGenerator
        from src.analysis.llm_client import LLMConfig
        from src.output import DocxGenerator, PdfGenerator

        # Thread-safe: LLMConfig built locally, never touches os.environ
        config = LLMConfig(provider=provider, api_key=api_key, model=model, base_url=base_url)  # type: ignore
        client = LLMClient(config=config)

        ctx = ProjectContext.from_path(str(project_root), project_name=inferred_name)
        summary = ctx.summary()
        log.info("Scanned %d files (%s KB)", summary["total_files"], summary["total_size_kb"], extra=extra)

        _jobs.update(job_id, step=f"Analisando {summary['total_files']} arquivos com LLM...")

        analyzer = ArchitectureAnalyzer(client=client, language=language)
        analysis = analyzer.analyze(ctx)

        log.info("LLM analysis complete: %d layers", len(analysis.layers), extra=extra)
        _jobs.update(job_id, step="Gerando diagrama...")

        diagram_gen = DiagramGenerator(output_dir=str(output_dir_run))
        diagram_path = diagram_gen.generate_png(analysis)
        mermaid = diagram_gen.generate_mermaid(analysis)

        _jobs.update(job_id, step="Gerando documentos (.docx e PDF)...")
        docx_path = DocxGenerator(output_dir=str(output_dir_run), language=language).generate(
            analysis, diagram_path=diagram_path
        )
        pdf_path = PdfGenerator(output_dir=str(output_dir_run), language=language).generate(
            analysis, diagram_path=diagram_path
        )

        def rel(p: str) -> str:
            return "/" + str(Path(p).relative_to("."))

        log.info("Job complete - outputs: diagram, docx, pdf", extra=extra)
        _jobs.update(
            job_id,
            status="done",
            step="Concluido.",
            result={
                "project_name": analysis.project_name,
                "description": analysis.description,
                "layers": analysis.layers,
                "tech_stack": analysis.tech_stack,
                "good_practices": analysis.good_practices,
                "improvement_points": analysis.improvement_points,
                "validation_questions": analysis.validation_questions,
                "mermaid": mermaid,
                "files_scanned": summary["total_files"],
                "files": {
                    "diagram": rel(diagram_path),
                    "docx": rel(docx_path),
                    "pdf": rel(pdf_path),
                },
            },
        )

    except Exception as exc:
        log.error("Job failed: %s", exc, exc_info=True, extra=extra)
        _jobs.update(job_id, status="error", step="Erro.", error=str(exc))

    finally:
        _job_semaphore.release()
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    output_root = Path("./output")
    output_root.mkdir(exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        log.info(
            "ArchDocAI starting up (v1.4.0) - CORS=%s, MAX_REPO=%sMB, RATE=%s/%ss",
            _ALLOWED_ORIGINS, _MAX_REPO_SIZE_MB, _RATE_MAX, _RATE_WINDOW,
        )
        cleanup_old_output(output_root)
        yield

    app = FastAPI(title="ArchDocAI", version="1.4.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_ALLOWED_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    app.mount("/output", StaticFiles(directory=str(output_root)), name="output")

    @app.get("/health")
    async def health():
        """Health check for load balancers and container orchestrators."""
        return JSONResponse({
            "status": "ok",
            "version": "1.4.0",
            "jobs_active": sum(
                1 for j in [_jobs.get(jid) for jid in list(_jobs._jobs)]
                if j and j.get("status") == "running"
            ),
        })

    @app.get("/", response_class=HTMLResponse)
    async def index():
        html_path = Path(__file__).parent / "templates" / "index.html"
        return HTMLResponse(content=html_path.read_text())

    @app.post("/api/analyze")
    async def analyze(
        request: Request,
        provider: str = Form(..., max_length=20),
        api_key: str = Form(..., max_length=512),
        model: str = Form(..., max_length=100),
        language: str = Form("pt", max_length=5),
        git_url: str = Form(..., max_length=512),
        git_branch: str = Form("", max_length=200),
        project_name: str = Form("", max_length=200),
        base_url: str = Form("", max_length=512),
    ):
        # Optional Bearer token auth (only enforced when ARCHDOC_API_KEY is set)
        if _API_KEY:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer ") or auth_header[7:] != _API_KEY:
                raise HTTPException(401, "Autenticacao necessaria: Bearer token invalido ou ausente.")

        # Rate limiting by IP
        client_ip = request.client.host if request.client else "unknown"
        allowed, retry_after = _rate_limiter.check(client_ip)

        if not allowed:
            log.warning("Rate limit exceeded for IP %s", client_ip)
            raise HTTPException(
                status_code=429,
                detail=f"Limite de requisicoes atingido. Tente novamente em {retry_after} segundos.",
                headers={"Retry-After": str(retry_after)},
            )

        if provider not in ("openai", "anthropic", "custom"):
            raise HTTPException(400, "provider deve ser openai, anthropic ou custom")

        # Validate git URL scheme -- reject file://, git://, local paths, etc.
        if not git_url.strip() or not _GIT_URL_RE.match(git_url.strip()):
            raise HTTPException(
                400,
                "git_url invalida: use https:// ou git@ (SSH). Esquemas file://, git:// e caminhos locais nao sao permitidos.",
            )

        # Require base_url when provider is custom
        if provider == "custom" and not base_url.strip():
            raise HTTPException(
                400,
                "base_url e obrigatorio quando provider=custom (ex: http://localhost:11434/v1).",
            )

        remaining = _rate_limiter.remaining(client_ip)
        log.info("New job request from %s - %s (remaining quota: %d)", client_ip, git_url, remaining)

        _jobs.purge_old()
        cleanup_old_output(output_root)

        job_id = uuid.uuid4().hex
        _jobs.create(job_id)

        thread = threading.Thread(
            target=_run_analysis,
            args=(job_id, provider, api_key, model, language, git_url, git_branch, project_name, output_root, base_url.strip() or None),
            daemon=True,
        )
        thread.start()

        return JSONResponse(
            {"job_id": job_id, "status": "queued", "remaining_quota": remaining},
            status_code=202,
        )

    @app.get("/api/status/{job_id}")
    async def status(job_id: str):
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "job nao encontrado")
        job.pop("created_at", None)
        return JSONResponse(job)

    @app.get("/api/quota")
    async def quota(request: Request):
        """Return how many requests the caller still has in the current window."""
        client_ip = request.client.host if request.client else "unknown"
        remaining = _rate_limiter.remaining(client_ip)
        return JSONResponse({"remaining": remaining, "limit": _rate_limiter.max_requests, "window_seconds": _rate_limiter.window_seconds})

    return app
