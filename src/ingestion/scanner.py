"""
Layer 1 - Ingestion: Scan a project directory and collect relevant files.
Supports Python, SQL, YAML, JSON, JS/TS, Go, Java, and more.

Prioritization strategy (lower score = higher priority):
  1. Language relevance (SQL, Terraform, Docker = most architectural)
  2. File name relevance (main, app, config, pipeline = entry points)
  3. Path depth (shallower = more likely to be architectural)
  4. File size (tiny stubs and giant data files are deprioritized)
"""

import os
import fnmatch
from pathlib import Path
from dataclasses import dataclass
from src.logger import get_logger

log = get_logger(__name__)

SUPPORTED_EXTENSIONS = {
    ".py": "Python",
    ".sql": "SQL",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript/React",
    ".jsx": "JavaScript/React",
    ".go": "Go",
    ".java": "Java",
    ".cs": "C#",
    ".tf": "Terraform",
    ".sh": "Shell",
    ".md": "Markdown",
    ".toml": "TOML",
    ".env.example": "Environment Config",
    ".dockerfile": "Docker",
    "Dockerfile": "Docker",
    "docker-compose.yml": "Docker Compose",
    "docker-compose.yaml": "Docker Compose",
}

IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    "dist", "build", ".next", ".mypy_cache", ".pytest_cache",
    "coverage", ".tox", "eggs", "*.egg-info", "vendor", "target",
    ".terraform", "migrations", "fixtures", "static", "assets",
}

IGNORE_FILES = {
    "*.lock", "*.pyc", "*.pyo", "*.min.js", "*.min.css",
    "package-lock.json", "yarn.lock", "poetry.lock", "*.pb.go",
    "*.generated.*", "*_test.go",
}

# Language priority: lower = more architecturally relevant
LANGUAGE_PRIORITY = {
    "SQL": 0,
    "Terraform": 1,
    "Docker Compose": 2,
    "Docker": 3,
    "Python": 4,
    "Go": 4,
    "Java": 4,
    "TypeScript": 5,
    "JavaScript": 5,
    "YAML": 6,
    "TOML": 7,
    "Shell": 8,
    "Markdown": 9,
    "JSON": 10,
}

# File name patterns that indicate architectural entry points (lower score = better)
IMPORTANT_NAME_PATTERNS = [
    ("main", 0), ("app", 0), ("server", 0), ("index", 0),
    ("pipeline", 1), ("dag", 1), ("flow", 1), ("workflow", 1),
    ("config", 2), ("settings", 2), ("conf", 2),
    ("schema", 3), ("model", 3), ("entity", 3),
    ("route", 4), ("router", 4), ("handler", 4), ("controller", 4),
    ("service", 4), ("repository", 4), ("manager", 4),
    ("docker", 5), ("compose", 5), ("makefile", 5),
    ("readme", 6), ("requirements", 6),
]

MAX_FILE_BYTES = 50_000   # 50KB per file to avoid flooding the LLM context
MIN_FILE_BYTES = 1        # Skip truly empty files only
MAX_FILES = 100           # Raised from 80 to capture more of large repos


@dataclass
class ScannedFile:
    path: str
    relative_path: str
    language: str
    size_bytes: int
    content: str
    truncated: bool = False


@dataclass
class ProjectScanner:
    root_path: str
    max_files: int = MAX_FILES

    def scan(self) -> list[ScannedFile]:
        root = Path(self.root_path).resolve()
        candidates: list[tuple[tuple, ScannedFile]] = []

        for dirpath, dirnames, filenames in os.walk(root):
            # Prune ignored directories in-place
            dirnames[:] = [
                d for d in dirnames
                if d not in IGNORE_DIRS and not d.startswith(".")
            ]

            current_depth = len(Path(dirpath).relative_to(root).parts)

            for filename in filenames:
                if self._should_ignore_file(filename):
                    continue

                filepath = Path(dirpath) / filename
                ext = filepath.suffix.lower()
                language = SUPPORTED_EXTENSIONS.get(ext) or SUPPORTED_EXTENSIONS.get(filename)
                if language is None:
                    continue

                try:
                    size = filepath.stat().st_size
                    if size < MIN_FILE_BYTES:
                        continue

                    raw = filepath.read_bytes()
                    truncated = False
                    if size > MAX_FILE_BYTES:
                        raw = raw[:MAX_FILE_BYTES]
                        truncated = True

                    content = raw.decode("utf-8", errors="replace")
                    relative = str(filepath.relative_to(root))

                    scanned = ScannedFile(
                        path=str(filepath),
                        relative_path=relative,
                        language=language,
                        size_bytes=size,
                        content=content,
                        truncated=truncated,
                    )
                    priority = self._score(filename, language, current_depth, size)
                    candidates.append((priority, scanned))

                except (PermissionError, OSError):
                    continue

        # Sort by score ascending (best first), then slice
        candidates.sort(key=lambda x: x[0])
        result = [sf for _, sf in candidates[: self.max_files]]
        log.info("Scan complete: %d files selected (out of %d candidates)", len(result), len(candidates))
        return result

    def _score(self, filename: str, language: str, depth: int, size: int) -> tuple:
        lang_score = LANGUAGE_PRIORITY.get(language, 15)

        name_lower = Path(filename).stem.lower()
        name_score = 99
        for pattern, score in IMPORTANT_NAME_PATTERNS:
            if pattern in name_lower:
                name_score = min(name_score, score)

        # Penalize very large files slightly (likely data, not architecture)
        size_penalty = 1 if size > 20_000 else 0

        return (lang_score, name_score, depth, size_penalty, filename)

    def _should_ignore_file(self, filename: str) -> bool:
        for pattern in IGNORE_FILES:
            if fnmatch.fnmatch(filename, pattern):
                return True
        return False

    def get_directory_tree(self, max_depth: int = 4) -> str:
        root = Path(self.root_path).resolve()
        lines = [str(root.name) + "/"]
        self._walk_tree(root, lines, prefix="", depth=0, max_depth=max_depth)
        return "\n".join(lines)

    def _walk_tree(self, path: Path, lines: list, prefix: str, depth: int, max_depth: int):
        if depth >= max_depth:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda e: (e.is_file(), e.name))
        except PermissionError:
            return

        entries = [
            e for e in entries
            if not (e.is_dir() and (e.name in IGNORE_DIRS or e.name.startswith(".")))
        ]

        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{entry.name}{'/' if entry.is_dir() else ''}")
            if entry.is_dir():
                extension = "    " if is_last else "│   "
                self._walk_tree(entry, lines, prefix + extension, depth + 1, max_depth)
