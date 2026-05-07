"""
Layer 3 - Output: Generate a polished PDF technical documentation file.
Uses reportlab for full layout control.

Visual design notes:
- Cover page is rendered without the running header/footer.
- All other pages carry a thin grey header (project name | ArchDocAI) and
  centered page numbers in the footer.
- Quality score and architecture-pattern adherence render as horizontal bar
  charts so the reader sees relative weights at a glance instead of raw text.
- ADRs render as left-accented cards (status badge + title) for scanability.
"""

from datetime import datetime
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
GREY_RULE = "#E5E7EB"
GREY_HDR  = "#94A3B8"


@dataclass
class PdfGenerator:
    output_dir: str = "./output"
    language: str = "pt"

    def generate(self, result: AnalysisResult, diagram_path: str | None = None,
                 interactive_diagram_path: str | None = None) -> str:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.platypus import (
            BaseDocTemplate, PageTemplate, Frame,
            Paragraph, Spacer, Image,
            HRFlowable, ListFlowable, ListItem, PageBreak,
            Table, TableStyle, KeepTogether,
        )
        from reportlab.lib import colors

        out_path = Path(self.output_dir) / f"{self._safe_name(result.project_name)}_architecture.pdf"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # ── Document with two page templates: cover (no header/footer) + body ─
        page_w, page_h = A4
        left_margin = right_margin = 2.5 * cm
        top_margin = 2.5 * cm
        bottom_margin = 2.0 * cm

        frame_body = Frame(
            left_margin, bottom_margin,
            page_w - left_margin - right_margin,
            page_h - top_margin - bottom_margin,
            id="body", showBoundary=0,
        )
        frame_cover = Frame(
            left_margin, bottom_margin,
            page_w - left_margin - right_margin,
            page_h - bottom_margin - 1.5 * cm,
            id="cover", showBoundary=0,
        )

        project_name = result.project_name or "Projeto"

        def _draw_cover_chrome(canvas, _doc):
            # Subtle accent strip at the top of the cover so the title page has
            # a sense of identity without overwhelming the reader.
            canvas.saveState()
            canvas.setFillColor(colors.Color(*DARK_BLUE))
            canvas.rect(0, page_h - 0.7 * cm, page_w, 0.7 * cm, fill=1, stroke=0)
            canvas.setFillColor(colors.Color(*MID_BLUE))
            canvas.rect(0, page_h - 0.78 * cm, page_w, 0.08 * cm, fill=1, stroke=0)
            canvas.restoreState()

        def _draw_body_chrome(canvas, doc):
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.HexColor(GREY_HDR))
            # Header: project name (left) | "ArchDocAI" (right)
            canvas.drawString(left_margin, page_h - 1.2 * cm, project_name)
            canvas.drawRightString(page_w - right_margin, page_h - 1.2 * cm, "ArchDocAI")
            # Thin rule under the header
            canvas.setStrokeColor(colors.HexColor(GREY_RULE))
            canvas.setLineWidth(0.4)
            canvas.line(
                left_margin, page_h - 1.4 * cm,
                page_w - right_margin, page_h - 1.4 * cm,
            )
            # Footer: centered page number, omitting the cover (page 1).
            page_num = canvas.getPageNumber()
            if page_num >= 2:
                canvas.drawCentredString(page_w / 2, 1.2 * cm, f"{page_num}")
            canvas.restoreState()

        doc = BaseDocTemplate(
            str(out_path),
            pagesize=A4,
            leftMargin=left_margin, rightMargin=right_margin,
            topMargin=top_margin, bottomMargin=bottom_margin,
            title=project_name,
        )
        doc.addPageTemplates([
            PageTemplate(id="cover", frames=[frame_cover], onPage=_draw_cover_chrome),
            PageTemplate(id="body", frames=[frame_body], onPage=_draw_body_chrome),
        ])

        # ── Custom styles ────────────────────────────────────────────────────
        styles = getSampleStyleSheet()

        def rgb(t): return colors.Color(*t)

        s_cover_title = ParagraphStyle(
            "CoverTitle", fontSize=34, textColor=rgb(DARK_BLUE),
            alignment=TA_CENTER, spaceAfter=8, leading=40, fontName="Helvetica-Bold",
        )
        s_cover_subtitle = ParagraphStyle(
            "CoverSubtitle", fontSize=14, textColor=rgb(MID_BLUE),
            alignment=TA_CENTER, spaceAfter=24, fontName="Helvetica-Oblique",
        )
        s_cover_meta = ParagraphStyle(
            "CoverMeta", fontSize=10, textColor=colors.HexColor(GREY_HDR),
            alignment=TA_CENTER, spaceAfter=4, fontName="Helvetica",
        )
        s_h1 = ParagraphStyle(
            "H1", fontSize=17, textColor=rgb(DARK_BLUE), spaceBefore=18,
            spaceAfter=10, fontName="Helvetica-Bold", leading=22, keepWithNext=1,
        )
        s_h2 = ParagraphStyle(
            "H2", fontSize=12.5, textColor=rgb(MID_BLUE), spaceBefore=10,
            spaceAfter=4, fontName="Helvetica-Bold", leading=16, keepWithNext=1,
        )
        s_body = ParagraphStyle(
            "Body", fontSize=10.5, textColor=rgb(BLACK),
            alignment=TA_LEFT, spaceAfter=6, leading=15.5,
        )
        s_bullet = ParagraphStyle(
            "Bullet", fontSize=10.5, textColor=rgb(GREY_TEXT),
            leftIndent=14, spaceAfter=3, leading=15, bulletIndent=4,
        )
        s_info = ParagraphStyle(
            "InfoBlock", fontSize=10, textColor=colors.HexColor("#1E40AF"),
            fontName="Helvetica-Oblique", leading=15,
            leftIndent=12, rightIndent=12, spaceAfter=8, spaceBefore=4,
        )
        s_card_title = ParagraphStyle(
            "CardTitle", fontSize=12, textColor=rgb(DARK_BLUE),
            fontName="Helvetica-Bold", spaceAfter=4, leading=16,
        )
        s_card_label = ParagraphStyle(
            "CardLabel", fontSize=9.5, textColor=rgb(MID_BLUE),
            fontName="Helvetica-Bold", spaceAfter=2, leading=13,
        )
        s_card_body = ParagraphStyle(
            "CardBody", fontSize=10.5, textColor=rgb(BLACK),
            spaceAfter=4, leading=14.5,
        )

        INFO_BG = colors.HexColor("#DBEAFE")
        INFO_BORDER = colors.HexColor("#2563EB")

        # ── Helpers ──────────────────────────────────────────────────────────
        def info_block(text: str):
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
            return tbl

        def hbar(value: int, max_value: int, color_hex: str,
                 total_width_cm: float = 8.0, height_cm: float = 0.32) -> Table:
            """A small horizontal progress bar built from a 1x2 table.

            Why a Table and not a Drawing: the bar must flow with the page
            content (page breaks, indents) rather than being absolutely placed.
            """
            ratio = 0.0 if max_value <= 0 else max(0.0, min(1.0, value / max_value))
            total = total_width_cm * cm
            fw = total * ratio
            ew = total - fw
            data = [["", ""]]
            # Avoid zero-width columns; reportlab dislikes those.
            EPS = 0.5
            widths = [max(fw, EPS), max(ew, EPS)]
            tbl = Table(data, colWidths=widths, rowHeights=[height_cm * cm])
            track_color = colors.HexColor("#EEF2F6")
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, 0),
                 colors.HexColor(color_hex) if fw >= EPS else track_color),
                ("BACKGROUND", (1, 0), (1, 0), track_color),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LINEBEFORE", (0, 0), (-1, -1), 0, colors.white),
                ("LINEAFTER",  (0, 0), (-1, -1), 0, colors.white),
            ]))
            return tbl

        def metric_row(label: str, value: int, max_value: int,
                       color_hex: str) -> Table:
            """[Label] [bar] [value/max]  — one row of a stat block."""
            cell_label = Paragraph(label, ParagraphStyle(
                "MetricLabel", fontSize=10.2, textColor=rgb(BLACK),
                fontName="Helvetica", leading=14,
            ))
            cell_bar = hbar(value, max_value, color_hex, total_width_cm=8.5)
            cell_val = Paragraph(
                f"<b>{value}</b><font size='8' color='#94A3B8'>/{max_value}</font>",
                ParagraphStyle(
                    "MetricVal", fontSize=11, textColor=rgb(DARK_BLUE),
                    fontName="Helvetica-Bold", alignment=TA_LEFT, leading=14,
                ),
            )
            tbl = Table(
                [[cell_label, cell_bar, cell_val]],
                colWidths=[4.0 * cm, 8.5 * cm, 2.0 * cm],
            )
            tbl.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            return tbl

        def adr_card(num: str, title: str, status: str, fields: list[tuple[str, str]]):
            """Boxed ADR with a coloured status badge top-right."""
            status_clean = (status or "accepted").lower()
            badge_color = {
                "accepted":   "#10B981",
                "proposed":   "#3B82F6",
                "deprecated": "#94A3B8",
                "superseded": "#F97316",
            }.get(status_clean, "#10B981")

            # Header row: ADR-NNNN: title | status badge
            header_left = Paragraph(f"<b>ADR-{num}:</b> {title}", s_card_title)
            badge_para = Paragraph(
                f"<font color='white'><b>{status_clean.upper()}</b></font>",
                ParagraphStyle("Badge", fontSize=8, textColor=colors.white,
                               alignment=TA_CENTER, fontName="Helvetica-Bold"),
            )
            badge_tbl = Table([[badge_para]], colWidths=[2.6 * cm], rowHeights=[0.55 * cm])
            badge_tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(badge_color)),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROUNDEDCORNERS", [4, 4, 4, 4]),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))

            header = Table(
                [[header_left, badge_tbl]],
                colWidths=[doc.width - 0.4 * cm - 2.6 * cm - 0.4 * cm, 2.6 * cm],
            )
            header.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))

            body_flowables = [header]
            for label, value in fields:
                value = (value or "").strip()
                if not value:
                    continue
                body_flowables.append(Paragraph(label, s_card_label))
                body_flowables.append(Paragraph(value, s_card_body))

            # Wrap everything in an outer table that gives us the colored left
            # border + soft background.
            inner = Table([[body_flowables]], colWidths=[doc.width - 0.7 * cm])
            inner.setStyle(TableStyle([
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ]))
            outer = Table([["", inner]], colWidths=[0.18 * cm, doc.width - 0.7 * cm + 0.0001])
            outer.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(badge_color)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            return outer

        def colored_bullet_list(items: list[str], symbol: str, color_hex: str):
            """List with a coloured glyph instead of a generic bullet."""
            list_items = []
            for it in items:
                glyph = (
                    f"<font color='{color_hex}'><b>{symbol}</b></font>"
                )
                # Two-column row: glyph | text. Lets the glyph keep its color
                # while the text uses the body style.
                row = Table(
                    [[Paragraph(glyph, ParagraphStyle(
                        "Glyph", fontSize=11, alignment=TA_LEFT, leading=14,
                    )), Paragraph(it, s_card_body)]],
                    colWidths=[0.55 * cm, doc.width - 0.55 * cm],
                )
                row.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]))
                list_items.append(row)
            return list_items

        # ── Cover ─────────────────────────────────────────────────────────────
        story = []
        story.append(Spacer(1, 5 * cm))
        story.append(Paragraph(project_name, s_cover_title))
        subtitle_text = ("Documentação Técnica de Arquitetura"
                         if self.language == "pt"
                         else "Technical Architecture Documentation")
        story.append(Paragraph(subtitle_text, s_cover_subtitle))
        story.append(HRFlowable(width="40%", thickness=1.2, color=rgb(MID_BLUE),
                                hAlign="CENTER"))
        story.append(Spacer(1, 1.4 * cm))

        # Cover metadata block (date, layers, components count)
        n_layers = len(result.layers or [])
        n_components = sum(len(l.get("components", [])) for l in (result.layers or []))
        date_str = datetime.now().strftime("%d/%m/%Y" if self.language == "pt" else "%Y-%m-%d")
        meta_lines = (
            [
                f"Gerado em {date_str}",
                f"{n_layers} camadas, {n_components} componentes",
            ]
            if self.language == "pt" else
            [
                f"Generated on {date_str}",
                f"{n_layers} layers, {n_components} components",
            ]
        )
        for line in meta_lines:
            story.append(Paragraph(line, s_cover_meta))

        # Switch to body template for everything that follows.
        from reportlab.platypus.doctemplate import NextPageTemplate
        story.append(NextPageTemplate("body"))
        story.append(PageBreak())

        # ── 1. Overview ───────────────────────────────────────────────────────
        h1_label = "1. Visão Geral do Projeto" if self.language == "pt" else "1. Project Overview"
        story.append(Paragraph(h1_label, s_h1))
        if result.description:
            story.append(Paragraph(result.description, s_body))

        if result.tech_stack:
            tech_label = "Stack Tecnológico:" if self.language == "pt" else "Technology Stack:"
            story.append(Paragraph(tech_label, s_h2))
            items = [ListItem(Paragraph(t, s_bullet)) for t in result.tech_stack]
            story.append(ListFlowable(items, bulletType="bullet"))
        story.append(Spacer(1, 0.4 * cm))

        # ── 2. Layers ─────────────────────────────────────────────────────────
        arch_label = "2. Arquitetura em Camadas" if self.language == "pt" else "2. Layered Architecture"
        story.append(Paragraph(arch_label, s_h1))

        for layer in (result.layers or []):
            layer_block = []
            layer_block.append(Paragraph(layer["name"], s_h2))
            if layer.get("description"):
                layer_block.append(Paragraph(layer["description"], s_body))
            layer_block.append(info_block(_layer_rationale(layer, result.layers, self.language)))
            components = layer.get("components") or []
            if components:
                comp_label = "Componentes:" if self.language == "pt" else "Components:"
                layer_block.append(Paragraph(comp_label, s_h2))
                litems = []
                for comp in components:
                    tech_note = f" <font color='#64748B'>({comp['tech']})</font>" if comp.get("tech") else ""
                    text = f"<b>{comp['name']}</b>{tech_note} - {comp.get('description', '')}"
                    litems.append(ListItem(Paragraph(text, s_bullet)))
                layer_block.append(ListFlowable(litems, bulletType="bullet"))
            # KeepTogether so a layer header doesn't dangle at the bottom of a
            # page with its components on the next.
            story.append(KeepTogether(layer_block))
            story.append(Spacer(1, 0.3 * cm))

        # ── 3. Diagram ────────────────────────────────────────────────────────
        has_static = diagram_path and Path(diagram_path).exists()
        has_interactive = interactive_diagram_path and Path(interactive_diagram_path).exists()
        if has_static or has_interactive:
            story.append(PageBreak())
            diag_label = "3. Diagrama da Arquitetura" if self.language == "pt" else "3. Architecture Diagram"
            story.append(Paragraph(diag_label, s_h1))
            story.append(Spacer(1, 0.3 * cm))

            max_w = page_w - 5 * cm

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
            qs_label = (f"{next_n}. Score de Qualidade Arquitetural"
                        if self.language == "pt"
                        else f"{next_n}. Architecture Quality Score")
            story.append(Paragraph(qs_label, s_h1))

            total = int(score.get("total", 0))
            band_pt = ("Excelente" if total >= 80 else
                       "Bom, com pontos a evoluir" if total >= 60 else
                       "Funcional mas com lacunas relevantes" if total >= 40 else
                       "Atenção: problemas estruturais")
            band_en = ("Excellent" if total >= 80 else
                       "Good, with room to improve" if total >= 60 else
                       "Functional but with relevant gaps" if total >= 40 else
                       "Warning: structural problems")
            band = band_pt if self.language == "pt" else band_en
            score_color = ("#10B981" if total >= 80 else
                           "#EAB308" if total >= 60 else
                           "#F97316" if total >= 40 else "#EF4444")

            # Hero score card: big number + band label + total bar (out of 100)
            big = Paragraph(
                f"<font color='{score_color}'><b>{total}</b></font>"
                f"<font size='18' color='#94A3B8'>/100</font>",
                ParagraphStyle("ScoreBig", fontSize=36, leading=42,
                               fontName="Helvetica-Bold", alignment=TA_LEFT),
            )
            band_para = Paragraph(
                band,
                ParagraphStyle("ScoreBand", fontSize=12, textColor=rgb(MID_BLUE),
                               fontName="Helvetica-Oblique", alignment=TA_LEFT,
                               leading=15),
            )
            total_bar = hbar(total, 100, score_color, total_width_cm=10.0, height_cm=0.36)

            score_hero = Table(
                [[big, [band_para, Spacer(1, 0.2 * cm), total_bar]]],
                colWidths=[5.5 * cm, doc.width - 5.5 * cm],
            )
            score_hero.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(score_hero)
            story.append(Spacer(1, 0.25 * cm))

            if score.get("rationale"):
                story.append(Paragraph(score["rationale"], s_body))
            story.append(Spacer(1, 0.25 * cm))

            breakdown = score.get("breakdown") or {}
            dim_labels_pt = {"arquitetura": "Arquitetura", "codigo": "Código",
                             "documentacao": "Documentação", "testabilidade": "Testabilidade",
                             "devops": "DevOps"}
            dim_labels_en = {"arquitetura": "Architecture", "codigo": "Code",
                             "documentacao": "Documentation", "testabilidade": "Testability",
                             "devops": "DevOps"}
            dim_labels = dim_labels_pt if self.language == "pt" else dim_labels_en
            for k, label in dim_labels.items():
                v = int(breakdown.get(k, 0))
                # Per-dimension bar shares the score's band color so the chart
                # tells the same visual story as the headline.
                story.append(metric_row(label, v, 20, score_color))
            story.append(Spacer(1, 0.4 * cm))
            next_n += 1

        # ── Architecture Pattern (classification) ────────────────────────────
        pattern = getattr(result, "architecture_pattern", None) or {}
        matches = pattern.get("matches") or []
        if matches:
            ap_label = (f"{next_n}. Padrão Arquitetural"
                        if self.language == "pt"
                        else f"{next_n}. Architectural Pattern")
            story.append(Paragraph(ap_label, s_h1))

            primary = pattern.get("primary") or matches[0]["name"]
            primary_pct = int(matches[0].get("adherence", 0))
            pattern_color = ("#10B981" if primary_pct >= 75 else
                             "#3B82F6" if primary_pct >= 50 else "#94A3B8")

            story.append(Paragraph(
                f"<font color='{pattern_color}'><b>{primary}</b></font>",
                ParagraphStyle("PatternPrimary", fontSize=18, alignment=TA_LEFT,
                               leading=22, spaceAfter=2),
            ))
            story.append(Paragraph(
                f"<font color='#94A3B8'>{primary_pct}% de aderência ao padrão</font>"
                if self.language == "pt"
                else f"<font color='#94A3B8'>{primary_pct}% adherence to the pattern</font>",
                ParagraphStyle("PatternPct", fontSize=10.5, alignment=TA_LEFT,
                               leading=14, spaceAfter=8),
            ))

            if pattern.get("summary"):
                story.append(Paragraph(pattern["summary"], s_body))
                story.append(Spacer(1, 0.2 * cm))

            # Comparison bars for all matches, sorted descending by adherence.
            for m in sorted(matches, key=lambda x: x.get("adherence", 0), reverse=True):
                pct = int(m.get("adherence", 0))
                color = ("#10B981" if pct >= 75 else
                         "#3B82F6" if pct >= 50 else
                         "#F97316" if pct >= 25 else "#94A3B8")
                story.append(metric_row(m["name"], pct, 100, color))

            story.append(Spacer(1, 0.3 * cm))

            # Per-match rationales + evidence (free-form text below the bars)
            ev_lbl = "Evidências:" if self.language == "pt" else "Evidence:"
            for m in matches:
                story.append(Paragraph(f"<b>{m['name']}</b>", s_h2))
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
            uc_label = (f"{next_n}. Diagramas de Sequência"
                        if self.language == "pt"
                        else f"{next_n}. Sequence Diagrams")
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
            max_w = page_w - 5 * cm
            for uc in use_cases:
                uc_block = []
                uc_block.append(Paragraph(uc.get("name", ""), s_h2))
                if uc.get("description"):
                    uc_block.append(Paragraph(uc["description"], s_body))
                diagram = (uc.get("sequence_diagram") or "").strip()
                if diagram:
                    png_path = render_mermaid_png(diagram)
                    if png_path:
                        try:
                            from PIL import Image as PILImage
                            with PILImage.open(str(png_path)) as img:
                                ratio = img.height / img.width if img.width else 0.6
                            img_w = min(max_w, 16 * cm)
                            uc_block.append(Image(str(png_path), width=img_w, height=img_w * ratio))
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
                            uc_block.append(Paragraph(line_html, s_code))
                uc_block.append(Spacer(1, 0.3 * cm))
                story.append(KeepTogether(uc_block))
            next_n += 1

        # ── Architecture Decision Records (ADRs) ─────────────────────────────
        adrs = getattr(result, "adrs", None) or []
        if adrs:
            adr_label = (f"{next_n}. Decisões Arquiteturais (ADRs)"
                         if self.language == "pt"
                         else f"{next_n}. Architecture Decision Records (ADRs)")
            story.append(Paragraph(adr_label, s_h1))
            intro = (
                "Decisões arquiteturais identificadas no projeto. Cada ADR descreve o "
                "contexto, a decisão tomada e suas consequências - formato MADR."
                if self.language == "pt" else
                "Architectural decisions identified in the project. Each ADR describes the "
                "context, the decision and its consequences - MADR format."
            )
            story.append(Paragraph(intro, s_body))
            story.append(Spacer(1, 0.2 * cm))

            ctx_lbl = "Contexto" if self.language == "pt" else "Context"
            dec_lbl = "Decisão" if self.language == "pt" else "Decision"
            cons_lbl = "Consequências" if self.language == "pt" else "Consequences"
            alt_lbl = "Alternativas" if self.language == "pt" else "Alternatives"

            for i, adr in enumerate(adrs, start=1):
                num = f"{i:04d}"
                title = (adr.get("title") or "Untitled").strip()
                status = (adr.get("status") or "accepted")
                fields = [
                    (ctx_lbl, adr.get("context", "")),
                    (dec_lbl, adr.get("decision", "")),
                    (cons_lbl, adr.get("consequences", "")),
                    (alt_lbl, adr.get("alternatives", "")),
                ]
                story.append(KeepTogether(adr_card(num, title, status, fields)))
                story.append(Spacer(1, 0.35 * cm))
            next_n += 1

        # ── Good Practices ───────────────────────────────────────────────────
        if result.good_practices:
            gp_label = (f"{next_n}. Boas Práticas Identificadas"
                        if self.language == "pt"
                        else f"{next_n}. Good Practices")
            story.append(Paragraph(gp_label, s_h1))
            for row in colored_bullet_list(result.good_practices, "✓", "#10B981"):
                story.append(row)
            story.append(Spacer(1, 0.3 * cm))
            next_n += 1

        # ── Improvement Points ───────────────────────────────────────────────
        if result.improvement_points:
            ip_label = (f"{next_n}. Pontos de Melhoria"
                        if self.language == "pt"
                        else f"{next_n}. Improvement Points")
            story.append(Paragraph(ip_label, s_h1))
            for row in colored_bullet_list(result.improvement_points, "!", "#F97316"):
                story.append(row)

        doc.build(story)
        return str(out_path)

    def _safe_name(self, name: str) -> str:
        return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
