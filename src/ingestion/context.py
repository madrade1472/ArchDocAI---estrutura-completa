"""
Layer 1 - Ingestion: Build a compact, structured project context
to send to the LLM without wasting tokens.
"""

from dataclasses import dataclass
from .scanner import ScannedFile, ProjectScanner


@dataclass
class ProjectContext:
    project_name: str
    root_path: str
    directory_tree: str
    files: list[ScannedFile]

    @classmethod
    def from_path(cls, path: str, project_name: str | None = None) -> "ProjectContext":
        from pathlib import Path
        root = Path(path).resolve()
        name = project_name or root.name

        scanner = ProjectScanner(root_path=str(root))
        files = scanner.scan()
        tree = scanner.get_directory_tree()

        return cls(
            project_name=name,
            root_path=str(root),
            directory_tree=tree,
            files=files,
        )

    def to_llm_prompt(self, language: str = "pt") -> str:
        """Serialize the project context into a single prompt string for the LLM."""
        lang_instructions = {
            "pt": "Responda em português brasileiro.",
            "en": "Respond in English.",
        }
        lang_note = lang_instructions.get(language, lang_instructions["pt"])

        sections = [
            f"# Project: {self.project_name}",
            f"\n{lang_note}",
            "\n## Directory Structure\n```\n" + self.directory_tree + "\n```",
            "\n## Source Files\n",
        ]

        for f in self.files:
            trunc_note = " *(truncated)*" if f.truncated else ""
            sections.append(
                f"### `{f.relative_path}` ({f.language}){trunc_note}\n"
                f"```{f.language.lower()}\n{f.content}\n```\n"
            )

        return "\n".join(sections)

    def summary(self) -> dict:
        from collections import Counter
        lang_counts = Counter(f.language for f in self.files)
        return {
            "project_name": self.project_name,
            "total_files": len(self.files),
            "languages": dict(lang_counts),
            "total_size_kb": round(sum(f.size_bytes for f in self.files) / 1024, 1),
        }
