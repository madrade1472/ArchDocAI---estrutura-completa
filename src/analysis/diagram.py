"""
Layer 2 - Analysis: Generate architecture diagrams from AnalysisResult.

Landscape A4 format — layers flow left → right as columns.
Each component card has a drawn icon (database, queue, API, code, container…).
Also exports Mermaid markup for embedding in docs.
"""

import math
import textwrap
from pathlib import Path
from dataclasses import dataclass
from .analyzer import AnalysisResult

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------
DEFAULT_COLORS = [
    "#2563eb",  # blue
    "#16a34a",  # green
    "#9333ea",  # purple
    "#ea580c",  # orange
    "#dc2626",  # red
    "#0891b2",  # cyan
    "#854d0e",  # amber-brown
    "#475569",  # slate
]

_PASTEL = [
    "#dbeafe",  # blue-100
    "#dcfce7",  # green-100
    "#f3e8ff",  # purple-100
    "#ffedd5",  # orange-100
    "#fee2e2",  # red-100
    "#cffafe",  # cyan-100
    "#fef3c7",  # amber-100
    "#f1f5f9",  # slate-100
]

# ---------------------------------------------------------------------------
# Icon types
# ---------------------------------------------------------------------------
_DB = "db"
_QUEUE = "queue"
_API = "api"
_CODE = "code"
_CONTAINER = "container"
_CLOUD = "cloud"
_WEB = "web"
_GEAR = "gear"
_ML = "ml"
_STORAGE = "storage"
_MONITOR = "monitor"

# Tech keyword → icon type  (longest match wins)
_TECH_ICON: dict[str, str] = {
    "postgresql": _DB, "postgres": _DB, "mysql": _DB, "sqlite": _DB,
    "mongodb": _DB, "mongo": _DB, "cassandra": _DB, "dynamodb": _DB,
    "firestore": _DB, "aurora": _DB, "rds": _DB, "cloud sql": _DB,
    "redis": _DB, "memcached": _DB, "elasticache": _DB,
    "elasticsearch": _DB, "elastic": _DB, "opensearch": _DB,
    "kafka": _QUEUE, "rabbitmq": _QUEUE, "celery": _QUEUE,
    "activemq": _QUEUE, "sqs": _QUEUE, "pubsub": _QUEUE,
    "pub/sub": _QUEUE, "kinesis": _QUEUE, "eventbridge": _QUEUE,
    "service bus": _QUEUE, "event hub": _QUEUE, "nats": _QUEUE,
    "fastapi": _API, "flask": _API, "django": _API, "express": _API,
    "nginx": _API, "apache": _API, "spring": _API, "grpc": _API,
    "graphql": _API, "api gateway": _API, "load balancer": _API,
    "haproxy": _API, "traefik": _API, "rest": _API,
    "python": _CODE, "javascript": _CODE, "typescript": _CODE,
    "go": _CODE, "java": _CODE, "rust": _CODE, "scala": _CODE,
    "kotlin": _CODE, "ruby": _CODE, "c++": _CODE,
    "pandas": _CODE, "numpy": _CODE,
    "docker": _CONTAINER, "kubernetes": _CONTAINER, "k8s": _CONTAINER,
    "fargate": _CONTAINER, "ecs": _CONTAINER, "eks": _CONTAINER,
    "gke": _CONTAINER, "aks": _CONTAINER, "podman": _CONTAINER,
    "aws": _CLOUD, "gcp": _CLOUD, "azure": _CLOUD,
    "lambda": _CLOUD, "cloud run": _CLOUD, "cloudfront": _CLOUD,
    "s3": _STORAGE, "gcs": _STORAGE, "blob": _STORAGE,
    "glacier": _STORAGE, "hdfs": _STORAGE,
    "react": _WEB, "vue": _WEB, "angular": _WEB, "svelte": _WEB,
    "next": _WEB, "nuxt": _WEB, "html": _WEB,
    "grafana": _MONITOR, "prometheus": _MONITOR, "cloudwatch": _MONITOR,
    "datadog": _MONITOR, "bigquery": _MONITOR, "redshift": _MONITOR,
    "athena": _MONITOR, "snowflake": _MONITOR, "databricks": _MONITOR,
    "airflow": _GEAR, "spark": _GEAR, "flink": _GEAR, "dbt": _GEAR,
    "terraform": _GEAR, "ansible": _GEAR, "jenkins": _GEAR,
    "gitlab": _GEAR, "github": _GEAR, "prefect": _GEAR,
    "pytorch": _ML, "tensorflow": _ML, "sklearn": _ML,
    "sagemaker": _ML, "mlflow": _ML, "hugging": _ML, "xgboost": _ML,
}

