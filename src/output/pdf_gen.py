"""
Layer 3 - Output: Generate a professional PDF technical documentation file.
Uses reportlab for full layout control.
"""

from pathlib import Path
from dataclasses import dataclass
from ..analysis.analyzer import AnalysisResult
from .docx_gen import _layer_rationale
from src.logger import get_logger

log = get_logger(__name__)


# ── Color palette ────────────────────────────────────────────────────────────
DARK_BLUE = (0x1D / 255, 0x35 / 255, 0x57 / 255)
MID_BLUE  = (0x45 / 255, 0x78 / 255, 0x9B / 255)
LIGHT_BG  = (0xF4 / 255, 0xF7 / 255, 0xFB / 255)
WHITE     = (1, 1, 1)
BLACK     = (0, 0, 0)
GREY_TEXT = (0.35, 0.35, 0.35)


@dataclass
class PdfGenerator:
    output_dir: str = "./output"
    language: str = "pt"

    def generate(self, result: AnalysisResult, diagram_path: str | None = None,
                 interactive_diagram_path: str | None = None) -> str:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Image,
            HRFlowable, ListFlowable, ListItem, PageBreak,
        )
        from reportlab.lib import colors

        out_path = Path(self.output_dir) / f"{self._safe_name(result.project_name)}_architecture.pdf"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        doc = SimpleDocTemplate(
            str(out_path),
            pagesize=A4,
            leftMargin=2.5 * cm, rightMargin=2.5 * cm,
            topMargin=2 * cm, bottomMargin=2 * cm,
            title=result.project_name,
        )

        styles = getSampleStyleSheet()
        story = []

        # ── Custom styles ────────────────────────────────────────────────────
        def rgb(t): return colors.Color(*t)

        s_title = ParagraphStyle("DocTitle", fontSize=28, textColor=rgb(DARK_BLUE),
                                  alignment=TA_CENTER, spaceAfter=6, fontName="Helvetica-Bold")
        s_subtitle = ParagraphStyle("DocSubtitle", fontSize=14, textColor=rgb(MID_BLUE),
                                     alignment=TA_CENTER, spaceAfter=20, fontName="Helvetica-Oblique")
        s_h1 = ParagraphStyle("H1", fontSize=16, textColor=rgb(DARK_BLUE), spaceBefore=16,
                               spaceAfter=6, fontName="Helvetica-Bold")
        s_h2 = ParagraphStyle("H2", fontSize=13, textColor=rgb(MID_BLUE), spaceBefore=10,
                               spaceAfter=4, fontName="Helvetica-Bold")
        s_body = ParagraphStyle("Body", fontSize=11, textColor=rgb(BLACK),
                                 alignment=TA_JUSTIFY, spaceAfter=6, leading=16)
        s_bullet = ParagraphStyle("Bullet", fontSize=11, textColor=rgb(GREY_TEXT),
                                   leftIndent=16, spaceAfter=3, leading=15,
                                   bulletIndent=6)
        s_info = ParagraphStyle(
            "InfoBlock", fontSize=10, textColor=colors.HexColor("#1E40AF"),
            fontName="Helvetica-Oblique", leading=15,
            leftIndent=12, rightIndent=12, spaceAfter=8, spaceBefore=4,
        )

        INFO_BG = colors.HexColor("#DBEAFE")
        INFO_BORDER = colors.HexColor("#2563EB")

        def add_info_block(text: str):
            """Render a light-blue callout box with colored left border."""
            from reportlab.platypus import Table, TableStyle
            from reportlab.lib.units import cm

            # Left accent bar (thin colored column) + text column
            bar_w = 0.22 * cm
            content_w = doc.width - bar_w
            data = [["", Paragraph(text, s_info)]]
            tbl = Table(data, colWidths=[bar_w, content_w])
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, 0), INFO_BORDER),
                ("BACKGROUND", (1, 0), (1, 0), INFO_BG),
                ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING",  (1, 0), (1, 0), 10),
                ("RIGHTPADDING", (1, 0), (1, 0), 8),
                ("TOPPADDING",   (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 7),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [INFO_BG]),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 0.3 * cm))

        # ── Cover ─────────────────────────────────────────────────────────────
        story.append(Spacer(1, 3 * cm))
        story.append(Paragraph(result.project_name, s_title))
        subtitle_text = "Documentação Técnica de Arquitetura" if self.language == "pt" else "Technical Architecture Documentation"
        story.append(Paragraph(subtitle_text, s_subtitle))
        story.append(HRFlowable(width="100%", thickness=1, color=rgb(MID_BLUE)))
        story.append(Spacer(1, 1 * cm))

        # ── 1. Overview ───────────────────────────────────────────────────────
        h1_label = "1. Visão Geral do Projeto" if self.language == "pt" else "1. Project Overview"
        story.append(Paragraph(h1_label, s_h1))
        story.append(Paragraph(result.description, s_body))

        tech_label = "Stack Tecnológico:" if self.language == "pt" else "Technology Stack:"
        story.append(Paragraph(tech_label, s_h2))
        items = [ListItem(Paragraph(t, s_bullet)) for t in result.tech_stack]
        story.append(ListFlowable(items, bulletType="bullet"))
        story.append(Spacer(1, 0.5 * cm))

        # ── 2. Layers ─────────────────────────────────────────────────────────
        arch_label = "2. Arquitetura em Camadas" if self.language == "pt" else "2. Layered Architecture"
        story.append(Paragraph(arch_label, s_h1))

        for layer in result.layers:
            story.append(Paragraph(layer["name"], s_h2))
            story.append(Paragraph(layer.get("description", ""), s_body))

            # Info block — design rationale
            add_info_block(_layer_rationale(layer, result.layers, self.language))

            components = layer.get("components", [])
            if components:
                comp_label = "Componentes:" if self.language == "pt" else "Components:"
                story.append(Paragraph(comp_label, s_h2))
                litems = []
                for comp in components:
                    tech_note = f" ({comp['tech']})" if comp.get("tech") else ""
                    text = f"<b>{comp['name']}</b>{tech_note} - {comp.get('description', '')}"
                    litems.append(ListItem(Paragraph(text, s_bullet)))
                story.append(ListFlowable(litems, bulletType="bullet"))

        # ── 3. Diagram ────────────────────────────────────────────────────────
        has_static = diagram_path and Path(diagram_path).exists()
        has_interactive = interactive_diagram_path and Path(interactive_diagram_path).exists()
        if has_static or has_interactive:
            story.append(PageBreak())
            diag_label = "3. Diagrama da Arquitetura" if self.language == "pt" else "3. Architecture Diagram"
            story.append(Paragraph(diag_label, s_h1))
            story.append(Spacer(1, 0.3 * cm))

            from reportlab.lib.pagesizes import A4
            max_w = A4[0] - 5 * cm

            if has_static:
                story.append(Image(diagram_path, width=max_w, height=max_w * 0.7))

            if has_interactive:
                p_int = Path(interactive_diagram_path)
                size = p_int.stat().st_size
                if size < 1024:
                    log.warning("PDF: interactive PNG too small (%d bytes), skipping: %s", size, p_int)
                else:
                    if has_static:
                        story.append(Spacer(1, 0.6 * cm))
                    sub_label = "Diagrama Interativo (Node-Graph)" if self.language == "pt" else "Interactive Diagram (Node-Graph)"
                    story.append(Paragraph(sub_label, s_h2))
                    story.append(Spacer(1, 0.2 * cm))
                    try:
                        story.append(Image(str(p_int), width=max_w, height=max_w * 0.625))
                    except Exception as exc:
                        log.error("PDF: failed to embed interactive PNG at %s: %s", p_int, exc, exc_info=True)
            elif interactive_diagram_path:
                log.warning("PDF: interactive_diagram_path provided but file missing: %s", interactive_diagram_path)
            else:
                log.info("PDF: no interactive_diagram_path provided - skipping interactive subsection")

        # ── Quality Score ────────────────────────────────────────────────────
        next_n = 4 if (has_static or has_interactive) else 3
        score = result.quality_score or {}
        if score.get("total"):
            qs_label = f"{next_n}. Score de Qualidade Arquitetural" if self.language == "pt" else f"{next_n}. Architecture Quality Score"
            story.append(Paragraph(qs_label, s_h1))

            total = score.get("total", 0)
            label_pt = ("Excelente" if total >= 80 else
                        "Bom, com pontos a evoluir" if total >= 60 else
                        "Funcional mas com lacunas relevantes" if total >= 40 else
                        "Atencao: problemas estruturais")
            label_en = ("Excellent" if total >= 80 else
                        "Good, with room to improve" if total >= 60 else
                        "Functional but with relevant gaps" if total >= 40 else
                        "Warning: structural problems")
            label = label_pt if self.language == "pt" else label_en

            score_color = ("#10B981" if total >= 80 else
                           "#EAB308" if total >= 60 else
                           "#F97316" if total >= 40 else "#EF4444")

            s_score = ParagraphStyle("ScoreBig", fontSize=24, textColor=colors.HexColor(score_color),
                                      fontName="Helvetica-Bold", spaceAfter=2)
            story.append(Paragraph(f"{total}/100", s_score))
            s_score_label = ParagraphStyle("ScoreLabel", fontSize=12, textColor=rgb(MID_BLUE),
                                            fontName="Helvetica-Oblique", spaceAfter=8)
            story.append(Paragraph(label, s_score_label))

            if score.get("rationale"):
                story.append(Paragraph(score["rationale"], s_body))

            breakdown = score.get("breakdown") or {}
            dim_labels_pt = {"arquitetura": "Arquitetura", "codigo": "Codigo",
                             "documentacao": "Documentacao", "testabilidade": "Testabilidade",
                             "devops": "DevOps"}
            dim_labels_en = {"arquitetura": "Architecture", "codigo": "Code",
                             "documentacao": "Documentation", "testabilidade": "Testability",
                             "devops": "DevOps"}
            dim_labels = dim_labels_pt if self.language == "pt" else dim_labels_en
            qs_items = [ListItem(Paragraph(f"{dim_labels[k]}: {int(breakdown.get(k, 0))}/20", s_bullet))
                        for k in dim_labels]
            story.append(ListFlowable(qs_items, bulletType="bullet"))
            story.append(Spacer(1, 0.4 * cm))
            next_n += 1

        # ── Architecture Pattern (classification badge) ──────────────────────
        pattern = getattr(result, "architecture_pattern", None) or {}
        matches = pattern.get("matches") or []
        if matches:
            ap_label = (f"{next_n}. Padrao Arquitetural"
                        if self.language == "pt"
                        else f"{next_n}. Architectural Pattern")
            story.append(Paragraph(ap_label, s_h1))

            primary = pattern.get("primary") or matches[0]["name"]
            primary_pct = matches[0].get("adherence", 0)
            s_pattern_primary = ParagraphStyle(
                "PatternPrimary", fontSize=18, textColor=rgb(DARK_BLUE),
                fontName="Helvetica-Bold", spaceAfter=2,
            )
            s_pattern_pct = ParagraphStyle(
                "PatternPct", fontSize=18, textColor=colors.HexColor("#10B981"),
                fontName="Helvetica-Bold", spaceAfter=8,
            )
            story.append(Paragraph(primary, s_pattern_primary))
            story.append(Paragraph(f"{primary_pct}%", s_pattern_pct))

            if pattern.get("summary"):
                story.append(Paragraph(pattern["summary"], s_body))

            ev_lbl = "Evidencias:" if self.language == "pt" else "Evidence:"
            for m in matches:
                story.append(Paragraph(f"<b>{m['name']}</b> - {m.get('adherence', 0)}%", s_h2))
                if m.get("rationale"):
                    story.append(Paragraph(m["rationale"], s_body))
                evidence = m.get("evidence") or []
                if evidence:
                    story.append(Paragraph(f"<b>{ev_lbl}</b>", s_body))
                    ev_items = [ListItem(Paragraph(e, s_bullet)) for e in evidence]
                    story.append(ListFlowable(ev_items, bulletType="bullet"))
            story.append(Spacer(1, 0.3 * cm))
            next_n += 1

        # ── Use Cases (sequence diagrams) ────────────────────────────────────
        use_cases = getattr(result, "use_cases", None) or []
        if use_cases:
            from .mermaid_renderer import render_mermaid_png
            from reportlab.lib.pagesizes import A4
            uc_label = f"{next_n}. Diagramas de Sequencia" if self.language == "pt" else f"{next_n}. Sequence Diagrams"
            story.append(Paragraph(uc_label, s_h1))
            s_code = ParagraphStyle(
                "MermaidCode", fontSize=9, fontName="Courier",
                textColor=colors.HexColor("#1E40AF"),
                leftIndent=12, rightIndent=12, leading=12,
                spaceBefore=4, spaceAfter=8,
                backColor=colors.HexColor("#F1F5F9"),
                borderColor=colors.HexColor("#CBD5E1"),
                borderWidth=0.5, borderPadding=6,
            )
            max_w = A4[0] - 5 * cm
            for uc in use_cases:
                story.append(Paragraph(uc.get("name", ""), s_h2))
                if uc.get("description"):
                    story.append(Paragraph(uc["description"], s_body))
                diagram = (uc.get("sequence_diagram") or "").strip()
                if not diagram:
                    continue
                # Render via kroki.io (cached). Fall back to monospace text
                # if the service is unreachable or rejects the diagram.
                png_path = render_mermaid_png(diagram)
                if png_path:
                    try:
                        from PIL import Image as PILImage
                        with PILImage.open(str(png_path)) as img:
                            ratio = img.height / img.width if img.width else 0.6
                        img_w = min(max_w, 16 * cm)
                        story.append(Image(str(png_path), width=img_w, height=img_w * ratio))
                    except Exception as exc:
                        log.warning("PDF: failed to embed kroki PNG, falling back to text: %s", exc)
                        png_path = None
                if not png_path:
                    log.warning("PDF: rendering failed, embedding text for use case '%s'", uc.get("name", ""))
                    for raw_line in diagram.split("\n"):
                        leading = len(raw_line) - len(raw_line.lstrip(" "))
                        body_text = (raw_line[leading:]
                                     .replace("&", "&amp;")
                                     .replace("<", "&lt;")
                                     .replace(">", "&gt;"))
                        line_html = ("&nbsp;" * leading) + (body_text or "&nbsp;")
                        story.append(Paragraph(line_html, s_code))
                story.append(Spacer(1, 0.3 * cm))
            next_n += 1

        # ── Architecture Decision Records (ADRs) ─────────────────────────────
        adrs = getattr(result, "adrs", None) or []
        if adrs:
            adr_label = (f"{next_n}. Decisoes Arquiteturais (ADRs)"
                         if self.language == "pt"
                         else f"{next_n}. Architecture Decision Records (ADRs)")
            story.append(Paragraph(adr_label, s_h1))
            intro = (
                "Decisoes arquiteturais identificadas no projeto. Cada ADR descreve o "
                "contexto, a decisao tomada e suas consequencias - formato MADR."
                if self.language == "pt" else
                "Architectural decisions identified in the project. Each ADR describes the "
                "context, the decision and its consequences - MADR format."
            )
            story.append(Paragraph(intro, s_body))

            ctx_lbl = "Contexto:" if self.language == "pt" else "Context:"
            dec_lbl = "Decisao:" if self.language == "pt" else "Decision:"
            cons_lbl = "Consequencias:" if self.language == "pt" else "Consequences:"
            alt_lbl = "Alternativas:" if self.language == "pt" else "Alternatives:"
            status_lbl = "Status:"

            for i, adr in enumerate(adrs, start=1):
                num = f"{i:04d}"
                title = (adr.get("title") or "Untitled").strip()
                status = (adr.get("status") or "accepted").capitalize()
                story.append(Paragraph(f"ADR-{num}: {title}", s_h2))
                story.append(Paragraph(f"<b>{status_lbl}</b> {status}", s_body))

                def _line(label: str, value: str):
                    value = (value or "").strip()
                    if value:
                        story.append(Paragraph(f"<b>{label}</b> {value}", s_body))

                _line(ctx_lbl, adr.get("context", ""))
                _line(dec_lbl, adr.get("decision", ""))
                _line(cons_lbl, adr.get("consequences", ""))
                _line(alt_lbl, adr.get("alternatives", ""))
                story.append(Spacer(1, 0.25 * cm))
            next_n += 1

        # ── Good Practices ───────────────────────────────────────────────────
        gp_label = f"{next_n}. Boas Práticas Identificadas" if self.language == "pt" else f"{next_n}. Good Practices"
        story.append(Paragraph(gp_label, s_h1))
        gp_items = [ListItem(Paragraph(gp, s_bullet)) for gp in result.good_practices]
        story.append(ListFlowable(gp_items, bulletType="bullet"))

        # ── Improvement Points ───────────────────────────────────────────────
        next_n += 1
        ip_label = f"{next_n}. Pontos de Melhoria" if self.language == "pt" else f"{next_n}. Improvement Points"
        story.append(Paragraph(ip_label, s_h1))
        ip_items = [ListItem(Paragraph(ip, s_bullet)) for ip in result.improvement_points]
        story.append(ListFlowable(ip_items, bulletType="bullet"))

        doc.build(story)
        return str(out_path)

    def _safe_name(self, name: str) -> str:
        return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
