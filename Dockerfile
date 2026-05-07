# ─────────────────────────────────────────────────────────────────────────────
# ArchDocAI — production container.
#
# Two-stage build keeps the runtime image small (build-essential lives only in
# the builder stage). The runtime carries just the shared libraries the Python
# wheels expect at import time.
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: build wheels with native deps ──────────────────────────────────
FROM python:3.12-slim AS builder

# Build deps needed to compile any wheel without a manylinux build:
# cairo headers for cairosvg, ffi for cryptography-style transitive deps.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libcairo2-dev \
        libffi-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Install requirements into an isolated prefix so we can copy just that
# into the runtime stage without dragging headers/compilers along.
COPY requirements.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.12-slim

# Runtime shared libraries:
#   libcairo2          - cairosvg renders Devicon SVG logos onto the diagram
#   libpango / pangoft - matplotlib text rendering paths
#   fonts-dejavu-core  - matplotlib default font family
#   git                - ingestion clones user-supplied repositories
RUN apt-get update && apt-get install -y --no-install-recommends \
        libcairo2 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        fonts-dejavu-core \
        git \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Non-root user keeps this safer if a clone-from-user-URL ever escapes its sandbox.
RUN useradd --create-home --shell /bin/bash --uid 1000 archdoc

WORKDIR /app

# Pull the prefix-installed packages out of the builder stage.
COPY --from=builder /install /usr/local

# Application code. .dockerignore keeps secrets, venvs and prior outputs out.
COPY --chown=archdoc:archdoc . /app

# Output and log directories are mounted as volumes in compose / mapped to
# managed storage in production. Pre-create them with the right owner so the
# non-root user can write even before the volume is mounted.
RUN mkdir -p /app/output /app/logs && chown -R archdoc:archdoc /app/output /app/logs

USER archdoc

# Cloud Run, Render and Railway all set $PORT at runtime. Local docker-compose
# and direct `docker run` fall back to 8000.
ENV PORT=8000 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000

# Lightweight liveness probe against the existing /health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health').read()" || exit 1

# `sh -c` lets ${PORT} expand at container start time.
CMD ["sh", "-c", "uvicorn web.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