_TYPE_ICON: dict[str, str] = {
    "source": _QUEUE, "store": _DB, "process": _GEAR,
    "api": _API, "ui": _WEB, "infra": _CONTAINER,
    "ml": _ML, "analytics": _MONITOR,
}

# ---------------------------------------------------------------------------
# Layout constants  (landscape A4 proportions)
# ---------------------------------------------------------------------------
_FIG_W = 18.0       # figure width in inches
_FIG_H = 11.0       # figure height in inches
_DPI = 160
_BG = "#f8fafc"

_MH = 0.30          # horizontal margin
_MV = 0.42          # vertical margin
_TITLE_H = 0.55     # project title area
_HDR_H = 0.72       # column header height
_COL_GAP = 0.46     # gap between columns (arrow lives here)
_CARD_PAD_H = 0.13  # horizontal padding inside column
_CARD_PAD_V = 0.14  # vertical padding top/bottom inside column
_CARD_GAP = 0.10    # gap between consecutive cards
_MAX_CARD_H = 1.22  # tallest a card can be
_MIN_CARD_H = 0.68  # shortest a card can be
_MAX_CARDS = 8      # truncate columns with more components than this


# ---------------------------------------------------------------------------
# Icon drawing helpers
# ---------------------------------------------------------------------------

def _split_name(name: str) -> tuple[str, str]:
    """Split 'Short — Long description' into (short, long).
    Handles em-dash (—), en-dash (–) and plain hyphen ( - ).
    Returns (full_name, '') when no separator found.
    """
    for sep in (" — ", " – ", " - "):
        if sep in name:
            head, tail = name.split(sep, 1)
            return head.strip(), tail.strip()
    return name.strip(), ""


