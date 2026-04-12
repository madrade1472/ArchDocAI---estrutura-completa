"""
Layer 2 - Analysis: Generate architecture diagrams from AnalysisResult.
Renders a layered diagram using matplotlib with dynamic layout.
Also exports Mermaid markup for embedding in docs.
"""

import math
import textwrap
from pathlib import Path
from dataclasses import dataclass
from .analyzer import AnalysisResult

# Default palette when layers don't specify colors
DEFAULT_COLORS = [
    "#1a6b4a",  # green        - ingestion / source
    "#1a3a5c",  # dark blue    - raw / storage
    "#5a2d82",  # purple       - transform / processing
    "#8b3a00",  # amber-brown  - business logic
    "#c0392b",  # red          - output / serving
    "#2c7a7b",  # teal         - orchestration
    "#6d4c41",  # brown        - infra
]

# Layout constants
_MAX_PER_ROW = 4       # max components per row before wrapping
_COMP_H = 1.6          # component box height (data units)
_COMP_ROW_GAP = 0.2    # vertical gap between component rows
_TITLE_H = 0.75        # space reserved for layer title inside layer box
_LAYER_PAD = 0.4       # vertical gap between consecutive layers
_MARGIN_TOP = 0.7      # space above title
_FIG_W = 18.0          # figure width in inches
_DPI = 160
_BG = "#111827"        # figure background (dark navy)
_TEXT = "#f0f4f8"      # primary text
_SUBTEXT = "#94a3b8"   # secondary text (tech / desc)


