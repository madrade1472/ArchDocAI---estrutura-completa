"""
Tech logo lookup and download for diagram rendering.

Maps tech keywords detected in the analysis to Devicon CDN URLs and caches
downloaded PNGs locally so we never hit the network twice for the same logo.

Devicon (https://devicon.dev) is the canonical source of free tech logos.
We use the jsDelivr mirror for fast, anonymous, no-rate-limited downloads.
"""

from __future__ import annotations

import os
import threading
import urllib.request
import urllib.error
from pathlib import Path
from src.logger import get_logger

log = get_logger(__name__)


# Cache lives in the user's cache dir (or env override) so it survives across runs
# and is shared between CLI and web server processes.
def _cache_dir() -> Path:
    base = os.getenv("ARCHDOC_ICON_CACHE", str(Path.home() / ".cache" / "archdocai" / "icons"))
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


# (devicon_folder, devicon_filename) per tech keyword.
# Keywords are matched case-insensitively against component.tech and layer name.
# Order matters for substring matches: longer/more specific keys go first.
TECH_TO_DEVICON: dict[str, tuple[str, str]] = {
    # Languages
    "python":          ("python", "python-original.svg"),
    "typescript":      ("typescript", "typescript-original.svg"),
    "javascript":      ("javascript", "javascript-original.svg"),
    "java":            ("java", "java-original.svg"),
    "kotlin":          ("kotlin", "kotlin-original.svg"),
    "scala":           ("scala", "scala-original.svg"),
    "go":              ("go", "go-original.svg"),
    "golang":          ("go", "go-original.svg"),
    "rust":            ("rust", "rust-original.svg"),
    "ruby":            ("ruby", "ruby-original.svg"),
    "php":             ("php", "php-original.svg"),
    "csharp":          ("csharp", "csharp-original.svg"),
    "c#":              ("csharp", "csharp-original.svg"),
    "swift":           ("swift", "swift-original.svg"),
    "r":               ("r", "r-original.svg"),

    # Web frameworks
    "react":           ("react", "react-original.svg"),
    "vue":             ("vuejs", "vuejs-original.svg"),
    "angular":         ("angularjs", "angularjs-original.svg"),
    "nextjs":          ("nextjs", "nextjs-original.svg"),
    "next.js":         ("nextjs", "nextjs-original.svg"),
    "nuxt":            ("nuxtjs", "nuxtjs-original.svg"),
    "svelte":          ("svelte", "svelte-original.svg"),
    "fastapi":         ("fastapi", "fastapi-original.svg"),
    "flask":           ("flask", "flask-original.svg"),
    "django":          ("django", "django-plain.svg"),
    "express":         ("express", "express-original.svg"),
    "spring":          ("spring", "spring-original.svg"),
    "rails":           ("rails", "rails-original-wordmark.svg"),
    "streamlit":       ("streamlit", "streamlit-original.svg"),

    # Databases
    "postgresql":      ("postgresql", "postgresql-original.svg"),
    "postgres":        ("postgresql", "postgresql-original.svg"),
    "mysql":           ("mysql", "mysql-original.svg"),
    "sqlite":          ("sqlite", "sqlite-original.svg"),
    "mongodb":         ("mongodb", "mongodb-original.svg"),
    "mongo":           ("mongodb", "mongodb-original.svg"),
    "redis":           ("redis", "redis-original.svg"),
    "cassandra":       ("cassandra", "cassandra-original.svg"),
    "elasticsearch":   ("elasticsearch", "elasticsearch-original.svg"),
    "elastic":         ("elasticsearch", "elasticsearch-original.svg"),
    "neo4j":           ("neo4j", "neo4j-original.svg"),
    "mariadb":         ("mariadb", "mariadb-original.svg"),
    "oracle":          ("oracle", "oracle-original.svg"),
    "supabase":        ("supabase", "supabase-original.svg"),
    "snowflake":       ("snowflake", "snowflake-original.svg"),

    # Message queues / streaming
    "kafka":           ("apachekafka", "apachekafka-original.svg"),
    "rabbitmq":        ("rabbitmq", "rabbitmq-original.svg"),
    "celery":          ("celery", "celery-plain.svg"),

    # Cloud
    "aws":             ("amazonwebservices", "amazonwebservices-original-wordmark.svg"),
    "amazonwebservices": ("amazonwebservices", "amazonwebservices-original-wordmark.svg"),
    "gcp":             ("googlecloud", "googlecloud-original.svg"),
    "googlecloud":     ("googlecloud", "googlecloud-original.svg"),
    "azure":           ("azure", "azure-original.svg"),
    "vercel":          ("vercel", "vercel-original.svg"),
    "heroku":          ("heroku", "heroku-original.svg"),
    "digitalocean":    ("digitalocean", "digitalocean-original.svg"),
    "cloudflare":      ("cloudflare", "cloudflare-original.svg"),

    # Containers / orchestration
    "docker":          ("docker", "docker-original.svg"),
    "kubernetes":      ("kubernetes", "kubernetes-original.svg"),
    "k8s":             ("kubernetes", "kubernetes-original.svg"),
    "podman":          ("podman", "podman-original.svg"),
    "helm":            ("helm", "helm-original.svg"),

    # Data / ML
    "pandas":          ("pandas", "pandas-original.svg"),
    "numpy":           ("numpy", "numpy-original.svg"),
    "scikit-learn":    ("scikitlearn", "scikitlearn-original.svg"),
    "sklearn":         ("scikitlearn", "scikitlearn-original.svg"),
    "tensorflow":      ("tensorflow", "tensorflow-original.svg"),
    "pytorch":         ("pytorch", "pytorch-original.svg"),
    "spark":           ("apachespark", "apachespark-original.svg"),
    "airflow":         ("apacheairflow", "apacheairflow-original.svg"),
    "jupyter":         ("jupyter", "jupyter-original.svg"),
    "matplotlib":      ("matplotlib", "matplotlib-original.svg"),

    # APIs / proto
    "graphql":         ("graphql", "graphql-plain.svg"),
    "grpc":            ("grpc", "grpc-plain.svg"),
    "swagger":         ("swagger", "swagger-original.svg"),

    # Web servers
    "nginx":           ("nginx", "nginx-original.svg"),
    "apache":          ("apache", "apache-original.svg"),

    # Tools
    "git":              ("git", "git-original.svg"),
    "github":           ("github", "github-original.svg"),
    "gitlab":           ("gitlab", "gitlab-original.svg"),
    "terraform":        ("terraform", "terraform-original.svg"),
    "ansible":          ("ansible", "ansible-original.svg"),
    "jenkins":          ("jenkins", "jenkins-original.svg"),
    "vscode":           ("vscode", "vscode-original.svg"),

    # Frontend
    "tailwind":         ("tailwindcss", "tailwindcss-original.svg"),
    "tailwindcss":      ("tailwindcss", "tailwindcss-original.svg"),
    "bootstrap":        ("bootstrap", "bootstrap-original.svg"),
    "sass":             ("sass", "sass-original.svg"),
    "html":             ("html5", "html5-original.svg"),
    "html5":            ("html5", "html5-original.svg"),
    "css":              ("css3", "css3-original.svg"),
    "css3":             ("css3", "css3-original.svg"),
    "vite":             ("vitejs", "vitejs-original.svg"),
    "webpack":          ("webpack", "webpack-original.svg"),
}

