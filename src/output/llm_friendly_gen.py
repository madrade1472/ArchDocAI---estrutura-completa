"""
Layer 3 - Output: Generate an LLM-friendly knowledge file (XML format).

Produces a single dense XML file that bundles the architectural analysis in a
format optimized for re-feeding into other LLMs as context (RAG, agent
toolchains, Cursor/Claude project setup, etc).

Inspired by repomix.com but focused on the architectural understanding rather
than raw source code dump.
"""

from pathlib import Path
from dataclasses import dataclass
from xml.sax.saxutils import escape

from ..analysis.analyzer import AnalysisResult


@dataclass
class LLMFriendlyGenerator:
    output_dir: str = "./output"

    def generate(self, result: AnalysisResult, scanned_files: list | None = None) -> str:
        """Render the analysis as a dense XML knowledge file.

        scanned_files (optional): list of ScannedFile objects from the ingestion
        scanner. When provided, the output includes a <key_files> section listing
        each file's path, language and size for downstream agents to navigate.
        """
        out_path = Path(self.output_dir) / f"{self._safe_name(result.project_name)}_archdoc.xml"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []
        lines.append('<?xml version="1.0" encoding="UTF-8"?>')
        lines.append('<archdocai version="1.0" generator="ArchDocAI" '
                     'purpose="Structured architectural knowledge for LLM consumption">')
        lines.append("")

        # ── Project metadata ────────────────────────────────────────────────
        lines.append("  <project>")
        lines.append(f"    <name>{escape(result.project_name)}</name>")
        lines.append(f"    <description>{escape(result.description)}</description>")
        lines.append("    <tech_stack>")
        for tech in result.tech_stack:
            lines.append(f"      <tech>{escape(tech)}</tech>")
        lines.append("    </tech_stack>")
        lines.append("  </project>")
        lines.append("")

        # ── Quality score (when present) ────────────────────────────────────
        score = result.quality_score or {}
        if score.get("total"):
            breakdown = score.get("breakdown") or {}
            attrs = " ".join(
                f'{k}="{int(breakdown.get(k, 0))}"'
                for k in ("arquitetura", "codigo", "documentacao", "testabilidade", "devops")
            )
            lines.append(f'  <quality_score total="{int(score["total"])}" {attrs}>')
            if score.get("rationale"):
                lines.append(f"    <rationale>{escape(score['rationale'])}</rationale>")
            lines.append("  </quality_score>")
            lines.append("")

        # ── Architecture layers and components ──────────────────────────────
        lines.append("  <architecture>")
        for layer in result.layers:
            color = layer.get("color", "")
            lid = layer.get("id", "")
            lname = layer.get("name", "")
            lines.append(f'    <layer id="{escape(lid)}" name="{escape(lname)}" color="{escape(color)}">')
            if layer.get("description"):
                lines.append(f"      <description>{escape(layer['description'])}</description>")
            connections = layer.get("connections_to") or []
            if connections:
                joined = ",".join(escape(c) for c in connections)
                lines.append(f"      <feeds_into>{joined}</feeds_into>")
            comps = layer.get("components") or []
            if comps:
                lines.append("      <components>")
                for comp in comps:
                    cname = escape(comp.get("name", ""))
                    ctype = escape(comp.get("type", "process"))
                    ctech = escape(comp.get("tech", ""))
                    lines.append(f'        <component name="{cname}" type="{ctype}" tech="{ctech}">')
                    if comp.get("description"):
                        lines.append(f"          <description>{escape(comp['description'])}</description>")
                    deps = comp.get("connections_to") or []
                    if deps:
                        joined = ",".join(escape(d) for d in deps)
                        lines.append(f"          <feeds_into>{joined}</feeds_into>")
                    lines.append("        </component>")
                lines.append("      </components>")
            lines.append("    </layer>")
        lines.append("  </architecture>")
        lines.append("")

        # ── Practices and improvement points ────────────────────────────────
        if result.good_practices:
            lines.append("  <good_practices>")
            for gp in result.good_practices:
                lines.append(f"    <item>{escape(gp)}</item>")
            lines.append("  </good_practices>")
            lines.append("")

        if result.improvement_points:
            lines.append("  <improvement_points>")
            for ip in result.improvement_points:
                lines.append(f"    <item>{escape(ip)}</item>")
            lines.append("  </improvement_points>")
            lines.append("")

        # ── Architecture Decision Records (when present) ────────────────────
        adrs = getattr(result, "adrs", None) or []
        if adrs:
            lines.append("  <adrs>")
            lines.append("    <!-- Architecture Decision Records inferred from the codebase, "
                         "MADR-inspired structure. Use these to understand WHY the project "
                         "was built this way. -->")
            for i, adr in enumerate(adrs, start=1):
                num = f"{i:04d}"
                title = escape((adr.get("title") or "").strip())
                status = escape((adr.get("status") or "accepted").lower())
                lines.append(f'    <adr id="ADR-{num}" status="{status}">')
                lines.append(f"      <title>{title}</title>")
                if (adr.get("context") or "").strip():
                    lines.append(f"      <context>{escape(adr['context'].strip())}</context>")
                if (adr.get("decision") or "").strip():
                    lines.append(f"      <decision>{escape(adr['decision'].strip())}</decision>")
                if (adr.get("consequences") or "").strip():
                    lines.append(f"      <consequences>{escape(adr['consequences'].strip())}</consequences>")
                if (adr.get("alternatives") or "").strip():
                    lines.append(f"      <alternatives>{escape(adr['alternatives'].strip())}</alternatives>")
                lines.append("    </adr>")
            lines.append("  </adrs>")
            lines.append("")

        # ── Key files (when scanned context is available) ───────────────────
        if scanned_files:
            lines.append("  <key_files>")
            lines.append("    <!-- Files selected by the scanner as most architecturally relevant. "
                         "Use these paths to navigate the repo. -->")
            for f in scanned_files:
                rel = escape(getattr(f, "relative_path", ""))
                lang = escape(getattr(f, "language", ""))
                size = int(getattr(f, "size_bytes", 0))
                lines.append(f'    <file path="{rel}" language="{lang}" size_bytes="{size}" />')
            lines.append("  </key_files>")
            lines.append("")

        # ── User corrections (when present) ─────────────────────────────────
        if result.user_corrections:
            lines.append("  <user_corrections>")
            for uc in result.user_corrections:
                lines.append(f"    <item>{escape(uc)}</item>")
            lines.append("  </user_corrections>")
            lines.append("")

        # ── Usage hint for downstream LLMs ──────────────────────────────────
        lines.append("  <usage_hint>")
        lines.append("    This file describes the high-level architecture of the project. "
                     "Use it as initial context before reading source code. The components "
                     "listed under each layer represent functional roles, not necessarily "
                     "individual files. Refer to key_files for navigation.")
        lines.append("  </usage_hint>")

        lines.append("</archdocai>")

        out_path.write_text("\n".join(lines), encoding="utf-8")
        return str(out_path)

    def _safe_name(self, name: str) -> str:
        return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
