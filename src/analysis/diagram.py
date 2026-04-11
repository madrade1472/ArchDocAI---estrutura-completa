"""
Layer 2 - Analysis: Generate architecture diagrams from AnalysisResult.
Renders a layered diagram similar to the reference image using matplotlib.
Also exports Mermaid markup for embedding in docs.
"""

import textwrap
from pathlib import Path
from dataclasses import dataclass
from .analyzer import AnalysisResult

# Default palette when layers don't specify colors
DEFAULT_COLORS = [
    "#2d6a4f",  # dark green  - sources
    "#1d3557",  # dark blue   - raw layer
    "#6a0572",  # purple      - transform
    "#7b2d00",  # dark red    - engine / processing
    "#b5451b",  # orange-red  - consumption / output
]

TEXT_COLOR = "#ffffff"
COMPONENT_ALPHA = 0.85


@dataclass
class DiagramGenerator:
    output_dir: str = "./output"

    def generate_png(self, result: AnalysisResult, filename: str = "architecture.png") -> str:
        """Render a layered architecture PNG. Returns the output file path."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        from matplotlib.patches import FancyBboxPatch

        layers = result.layers
        n_layers = len(layers)
        if n_layers == 0:
            raise ValueError("No layers found in analysis result.")

        fig_height = max(n_layers * 3.5, 10)
        fig, ax = plt.subplots(figsize=(14, fig_height))
        ax.set_xlim(0, 14)
        ax.set_ylim(0, fig_height)
        ax.axis("off")
        fig.patch.set_facecolor("#0d0d0d")

        layer_height = 3.0
        padding = 0.3
        y_cursor = fig_height - padding

        for i, layer in enumerate(layers):
            color = layer.get("color") or DEFAULT_COLORS[i % len(DEFAULT_COLORS)]
            y_top = y_cursor
            y_bottom = y_top - layer_height
            y_cursor = y_bottom - padding

            # Layer background box
            rect = FancyBboxPatch(
                (0.2, y_bottom), 13.6, layer_height - 0.1,
                boxstyle="round,pad=0.05",
                facecolor=color, edgecolor="none", alpha=0.9,
                zorder=1,
            )
            ax.add_patch(rect)

            # Layer title
            ax.text(
                7, y_top - 0.35, layer["name"],
                ha="center", va="top", fontsize=12, fontweight="bold",
                color=TEXT_COLOR, zorder=2,
            )

            # Components
            components = layer.get("components", [])
            if components:
                n = len(components)
                slot_w = 13.0 / max(n, 1)
                for j, comp in enumerate(components):
                    cx = 0.7 + j * slot_w + slot_w / 2
                    cy = (y_top + y_bottom) / 2 - 0.15
                    comp_rect = FancyBboxPatch(
                        (cx - slot_w * 0.42, cy - 0.7), slot_w * 0.84, 1.3,
                        boxstyle="round,pad=0.04",
                        facecolor="#ffffff18", edgecolor="#ffffff44",
                        zorder=2,
                    )
                    ax.add_patch(comp_rect)

                    name_lines = textwrap.wrap(comp["name"], width=18)
                    ax.text(
                        cx, cy + 0.35,
                        "\n".join(name_lines[:2]),
                        ha="center", va="top", fontsize=8, fontweight="bold",
                        color=TEXT_COLOR, zorder=3,
                    )
                    tech = comp.get("tech", "")
                    if tech:
                        ax.text(
                            cx, cy - 0.38,
                            tech[:30],
                            ha="center", va="bottom", fontsize=6.5, style="italic",
                            color="#ffffffaa", zorder=3,
                        )

            # Arrow to next layer
            if i < n_layers - 1:
                arrow_y = y_bottom - 0.01
                ax.annotate(
                    "", xy=(7, arrow_y - padding + 0.05), xytext=(7, arrow_y),
                    arrowprops=dict(arrowstyle="->", color="#ffffff66", lw=1.5),
                    zorder=4,
                )

        # Title
        ax.text(
            7, fig_height - 0.05,
            result.project_name,
            ha="center", va="top", fontsize=16, fontweight="bold",
            color="#ffffff", zorder=5,
        )

        output_path = Path(self.output_dir) / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.tight_layout(pad=0)
        plt.savefig(str(output_path), dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close()
        return str(output_path)

    def generate_mermaid(self, result: AnalysisResult) -> str:
        """Return a Mermaid flowchart markup string."""
        lines = ["flowchart TD"]
        prev_id = None

        for layer in result.layers:
            lid = layer["id"]
            label = layer["name"].replace('"', "'")
            lines.append(f'    {lid}["{label}"]')

            for comp in layer.get("components", []):
                cid = lid + "_" + comp["name"].replace(" ", "_").lower()[:15]
                clabel = comp["name"].replace('"', "'")
                lines.append(f'    {cid}["{clabel}"]')
                lines.append(f"    {lid} --> {cid}")

            if prev_id:
                lines.append(f"    {prev_id} --> {lid}")
            prev_id = lid

        return "\n".join(lines)