# Devicon ships SVGs through the npm CDN. We download the SVG once and convert
# to PNG locally via cairosvg, caching both the source and the rendered PNG.
_DEVICON_BASE = "https://cdn.jsdelivr.net/npm/devicon@latest/icons"
_PNG_RENDER_WIDTH = 256  # rendered PNG width in pixels - high-DPI for sharp scaling
_download_lock = threading.Lock()
_failed_downloads: set[str] = set()  # remember failures to skip retries within same process


def _normalize(text: str) -> str:
    return text.lower().strip().replace("/", " ").replace(",", " ")


def find_icon_key(tech_text: str) -> str | None:
    """Return the canonical TECH_TO_DEVICON key for a free-form tech string, or None.

    Matches longest substring first so 'PostgreSQL 15' resolves to 'postgresql'
    and not to 'sql' or 'gres'.
    """
    if not tech_text:
        return None
    normalized = _normalize(tech_text)
    sorted_keys = sorted(TECH_TO_DEVICON.keys(), key=len, reverse=True)
    for key in sorted_keys:
        if key in normalized:
            return key
    return None


def get_icon_path(tech_text: str) -> Path | None:
    """Return a local Path to the cached PNG for this tech, downloading on first hit.

    Devicon ships SVGs only - we download the SVG and rasterize to PNG via
    cairosvg, then cache the PNG so subsequent calls are zero-cost.

    Returns None when:
      - No mapping exists for the tech
      - Network download fails (logs a warning, caches the failure for the run)
      - cairosvg is not installed (logs a warning once)
    Calling code should fall back to drawn icons in either case.
    """
    key = find_icon_key(tech_text)
    if not key:
        return None

    folder, filename = TECH_TO_DEVICON[key]  # filename ends in .svg
    png_filename = filename[:-4] + ".png" if filename.endswith(".svg") else filename + ".png"
    png_path = _cache_dir() / folder / png_filename

    if png_path.exists() and png_path.stat().st_size > 0:
        return png_path

    cache_id = f"{folder}/{filename}"
    if cache_id in _failed_downloads:
        return None

    url = f"{_DEVICON_BASE}/{folder}/{filename}"
    png_path.parent.mkdir(parents=True, exist_ok=True)

    with _download_lock:
        # Double-check inside the lock in case another thread just rendered it
        if png_path.exists() and png_path.stat().st_size > 0:
            return png_path
        try:
            import cairosvg  # local import: optional dep, only needed when icons are used
        except ImportError:
            log.warning("cairosvg not installed - falling back to drawn icons. "
                        "Install with: pip install cairosvg")
            _failed_downloads.add(cache_id)
            return None
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ArchDocAI/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status != 200:
                    raise urllib.error.HTTPError(url, resp.status, "non-200", resp.headers, None)
                svg_data = resp.read()
            if len(svg_data) < 100:
                raise ValueError(f"svg too small ({len(svg_data)} bytes)")
            png_data = cairosvg.svg2png(bytestring=svg_data, output_width=_PNG_RENDER_WIDTH)
            png_path.write_bytes(png_data)
            log.info("Rendered tech icon: %s (svg %dB -> png %dB)", cache_id, len(svg_data), len(png_data))
            return png_path
        except Exception as exc:
            log.warning("Failed to fetch/render tech icon %s from %s: %s", cache_id, url, exc)
            _failed_downloads.add(cache_id)
            return None
