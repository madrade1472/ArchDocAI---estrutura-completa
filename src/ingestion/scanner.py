"""
Layer 1 - Ingestion: Scan a project directory and collect relevant files.
Supports Python, SQL, YAML, JSON, JS/TS, Go, Java, and more.
"""

import os
import fnmatch
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

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
    "coverage", ".tox", "eggs", "*.egg-info",
}

IGNORE_FILES = {
    "*.lock", "*.pyc", "*.pyo", "*.min.js", "*.min.css",
    "package-lock.json", "yarn.lock", "poetry.lock",
}

MAX_FILE_BYTES = 50_000  # 50KB per file to avoid flooding the LLM context


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
    max_files: int = 80

    def scan(self) -> list[ScannedFile]:
        root = Path(self.root_path).resolve()
        files: list[ScannedFile] = []

        for dirpath, dirnames, filenames in os.walk(root):
            # Prune ignored directories in-place
            dirnames[:] = [
                d for d in dirnames
                if d not in IGNORE_DIRS and not d.startswith(".")
            ]

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
                    raw = filepath.read_bytes()
                    truncated = False

                    if size > MAX_FILE_BYTES:
                        raw = raw[:MAX_FILE_BYTES]
                        truncated = True

                    content = raw.decode("utf-8", errors="replace")
                    relative = str(filepath.relative_to(root))

                    files.append(ScannedFile(
                        path=str(filepath),
                        relative_path=relative,
                        language=language,
                        size_bytes=size,
                        content=content,
                        truncated=truncated,
                    ))

                except (PermissionError, OSError):
                    continue

                if len(files) >= self.max_files:
                    return files

        # Prioritize: SQL > Python > YAML > others (more architecture-relevant first)
        priority = {"SQL": 0, "Python": 1, "Terraform": 2, "YAML": 3, "Docker": 4}
        files.sort(key=lambda f: (priority.get(f.language, 99), f.relative_path))
        return files

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
