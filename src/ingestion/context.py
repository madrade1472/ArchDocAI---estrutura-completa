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

    # Target ~3 500 tokens for context so the full request stays well under
    # the 10 000 tok/min org rate limit (system prompt + schema add ~300 more).
    # Override via MAX_PROMPT_CHARS env var for orgs with higher limits.
    MAX_PROMPT_CHARS: int = int(__import__("os").getenv("MAX_PROMPT_CHARS", "12000"))

    def to_llm_prompt(self, language: str = "pt") -> str:
        """Serialize the project context into a single prompt string for the LLM.

        Hard-caps total size at MAX_PROMPT_CHARS: drops lowest-priority files
        once the budget is exhausted and records how many were omitted.
        """
        lang_instructions = {
            "pt": "Responda em português brasileiro.",
            "en": "Respond in English.",
        }
        lang_note = lang_instructions.get(language, lang_instructions["pt"])

        # Cap directory tree so it doesn't eat the whole budget on large repos
        _MAX_TREE_CHARS = 2_000
        tree = self.directory_tree
        if len(tree) > _MAX_TREE_CHARS:
            lines = tree.splitlines()
            truncated_lines = []
            used = 0
            for line in lines:
                if used + len(line) + 1 > _MAX_TREE_CHARS:
                    truncated_lines.append("... (truncated)")
                    break
                truncated_lines.append(line)
                used += len(line) + 1
            tree = "\n".join(truncated_lines)

        header = "\n".join([
            f"# Project: {self.project_name}",
            f"\n{lang_note}",
            "\n## Directory Structure\n```\n" + tree + "\n```",
            "\n## Source Files\n",
        ])

        budget = self.MAX_PROMPT_CHARS - len(header) - 200  # 200 chars safety margin
        file_sections: list[str] = []
        omitted = 0

        for f in self.files:
            trunc_note = " *(truncated)*" if f.truncated else ""
            block = (
                f"### `{f.relative_path}` ({f.language}){trunc_note}\n"
                f"```{f.language.lower()}\n{f.content}\n```\n"
            )
            if len(block) <= budget:
                file_sections.append(block)
                budget -= len(block)
            else:
                omitted += 1

        if omitted:
            omit_note = (
                f"\n> ⚠️ {omitted} arquivo(s) omitido(s) por limite de contexto (prompt muito grande).\n"
                if language == "pt" else
                f"\n> ⚠️ {omitted} file(s) omitted due to context size limit.\n"
            )
            file_sections.append(omit_note)

        return header + "\n".join(file_sections)

    def summary(self) -> dict:
        from collections import Counter
        lang_counts = Counter(f.language for f in self.files)
        return {
            "project_name": self.project_name,
            "total_files": len(self.files),
            "languages": dict(lang_counts),
            "total_size_kb": round(sum(f.size_bytes for f in self.files) / 1024, 1),
        }