@dataclass
class DiagramGenerator:
    output_dir: str = "./output"

    # ------------------------------------------------------------------
    # PNG generation
    # ------------------------------------------------------------------

    def generate_png(self, result: AnalysisResult, filename: str = "architecture.png") -> str:
        """Render a readable layered architecture PNG. Returns the output file path."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyBboxPatch

        layers = result.layers
        n_layers = len(layers)
        if n_layers == 0:
            raise ValueError("No layers found in analysis result.")

        # Pre-compute each layer's height based on component count
        layer_heights = []
        for layer in layers:
            n_comps = len(layer.get("components", []))
            n_rows = max(1, math.ceil(n_comps / _MAX_PER_ROW)) if n_comps > 0 else 0
            if n_rows == 0:
                h = _TITLE_H + 0.4
            else:
                h = _TITLE_H + n_rows * (_COMP_H + _COMP_ROW_GAP) + 0.3
            layer_heights.append(h)

        total_content_h = sum(layer_heights) + (_LAYER_PAD * (n_layers - 1))
        fig_h = total_content_h + _MARGIN_TOP + 0.5  # 0.5 bottom margin

        fig, ax = plt.subplots(figsize=(_FIG_W, fig_h))
        ax.set_xlim(0, _FIG_W)
        ax.set_ylim(0, fig_h)
        ax.axis("off")
        fig.patch.set_facecolor(_BG)

        # Project title at the top
        ax.text(
            _FIG_W / 2, fig_h - 0.15,
            result.project_name,
            ha="center", va="top",
            fontsize=18, fontweight="bold",
            color=_TEXT, zorder=10,
        )

        y_cursor = fig_h - _MARGIN_TOP  # top of first layer box

        for i, layer in enumerate(layers):
            lh = layer_heights[i]
            color = layer.get("color") or DEFAULT_COLORS[i % len(DEFAULT_COLORS)]
            y_bottom = y_cursor - lh

            # --- Layer background ---
            lpad = 0.25
            rect = FancyBboxPatch(
                (lpad, y_bottom), _FIG_W - 2 * lpad, lh,
                boxstyle="round,pad=0.08",
                facecolor=color, edgecolor="none", alpha=0.92,
                zorder=1,
            )
            ax.add_patch(rect)

            # --- Layer title (left-aligned, uppercase badge style) ---
            ax.text(
                0.7, y_cursor - 0.12,
                layer["name"].upper(),
                ha="left", va="top",
                fontsize=11, fontweight="bold",
                color=_TEXT, zorder=3,
                alpha=0.95,
            )

            # Layer description (right side, dimmed)
            desc = layer.get("description", "")
            if desc:
                short_desc = desc[:90] + ("..." if len(desc) > 90 else "")
                ax.text(
                    _FIG_W - 0.5, y_cursor - 0.15,
                    short_desc,
                    ha="right", va="top",
                    fontsize=8, style="italic",
                    color=_SUBTEXT, zorder=3,
                    alpha=0.85,
                )

            # --- Components ---
            components = layer.get("components", [])
            if components:
                usable_w = _FIG_W - 2 * lpad - 0.4  # inside the layer box
                n_per_row = min(len(components), _MAX_PER_ROW)
                slot_w = usable_w / n_per_row
                comp_x0 = lpad + 0.2

                # Starting y for first row of components (below title)
                row_y_top = y_cursor - _TITLE_H

                for j, comp in enumerate(components):
                    row = j // n_per_row
                    col = j % n_per_row
                    cx = comp_x0 + col * slot_w + slot_w / 2
                    # Top of this component row
                    comp_top = row_y_top - row * (_COMP_H + _COMP_ROW_GAP)
                    comp_bottom = comp_top - _COMP_H

                    box_margin = slot_w * 0.06
                    comp_rect = FancyBboxPatch(
                        (cx - slot_w / 2 + box_margin, comp_bottom + 0.08),
                        slot_w - 2 * box_margin, _COMP_H - 0.16,
                        boxstyle="round,pad=0.06",
                        facecolor="#ffffff15",
                        edgecolor="#ffffff40",
                        linewidth=0.8,
                        zorder=2,
                    )
                    ax.add_patch(comp_rect)

                    # Component name (wrapped, bold)
                    wrap_w = max(12, int(slot_w * 5.5))
                    name_lines = textwrap.wrap(comp.get("name", ""), width=wrap_w)[:2]
                    name_y = (comp_top + comp_bottom) / 2 + 0.28
                    ax.text(
                        cx, name_y,
                        "\n".join(name_lines),
                        ha="center", va="center",
                        fontsize=9.5, fontweight="bold",
                        color=_TEXT, zorder=4,
                        linespacing=1.25,
                    )

                    # Tech label (italic, dimmed)
                    tech = comp.get("tech", "")
                    if tech:
                        ax.text(
                            cx, comp_bottom + 0.22,
                            tech[:28],
                            ha="center", va="bottom",
                            fontsize=7.5, style="italic",
                            color=_SUBTEXT, zorder=4,
                        )

            # --- Arrow to next layer ---
            if i < n_layers - 1:
                arrow_y = y_bottom
                ax.annotate(
                    "", xy=(7, arrow_y - _LAYER_PAD + 0.1),
                    xytext=(7, arrow_y),
                    arrowprops=dict(
                        arrowstyle="->, head_width=0.25, head_length=0.12",
                        color="#64748b", lw=1.8,
                    ),
                    zorder=5,
                )

            y_cursor = y_bottom - _LAYER_PAD

        output_path = Path(self.output_dir) / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(
            str(output_path), dpi=_DPI, bbox_inches="tight",
            facecolor=fig.get_facecolor(), pad_inches=0.2,
        )
        plt.close()
        return str(output_path)

    # ------------------------------------------------------------------
    # Mermaid generation
    # ------------------------------------------------------------------

    def generate_mermaid(self, result: AnalysisResult) -> str:
        """Return a Mermaid flowchart markup string with per-layer colors."""
        lines = ["flowchart TD"]
        prev_id = None
        style_lines: list[str] = []

        for i, layer in enumerate(result.layers):
            lid = layer["id"]
            label = layer["name"].replace('"', "'")
            lines.append(f'    {lid}["{label}"]')

            color = layer.get("color") or DEFAULT_COLORS[i % len(DEFAULT_COLORS)]
            style_lines.append(
                f"    style {lid} fill:{color},stroke:#ffffff22,color:#ffffff,font-weight:bold"
            )

            for comp in layer.get("components", []):
                cid = lid + "_" + comp["name"].replace(" ", "_").lower()[:15]
                clabel = comp["name"].replace('"', "'")
                lines.append(f'    {cid}["{clabel}"]')
                lines.append(f"    {lid} --> {cid}")
                style_lines.append(
                    f"    style {cid} fill:{color}99,stroke:#ffffff33,color:#ffffff"
                )

            if prev_id:
                lines.append(f"    {prev_id} --> {lid}")
            prev_id = lid

        return "\n".join(lines + style_lines)
