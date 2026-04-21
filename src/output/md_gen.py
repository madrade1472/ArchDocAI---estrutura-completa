"""
Layer 3 - Output: Generate a clean Markdown documentation file.
Compatible with GitHub, GitLab, Notion, Obsidian and any Markdown viewer.
"""

from pathlib import Path
from dataclasses import dataclass
from ..analysis.analyzer import AnalysisResult
from .docx_gen import _layer_rationale


@dataclass
class MarkdownGenerator:
    output_dir: str = "./output"
    language: str = "pt"

    def generate(self, result: AnalysisResult, mermaid: str | None = None) -> str:
        lines: list[str] = []
        L = self.language

        # ── Cover ────────────────────────────────────────────────────────────
        lines.append(f"# {result.project_name}")
        subtitle = "Documentacao Tecnica de Arquitetura" if L == "pt" else "Technical Architecture Documentation"
        lines.append(f"*{subtitle}*")
        lines.append("")
        lines.append("---")
        lines.append("")

        # ── Table of contents ─────────────────────────────────────────────────
        toc_title = "## Sumario" if L == "pt" else "## Table of Contents"
        lines.append(toc_title)
        lines.append("")
        items = [
            ("1. Visao Geral" if L == "pt" else "1. Overview", "#1-visao-geral" if L == "pt" else "#1-overview"),
            ("2. Stack Tecnologico" if L == "pt" else "2. Technology Stack", "#2-stack-tecnologico" if L == "pt" else "#2-technology-stack"),
            ("3. Arquitetura em Camadas" if L == "pt" else "3. Layered Architecture", "#3-arquitetura-em-camadas" if L == "pt" else "#3-layered-architecture"),
        ]
        for layer in result.layers:
            slug = self._slug(layer["name"])
            items.append((f"   - {layer['name']}", f"#{slug}"))
        if mermaid:
            items.append(("4. Diagrama" if L == "pt" else "4. Diagram", "#4-diagrama" if L == "pt" else "#4-diagram"))
        next_n = 5 if mermaid else 4
        items.append(
            (f"{next_n}. Boas Praticas" if L == "pt" else f"{next_n}. Good Practices",
             f"#{next_n}-boas-praticas" if L == "pt" else f"#{next_n}-good-practices"),
        )
        next_n += 1
        items.append(
            (f"{next_n}. Pontos de Melhoria" if L == "pt" else f"{next_n}. Improvement Points",
             f"#{next_n}-pontos-de-melhoria" if L == "pt" else f"#{next_n}-improvement-points"),
        )
        for label, anchor in items:
            lines.append(f"- [{label}]({anchor})")
        lines.append("")
        lines.append("---")
        lines.append("")

        # ── 1. Overview ───────────────────────────────────────────────────────
        h1 = "## 1. Visao Geral" if L == "pt" else "## 1. Overview"
        lines.append(h1)
        lines.append("")
        lines.append(result.description)
        lines.append("")

        # ── 2. Tech stack ─────────────────────────────────────────────────────
        h2 = "## 2. Stack Tecnologico" if L == "pt" else "## 2. Technology Stack"
        lines.append(h2)
        lines.append("")
        for tech in result.tech_stack:
            lines.append(f"- {tech}")
        lines.append("")

        # ── 3. Layers ─────────────────────────────────────────────────────────
        h3 = "## 3. Arquitetura em Camadas" if L == "pt" else "## 3. Layered Architecture"
        lines.append(h3)
        lines.append("")

        for layer in result.layers:
            lines.append(f"### {layer['name']}")
            lines.append("")
            lines.append(layer.get("description", ""))
            lines.append("")

            # Info block as blockquote
            rationale = _layer_rationale(layer, result.layers, L)
            lines.append(f"> {rationale}")
            lines.append("")

            components = layer.get("components", [])
            if components:
                comp_label = "**Componentes:**" if L == "pt" else "**Components:**"
                lines.append(comp_label)
                lines.append("")
                lines.append("| Componente | Tecnologia | Descricao |" if L == "pt" else "| Component | Technology | Description |")
                lines.append("|---|---|---|")
                for comp in components:
                    name = comp.get("name", "")
                    tech = comp.get("tech", "")
                    desc = comp.get("description", "")
                    lines.append(f"| **{name}** | {tech} | {desc} |")
                lines.append("")

        # ── 4. Diagram (Mermaid) ──────────────────────────────────────────────
        if mermaid:
            diag_label = "## 4. Diagrama" if L == "pt" else "## 4. Diagram"
            lines.append(diag_label)
            lines.append("")
            lines.append("```mermaid")
            lines.append(mermaid)
            lines.append("```")
            lines.append("")

        # ── Quality Score ─────────────────────────────────────────────────────
        n = 5 if mermaid else 4
        score = result.quality_score or {}
        if score.get("total"):
            qs_label = f"## {n}. Score de Qualidade Arquitetural" if L == "pt" else f"## {n}. Architecture Quality Score"
            lines.append(qs_label)
            lines.append("")
            total = score.get("total", 0)
            label_pt = ("Excelente" if total >= 80 else
                        "Bom, com pontos a evoluir" if total >= 60 else
                        "Funcional mas com lacunas relevantes" if total >= 40 else
                        "Atencao: problemas estruturais")
            label_en = ("Excellent" if total >= 80 else
                        "Good, with room to improve" if total >= 60 else
                        "Functional but with relevant gaps" if total >= 40 else
                        "Warning: structural problems")
            label = label_pt if L == "pt" else label_en
            lines.append(f"**{total}/100** - {label}")
            lines.append("")
            if score.get("rationale"):
                lines.append(score["rationale"])
                lines.append("")
            breakdown = score.get("breakdown") or {}
            dim_labels_pt = {"arquitetura": "Arquitetura", "codigo": "Codigo",
                             "documentacao": "Documentacao", "testabilidade": "Testabilidade",
                             "devops": "DevOps"}
            dim_labels_en = {"arquitetura": "Architecture", "codigo": "Code",
                             "documentacao": "Documentation", "testabilidade": "Testability",
                             "devops": "DevOps"}
            dim_labels = dim_labels_pt if L == "pt" else dim_labels_en
            lines.append("| Dimensao | Score |" if L == "pt" else "| Dimension | Score |")
            lines.append("|---|---|")
            for k, name in dim_labels.items():
                lines.append(f"| {name} | {int(breakdown.get(k, 0))}/20 |")
            lines.append("")
            n += 1

        # ── Good Practices ────────────────────────────────────────────────────
        gp_label = f"## {n}. Boas Praticas Identificadas" if L == "pt" else f"## {n}. Good Practices Identified"
        lines.append(gp_label)
        lines.append("")
        for gp in result.good_practices:
            lines.append(f"- {gp}")
        lines.append("")

        # ── Improvement Points ────────────────────────────────────────────────
        n += 1
        ip_label = f"## {n}. Pontos de Melhoria" if L == "pt" else f"## {n}. Improvement Points"
        lines.append(ip_label)
        lines.append("")
        for ip in result.improvement_points:
            lines.append(f"- {ip}")
        lines.append("")

        # ── User corrections ──────────────────────────────────────────────────
        if result.user_corrections:
            n += 1
            uc_label = f"## {n}. Ajustes do Usuario" if L == "pt" else f"## {n}. User Adjustments"
            lines.append(uc_label)
            lines.append("")
            for uc in result.user_corrections:
                lines.append(f"- {uc}")
            lines.append("")

        # ── Footer ────────────────────────────────────────────────────────────
        lines.append("---")
        lines.append("")
        footer = "*Gerado por ArchDocAI*" if L == "pt" else "*Generated by ArchDocAI*"
        lines.append(footer)
        lines.append("")

        content = "\n".join(lines)
        out_path = Path(self.output_dir) / f"{self._safe_name(result.project_name)}_architecture.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        return str(out_path)

    def _safe_name(self, name: str) -> str:
        return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)

    def _slug(self, name: str) -> str:
        import re
        s = name.lower()
        s = re.sub(r"[^\w\s-]", "", s)
        s = re.sub(r"[\s_]+", "-", s).strip("-")
        return s
