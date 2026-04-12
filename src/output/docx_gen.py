"""
Layer 3 - Output: Generate a professional .docx technical documentation file.
"""

from pathlib import Path
from dataclasses import dataclass
from ..analysis.analyzer import AnalysisResult


def _layer_rationale(layer: dict, all_layers: list, language: str) -> str:
    """Generate a human-readable rationale sentence for a layer."""
    name = layer["name"]
    desc = layer.get("description", "").rstrip(".")
    comps = layer.get("components", [])
    techs = list(dict.fromkeys(c["tech"] for c in comps if c.get("tech")))[:3]
    conn_ids = layer.get("connections_to", [])
    id_to_name = {lyr["id"]: lyr["name"] for lyr in all_layers}
    conn_names = [id_to_name[c] for c in conn_ids if c in id_to_name]

    if language == "pt":
        tech_str = ", ".join(techs) if techs else "as tecnologias do projeto"
        n = len(comps)
        comp_str = f", composta por {n} componente{'s' if n != 1 else ''}" if n else ""
        conn_str = (f" Ela alimenta diretamente: {', '.join(conn_names)}."
                    if conn_names else "")
        return (f"É importante ressaltar que a camada \"{name}\" foi projetada "
                f"de forma isolada para {desc}{comp_str}, utilizando {tech_str}.{conn_str}")
    else:
        tech_str = ", ".join(techs) if techs else "the project's selected technologies"
        n = len(comps)
        comp_str = f", composed of {n} component{'s' if n != 1 else ''}" if n else ""
        conn_str = (f" It feeds directly into: {', '.join(conn_names)}."
                    if conn_names else "")
        return (f"It is important to note that the \"{name}\" layer was designed "
                f"in isolation to {desc}{comp_str}, using {tech_str}.{conn_str}")


@dataclass
class DocxGenerator:
    output_dir: str = "./output"
    language: str = "pt"

    def generate(self, result: AnalysisResult, diagram_path: str | None = None) -> str:
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn
        import docx.oxml

        doc = Document()

        # ── Styles ──────────────────────────────────────────────────────────
        style = doc.styles["Normal"]
        style.font.name = "Calibri"
        style.font.size = Pt(11)

        # ── Cover ────────────────────────────────────────────────────────────
        title_p = doc.add_paragraph()
        title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = title_p.add_run(result.project_name)
        run.bold = True
        run.font.size = Pt(28)
        run.font.color.rgb = RGBColor(0x1D, 0x35, 0x57)

        subtitle_label = "Documentação Técnica de Arquitetura" if self.language == "pt" else "Technical Architecture Documentation"
        sub_p = doc.add_paragraph()
        sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sub_run = sub_p.add_run(subtitle_label)
        sub_run.italic = True
        sub_run.font.size = Pt(14)

        doc.add_paragraph()

        # ── Section helper ───────────────────────────────────────────────────
        def add_section(title: str):
            h = doc.add_heading(title, level=1)
            h.runs[0].font.color.rgb = RGBColor(0x1D, 0x35, 0x57)

        def add_subsection(title: str):
            h = doc.add_heading(title, level=2)
            h.runs[0].font.color.rgb = RGBColor(0x45, 0x78, 0x9B)

        def add_bullet(text: str):
            p = doc.add_paragraph(text, style="List Bullet")
            p.runs[0].font.size = Pt(11)

        def add_info_block(text: str):
            """Render a light-blue callout box with a blue left border."""
            from docx.oxml import OxmlElement
            p = doc.add_paragraph()
            pPr = p._p.get_or_add_pPr()

            # Left border (thick blue bar)
            pBdr = OxmlElement("w:pBdr")
            left = OxmlElement("w:left")
            left.set(qn("w:val"), "thick")
            left.set(qn("w:sz"), "24")
            left.set(qn("w:space"), "4")
            left.set(qn("w:color"), "2563EB")
            pBdr.append(left)
            pPr.append(pBdr)

            # Light-blue background shading
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), "DBEAFE")
            pPr.append(shd)

            # Indentation
            ind = OxmlElement("w:ind")
            ind.set(qn("w:left"), "200")
            pPr.append(ind)

            run = p.add_run(text)
            run.italic = True
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor(0x1E, 0x40, 0xAF)
            doc.add_paragraph()  # breathing space after block

        # ── 1. Overview ──────────────────────────────────────────────────────
        section_title = "1. Visão Geral do Projeto" if self.language == "pt" else "1. Project Overview"
        add_section(section_title)
        doc.add_paragraph(result.description)

        tech_title = "Stack Tecnológico" if self.language == "pt" else "Technology Stack"
        add_subsection(tech_title)
        for tech in result.tech_stack:
            add_bullet(tech)

        # ── 2. Architecture Layers ───────────────────────────────────────────
        arch_title = "2. Arquitetura em Camadas" if self.language == "pt" else "2. Layered Architecture"
        add_section(arch_title)

        for layer in result.layers:
            add_subsection(f"{layer['name']}")
            doc.add_paragraph(layer.get("description", ""))

            # Info block — design rationale for this layer
            add_info_block(_layer_rationale(layer, result.layers, self.language))

            components = layer.get("components", [])
            if components:
                comp_label = "Componentes:" if self.language == "pt" else "Components:"
                doc.add_paragraph(comp_label)
                for comp in components:
                    tech_note = f" ({comp['tech']})" if comp.get("tech") else ""
                    add_bullet(f"{comp['name']}{tech_note} - {comp.get('description', '')}")

        # ── 3. Diagram ───────────────────────────────────────────────────────
        if diagram_path and Path(diagram_path).exists():
            diag_title = "3. Diagrama da Arquitetura" if self.language == "pt" else "3. Architecture Diagram"
            add_section(diag_title)
            doc.add_picture(diagram_path, width=Inches(6.5))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER

        # ── 4. Good Practices ────────────────────────────────────────────────
        next_n = 4 if diagram_path else 3
        gp_title = f"{next_n}. Boas Práticas Identificadas" if self.language == "pt" else f"{next_n}. Good Practices Identified"
        add_section(gp_title)
        for gp in result.good_practices:
            add_bullet(gp)

        # ── 5. Improvement Points ────────────────────────────────────────────
        next_n += 1
        ip_title = f"{next_n}. Pontos de Melhoria" if self.language == "pt" else f"{next_n}. Improvement Points"
        add_section(ip_title)
        for ip in result.improvement_points:
            add_bullet(ip)

        # ── 6. User Corrections (if any) ─────────────────────────────────────
        if result.user_corrections:
            next_n += 1
            uc_title = f"{next_n}. Ajustes Validados pelo Usuário" if self.language == "pt" else f"{next_n}. User-Validated Adjustments"
            add_section(uc_title)
            for uc in result.user_corrections:
                add_bullet(uc)

        # ── Save ─────────────────────────────────────────────────────────────
        out_path = Path(self.output_dir) / f"{self._safe_name(result.project_name)}_architecture.docx"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out_path))
        return str(out_path)

    def _safe_name(self, name: str) -> str:
        return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