def _dedup_components(components: list[dict]) -> list[dict]:
    """Remove duplicate components by normalised name (case-insensitive, strip)."""
    seen: set[str] = set()
    result: list[dict] = []
    for comp in components:
        key = comp.get("name", "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            result.append(comp)
    return result


def _resolve_icon_type(comp: dict) -> str:
    haystack = (comp.get("tech", "") + " " + comp.get("name", "")).lower()
    best_key = ""
    best_val = _GEAR
    for kw, val in _TECH_ICON.items():
        if kw in haystack and len(kw) > len(best_key):
            best_key = kw
            best_val = val
    if best_key:
        return best_val
    return _TYPE_ICON.get(comp.get("type", "").lower(), _GEAR)


def _draw_icon(ax, cx: float, cy: float, icon_type: str, color: str, r: float = 0.18) -> None:
    """Draw a recognisable tech icon centered at (cx, cy) with bounding radius r."""
    from matplotlib.patches import Circle, Ellipse, Polygon, FancyBboxPatch
    import matplotlib.patches as mpatches

    # translucent background disc
    ax.add_patch(Circle((cx, cy), r * 1.25,
                        facecolor=color + "1a", edgecolor=color + "55",
                        linewidth=0.6, zorder=4))

    if icon_type == _DB:
        # Cylinder: rect body + top ellipse + mid-line ellipse
        cw, ch = r * 1.12, r * 1.0
        ax.add_patch(mpatches.Rectangle(
            (cx - cw / 2, cy - ch / 2), cw, ch,
            facecolor=color + "30", edgecolor=color, linewidth=1.1, zorder=5))
        ax.add_patch(Ellipse((cx, cy + ch / 2), cw, ch * 0.40,
                             facecolor=color + "66", edgecolor=color,
                             linewidth=1.1, zorder=6))
        ax.add_patch(Ellipse((cx, cy), cw, ch * 0.35,
                             facecolor="none", edgecolor=color + "88",
                             linewidth=0.7, zorder=6))

    elif icon_type == _QUEUE:
        # Three horizontal bars
        bw, bh = r * 1.28, r * 0.20
        for offset in (r * 0.38, 0.0, -r * 0.38):
            ax.add_patch(FancyBboxPatch(
                (cx - bw / 2, cy + offset - bh / 2), bw, bh,
                boxstyle="round,pad=0.01",
                facecolor=color, edgecolor="none", zorder=5))
        # Chevron on the right of top bar
        ax.annotate("",
                    xy=(cx + bw / 2 + r * 0.22, cy + r * 0.38),
                    xytext=(cx + bw / 2, cy + r * 0.38),
                    arrowprops=dict(arrowstyle="->", color=color, lw=1.3),
                    zorder=6)

    elif icon_type == _API:
        # Hexagon with "API" label
        pts = [(cx + r * 0.92 * math.cos(math.radians(i * 60 + 30)),
                cy + r * 0.92 * math.sin(math.radians(i * 60 + 30)))
               for i in range(6)]
        ax.add_patch(Polygon(pts, closed=True,
                             facecolor=color + "30", edgecolor=color,
                             linewidth=1.3, zorder=5))
        ax.text(cx, cy, "API", ha="center", va="center",
                fontsize=max(4.5, r * 28), fontweight="bold",
                color=color, zorder=6)

    elif icon_type == _CODE:
        # </> monospace text
        ax.text(cx, cy, "</>", ha="center", va="center",
                fontsize=max(6.0, r * 36), fontweight="bold",
                color=color, family="monospace", zorder=5)

    elif icon_type == _CONTAINER:
        # Square box with three horizontal lines inside
        bs = r * 1.02
        ax.add_patch(FancyBboxPatch(
            (cx - bs / 2, cy - bs / 2), bs, bs,
            boxstyle="square,pad=0.01",
            facecolor=color + "22", edgecolor=color, linewidth=1.2, zorder=5))
        for frac in (0.28, -0.05, -0.38):
            ax.plot([cx - bs * 0.38, cx + bs * 0.38],
                    [cy + frac * bs, cy + frac * bs],
                    color=color, linewidth=0.9, zorder=6)

    elif icon_type == _CLOUD:
        # Three overlapping circles + solid base
        for ox, oy, rr in ((-r * 0.32, -r * 0.08, r * 0.48),
                            (r * 0.32, -r * 0.08, r * 0.48),
                            (0.0, r * 0.16, r * 0.52)):
            ax.add_patch(Circle((cx + ox, cy + oy), rr,
                                facecolor=color + "44", edgecolor=color,
                                linewidth=0.9, zorder=5))
        ax.add_patch(mpatches.Rectangle(
            (cx - r * 0.78, cy - r * 0.42), r * 1.56, r * 0.34,
            facecolor=color + "44", edgecolor="none", zorder=5))

    elif icon_type == _WEB:
        # Globe: circle + equator ellipse + meridian line
        ax.add_patch(Circle((cx, cy), r * 0.92,
                            facecolor=color + "22", edgecolor=color,
                            linewidth=1.3, zorder=5))
        ax.add_patch(Ellipse((cx, cy), r * 1.84, r * 0.56,
                             facecolor="none", edgecolor=color,
                             linewidth=0.9, zorder=6))
        ax.plot([cx, cx], [cy - r * 0.92, cy + r * 0.92],
                color=color, linewidth=0.9, zorder=6)

    elif icon_type == _GEAR:
        # Star-polygon teeth + inner circle
        pts = []
        for i in range(16):
            a = math.radians(i * 22.5)
            rr = r * 0.88 if i % 2 == 0 else r * 0.66
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        ax.add_patch(Polygon(pts, closed=True,
                             facecolor=color + "30", edgecolor=color,
                             linewidth=1.1, zorder=5))
        ax.add_patch(Circle((cx, cy), r * 0.40,
                            facecolor=color + "66", edgecolor=color,
                            linewidth=1.0, zorder=6))

    elif icon_type == _ML:
        # Mini neural net: 2-3-1 nodes + edges
        nr = r * 0.17
        node_layers = [
            [(cx - r * 0.68, cy + r * 0.32), (cx - r * 0.68, cy - r * 0.32)],
            [(cx, cy + r * 0.48), (cx, cy), (cx, cy - r * 0.48)],
            [(cx + r * 0.68, cy)],
        ]
        for prev_l, next_l in zip(node_layers, node_layers[1:]):
            for pn in prev_l:
                for nn in next_l:
                    ax.plot([pn[0], nn[0]], [pn[1], nn[1]],
                            color=color, linewidth=0.5, alpha=0.55, zorder=4)
        for layer_nodes in node_layers:
            for nx, ny in layer_nodes:
                ax.add_patch(Circle((nx, ny), nr,
                                   facecolor=color, edgecolor="white",
                                   linewidth=0.6, zorder=6))

    elif icon_type == _STORAGE:
        # Stack of three ellipses (disk platters)
        dw, dh = r * 1.30, r * 0.30
        for offset, alpha in ((r * 0.38, "30"), (r * 0.0, "55"), (-r * 0.38, "77")):
            ax.add_patch(Ellipse((cx, cy + offset), dw, dh,
                                 facecolor=color + alpha, edgecolor=color,
                                 linewidth=0.9, zorder=5))

    elif icon_type == _MONITOR:
        # Bar chart with three bars
        bw = r * 0.30
        gap = r * 0.09
        bars = [(r * 0.56, "44"), (r * 0.90, "88"), (r * 0.68, "66")]
        total_w = 3 * bw + 2 * gap
        x0 = cx - total_w / 2
        base_y = cy - r * 0.52
        for i, (h, al) in enumerate(bars):
            ax.add_patch(mpatches.Rectangle(
                (x0 + i * (bw + gap), base_y), bw, h,
                facecolor=color + al, edgecolor=color, linewidth=0.8, zorder=5))

    else:
        # Generic: filled circle
        ax.add_patch(Circle((cx, cy), r * 0.78,
                            facecolor=color + "44", edgecolor=color,
                            linewidth=1.2, zorder=5))


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

@dataclass
class DiagramGenerator:
    output_dir: str = "./output"

    def generate_png(self, result: AnalysisResult, filename: str = "architecture.png") -> str:
        """Render a landscape architecture diagram PNG with drawn icons."""
        if not result.layers:
            raise ValueError("No layers found in analysis result.")
        return self._render(result, filename)

    def _render(self, result: AnalysisResult, filename: str) -> str:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyBboxPatch

        layers = result.layers
        n = len(layers)

        # Column geometry
        col_w = (_FIG_W - 2 * _MH - (n - 1) * _COL_GAP) / n

        # Adaptive card height based on the busiest column (after dedup)
        max_comps = max((len(_dedup_components(lyr.get("components", []))) for lyr in layers), default=1)
        max_visible = min(max_comps, _MAX_CARDS)
        col_content_h = _FIG_H - 2 * _MV - _TITLE_H - _HDR_H - 2 * _CARD_PAD_V
        card_h = min(_MAX_CARD_H,
                     max(_MIN_CARD_H,
                         (col_content_h - _CARD_GAP * (max_visible - 1)) / max(max_visible, 1)))

        # Icon radius — scale to card size, never too big
        icon_r = min(0.20, card_h * 0.22, col_w * 0.20)

        fig, ax = plt.subplots(figsize=(_FIG_W, _FIG_H))
        fig.patch.set_facecolor(_BG)
        ax.set_facecolor(_BG)
        ax.set_xlim(0, _FIG_W)
        ax.set_ylim(0, _FIG_H)
        ax.axis("off")

        # Project title
        ax.text(_FIG_W / 2, _FIG_H - _MV * 0.55,
                result.project_name,
                ha="center", va="top", fontsize=17, fontweight="bold",
                color="#0f172a", zorder=10)
        ax.text(_FIG_W / 2, _FIG_H - _MV * 0.55 - 0.32,
                "Architecture Overview",
                ha="center", va="top", fontsize=8.5, color="#64748b",
                style="italic", zorder=10)

        col_top = _FIG_H - _MV - _TITLE_H
        col_bottom = _MV
        col_h = col_top - col_bottom

        for i, layer in enumerate(layers):
            accent = layer.get("color") or DEFAULT_COLORS[i % len(DEFAULT_COLORS)]
            pastel = _PASTEL[i % len(_PASTEL)]
            components = layer.get("components", [])

            x0 = _MH + i * (col_w + _COL_GAP)

            # ── Column background ─────────────────────────────────────
            ax.add_patch(FancyBboxPatch(
                (x0, col_bottom), col_w, col_h,
                boxstyle="round,pad=0.05",
                facecolor=pastel, edgecolor=accent + "55",
                linewidth=0.9, zorder=1))

            # ── Column header (colored) ───────────────────────────────
            ax.add_patch(FancyBboxPatch(
                (x0, col_top - _HDR_H), col_w, _HDR_H,
                boxstyle="round,pad=0.05",
                facecolor=accent, edgecolor="none", zorder=2))

            wrap_w = max(8, int(col_w * 7.5))
            name_lines = textwrap.wrap(layer["name"], width=wrap_w)[:2]
            ax.text(x0 + col_w / 2, col_top - _HDR_H / 2,
                    "\n".join(name_lines),
                    ha="center", va="center",
                    fontsize=min(9.0, 7.0 + col_w * 0.55),
                    fontweight="bold", color="white",
                    linespacing=1.2, zorder=3)

            # ── Arrow from previous column ────────────────────────────
            if i > 0:
                arr_y = col_top - _HDR_H / 2
                ax.annotate("",
                            xy=(x0 - 0.07, arr_y),
                            xytext=(x0 - _COL_GAP + 0.07, arr_y),
                            arrowprops=dict(
                                arrowstyle="->, head_width=0.18, head_length=0.10",
                                color="#94a3b8", lw=1.5),
                            zorder=5)

            # ── Component cards ───────────────────────────────────────
            deduped = _dedup_components(components)
            visible = deduped[:_MAX_CARDS]
            hidden = len(deduped) - len(visible)

            card_w = col_w - 2 * _CARD_PAD_H
            card_x = x0 + _CARD_PAD_H
            card_top_start = col_top - _HDR_H - _CARD_PAD_V

            icon_area_frac = 0.46
            icon_area_h = card_h * icon_area_frac

            for j, comp in enumerate(visible):
                cy_top = card_top_start - j * (card_h + _CARD_GAP)
                cy_bot = cy_top - card_h

                # Card
                ax.add_patch(FancyBboxPatch(
                    (card_x, cy_bot), card_w, card_h,
                    boxstyle="round,pad=0.03",
                    facecolor="white", edgecolor=accent + "77",
                    linewidth=0.9, zorder=3))

                # Icon (upper portion of card)
                icon_cx = card_x + card_w / 2
                icon_cy = cy_top - icon_area_h / 2
                _draw_icon(ax, icon_cx, icon_cy,
                           _resolve_icon_type(comp), accent, r=icon_r)

                # Component name (below icon) — split on dash separators
                raw_name = comp.get("name", "")
                short_name, subtitle = _split_name(raw_name)

                name_fs = min(7.8, 5.8 + col_w * 0.45)
                sub_fs = max(5.5, name_fs - 1.5)
                nwrap = max(8, int(card_w * 7.5))
                name_lines_comp = textwrap.wrap(short_name, width=nwrap)[:2]

                name_y = cy_top - icon_area_h - 0.02
                ax.text(card_x + card_w / 2, name_y,
                        "\n".join(name_lines_comp),
                        ha="center", va="top",
                        fontsize=name_fs, fontweight="bold",
                        color="#1e293b", linespacing=1.2, zorder=4)

                # Subtitle from dash-split (shown below name, smaller)
                if subtitle:
                    sub_lines = textwrap.wrap(subtitle, width=nwrap)[:2]
                    # estimate how far name text goes
                    n_name_lines = len(name_lines_comp)
                    sub_y = name_y - n_name_lines * (name_fs / 72 * 1.35)
                    ax.text(card_x + card_w / 2, sub_y,
                            "\n".join(sub_lines),
                            ha="center", va="top",
                            fontsize=sub_fs, color="#475569",
                            linespacing=1.1, zorder=4)

                # Tech label (bottom of card)
                tech = comp.get("tech", "")
                if tech:
                    ax.text(card_x + card_w / 2, cy_bot + 0.09,
                            tech[:24],
                            ha="center", va="bottom",
                            fontsize=min(6.8, 5.2 + col_w * 0.35),
                            color=accent, style="italic", zorder=4)

            # "+N more" if truncated
            if hidden:
                more_y = (card_top_start
                          - len(visible) * (card_h + _CARD_GAP)
                          - 0.06)
                ax.text(x0 + col_w / 2, more_y,
                        f"+{hidden} more…",
                        ha="center", va="top",
                        fontsize=7, color="#94a3b8", zorder=4)

        # Save
        output_path = Path(self.output_dir) / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(str(output_path), dpi=_DPI, bbox_inches="tight",
                    facecolor=fig.get_facecolor(), pad_inches=0.22)
        plt.close()
        return str(output_path)

    # ------------------------------------------------------------------
    # Mermaid
    # ------------------------------------------------------------------

    def generate_interactive_json(self, result: AnalysisResult) -> dict:
        """Return Cytoscape.js-compatible nodes/edges for the interactive diagram.

        Edges generated (in priority order):
        1. Component → Component  (from comp.connections_to — LLM-derived, most accurate)
        2. Layer → Layer          (from layer.connections_to, falling back to sequential)
        3. Layer → Component      (membership, dashed)
        4. Type-based fallback    (when no comp connections exist — inferred from comp.type)
        """
        import re as _re

        def _safe_id(text: str, prefix: str, index: int) -> str:
            slug = _re.sub(r"[^a-z0-9]", "_", text.lower())[:14].strip("_")
            return f"{prefix}_{index}_{slug}"

        nodes: list[dict] = []
        edges: list[dict] = []
        edge_ids: set[str] = set()  # dedup guard

        def _add_edge(src: str, tgt: str, etype: str, color: str) -> None:
            eid = f"e_{src}__{tgt}"
            if eid in edge_ids or src == tgt:
                return
            edge_ids.add(eid)
            edges.append({
                "data": {"id": eid, "source": src, "target": tgt, "type": etype, "color": color},
                "classes": f"{etype}-edge",
            })

        # ── Pass 1: build node list + name→id lookup ───────────────────
        # name_to_id: lowercased comp name → node id  (for connections_to resolution)
        name_to_id: dict[str, str] = {}
        layer_color: dict[str, str] = {}

        comp_records: list[tuple[str, str, dict, str]] = []  # (lid, cid, comp, color)

        for i, layer in enumerate(result.layers):
            color = layer.get("color") or DEFAULT_COLORS[i % len(DEFAULT_COLORS)]
            lid = layer["id"]
            layer_color[lid] = color

            nodes.append({
                "data": {
                    "id": lid,
                    "label": layer["name"],
                    "type": "layer",
                    "color": color,
                    "description": layer.get("description", ""),
                },
                "classes": "layer-node",
            })

            for j, comp in enumerate(layer.get("components", [])):
                cid = _safe_id(comp.get("name", f"comp{j}"), lid, j)
                name_to_id[comp.get("name", "").lower().strip()] = cid
                comp_records.append((lid, cid, comp, color))

                nodes.append({
                    "data": {
                        "id": cid,
                        "label": comp.get("name", ""),
                        "tech": comp.get("tech", ""),
                        "comp_type": comp.get("type", "process"),
                        "type": "component",
                        "color": color,
                        "parent_layer": lid,
                        "description": comp.get("description", ""),
                    },
                    "classes": "comp-node",
                })

        # ── Pass 2: membership edges (layer → its components) ──────────
        for lid, cid, comp, color in comp_records:
            _add_edge(lid, cid, "member", color)

        # ── Pass 3: layer → layer flow edges ──────────────────────────
        # Prefer explicit connections_to; fall back to sequential order
        layer_ids = [l["id"] for l in result.layers]
        connected_layers: set[tuple[str, str]] = set()

        for i, layer in enumerate(result.layers):
            lid = layer["id"]
            targets = layer.get("connections_to", [])
            if targets:
                for tid in targets:
                    if tid in layer_color:
                        _add_edge(lid, tid, "flow", layer_color[lid])
                        connected_layers.add((lid, tid))
            else:
                # Sequential fallback
                if i > 0:
                    prev = layer_ids[i - 1]
                    _add_edge(prev, lid, "flow", layer_color[lid])
                    connected_layers.add((prev, lid))

        # ── Pass 4: component → component edges ───────────────────────
        has_comp_connections = False
        for lid, cid, comp, color in comp_records:
            targets = comp.get("connections_to", [])
            for target_name in targets:
                target_id = name_to_id.get(target_name.lower().strip())
                if target_id and target_id != cid:
                    _add_edge(cid, target_id, "comp-flow", color)
                    has_comp_connections = True

        # ── Pass 5: type-based fallback when LLM gave no comp connections
        if not has_comp_connections:
            # Group comp records by layer
            by_layer: dict[str, list[tuple[str, dict, str]]] = {}
            for lid, cid, comp, color in comp_records:
                by_layer.setdefault(lid, []).append((cid, comp, color))

            # Output types (produce data) → Input types (consume data)
            _output_types = {"source", "api", "process"}
            _input_types  = {"process", "store", "api"}

            for src_lid, tgt_lid in connected_layers:
                src_comps = by_layer.get(src_lid, [])
                tgt_comps = by_layer.get(tgt_lid, [])
                if not src_comps or not tgt_comps:
                    continue

                # Pick best source: prefer api/process/source type
                src_candidates = [(cid, c, col) for cid, c, col in src_comps
                                  if c.get("type", "process") in _output_types]
                if not src_candidates:
                    src_candidates = src_comps[:1]

                # Pick best target: prefer process/store/api type
                tgt_candidates = [(cid, c, col) for cid, c, col in tgt_comps
                                  if c.get("type", "process") in _input_types]
                if not tgt_candidates:
                    tgt_candidates = tgt_comps[:1]

                # Connect up to 2 source components to up to 2 target components
                for s_cid, _, s_col in src_candidates[:2]:
                    for t_cid, _, _ in tgt_candidates[:2]:
                        _add_edge(s_cid, t_cid, "comp-flow", s_col)

        return {"nodes": nodes, "edges": edges, "project_name": result.project_name}

    def generate_interactive_png(self, result: AnalysisResult, filename: str = "architecture_interactive.png") -> str:
        """Render the interactive node-graph as a static PNG (for embedding in docx/pdf).

        Uses the same node/edge data as `generate_interactive_json` and lays it out
        as columns (one per layer) with components stacked vertically inside each column.
        """
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import networkx as nx

        graph = self.generate_interactive_json(result)
        nodes = graph["nodes"]
        edges = graph["edges"]

        G = nx.DiGraph()
        layer_ids: list[str] = []
        comp_ids: list[str] = []
        node_color: dict[str, str] = {}
        node_label: dict[str, str] = {}
        comp_parent: dict[str, str] = {}

        for n in nodes:
            d = n["data"]
            nid = d["id"]
            G.add_node(nid)
            node_color[nid] = d.get("color", "#475569")
            node_label[nid] = d.get("label", "")
            if d.get("type") == "layer":
                layer_ids.append(nid)
            else:
                comp_ids.append(nid)
                comp_parent[nid] = d.get("parent_layer", "")

        for e in edges:
            d = e["data"]
            G.add_edge(d["source"], d["target"], etype=d.get("type"))

        # Layout: layers as evenly-spaced columns; components stacked under their layer
        pos: dict[str, tuple[float, float]] = {}
        n_cols = max(len(layer_ids), 1)
        for i, lid in enumerate(layer_ids):
            x = (i + 0.5) / n_cols
            pos[lid] = (x, 0.93)
            children = [c for c in comp_ids if comp_parent.get(c) == lid]
            if children:
                top, bottom = 0.80, 0.08
                step = (top - bottom) / max(len(children), 1)
                for j, cid in enumerate(children):
                    pos[cid] = (x, top - (j + 0.5) * step)

        fig, ax = plt.subplots(figsize=(16, 10))
        BG = "#0f172a"
        fig.patch.set_facecolor(BG)
        ax.set_facecolor(BG)
        ax.set_xlim(-0.05, 1.05)
        ax.set_ylim(-0.05, 1.08)
        ax.axis("off")

        member_e = [(u, v) for u, v, d in G.edges(data=True) if d.get("etype") == "member"]
        flow_e = [(u, v) for u, v, d in G.edges(data=True) if d.get("etype") == "flow"]
        comp_e = [(u, v) for u, v, d in G.edges(data=True) if d.get("etype") == "comp-flow"]

        if member_e:
            nx.draw_networkx_edges(G, pos, edgelist=member_e, ax=ax,
                                    edge_color="#475569", style="dashed",
                                    width=0.8, alpha=0.35, arrows=False)
        if flow_e:
            nx.draw_networkx_edges(G, pos, edgelist=flow_e, ax=ax,
                                    edge_color="#cbd5e1", width=2.2, alpha=0.85,
                                    arrows=True, arrowsize=18, arrowstyle="-|>",
                                    node_size=2400)
        if comp_e:
            nx.draw_networkx_edges(G, pos, edgelist=comp_e, ax=ax,
                                    edge_color="#94a3b8", width=1.2, alpha=0.6,
                                    arrows=True, arrowsize=12, arrowstyle="-|>",
                                    node_size=1200, connectionstyle="arc3,rad=0.12")

        if layer_ids:
            nx.draw_networkx_nodes(G, pos, nodelist=layer_ids, ax=ax,
                                    node_size=900, node_shape="s",
                                    node_color=[node_color[n] for n in layer_ids],
                                    edgecolors="white", linewidths=2)
        if comp_ids:
            nx.draw_networkx_nodes(G, pos, nodelist=comp_ids, ax=ax,
                                    node_size=700,
                                    node_color=[node_color[n] for n in comp_ids],
                                    edgecolors="white", linewidths=1.2, alpha=0.92)

        # Labels go OUTSIDE the nodes (above for layers, below for components)
        # so text never gets clipped no matter how long.
        for lid in layer_ids:
            x, y = pos[lid]
            ax.text(x, y + 0.045, node_label[lid], ha="center", va="bottom",
                    fontsize=9, fontweight="bold", color="#e2e8f0",
                    wrap=True)

        for cid in comp_ids:
            x, y = pos[cid]
            wrapped = "\n".join(textwrap.wrap(node_label[cid], 22))
            ax.text(x, y - 0.025, wrapped, ha="center", va="top",
                    fontsize=7, color="#cbd5e1")

        ax.text(0.5, 1.05, result.project_name, transform=ax.transAxes,
                ha="center", va="bottom", fontsize=15, fontweight="bold", color="#e2e8f0")
        ax.text(0.5, -0.03, "Interactive Diagram (Node-Graph)", transform=ax.transAxes,
                ha="center", va="top", fontsize=9, color="#94a3b8", style="italic")

        out_path = Path(self.output_dir) / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=BG)
        plt.close(fig)

        # Validate the file was actually written and is non-trivial.
        # matplotlib can swallow errors and produce empty/tiny PNGs that pass
        # path.exists() but break python-docx and reportlab embedding.
        if not out_path.exists():
            raise RuntimeError(f"Interactive PNG was not written to {out_path}")
        size = out_path.stat().st_size
        if size < 1024:
            raise RuntimeError(
                f"Interactive PNG at {out_path} is too small ({size} bytes), "
                "likely a silent matplotlib failure. Check fonts and Agg backend."
            )
        return str(out_path)

    def generate_mermaid(self, result: AnalysisResult) -> str:
        """Return Mermaid flowchart markup with per-layer colors."""
        import re as _re

        def _safe_id(text: str, prefix: str, index: int) -> str:
            """Build a collision-free Mermaid node ID from arbitrary text."""
            slug = _re.sub(r"[^a-z0-9]", "_", text.lower())[:12].strip("_")
            return f"{prefix}_{index}_{slug}"

        lines = ["flowchart LR"]   # left-right to match landscape orientation
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

            for j, comp in enumerate(layer.get("components", [])):
                cid = _safe_id(comp["name"], lid, j)
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
