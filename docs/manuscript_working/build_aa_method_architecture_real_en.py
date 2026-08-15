# Academic Figure Skill Asset Confirmation (verified against available project assets)
# (a) CAD geometry -> user DWG exported as longyang_station_20260815.dxf -> param inherit
# (b) directed network -> network.py::build_graph() -> param inherit
# (c) AA* mechanism -> pasted method text + implementation -> param inherit
# (d) Pathfinder overview -> user-provided PNG -> native run
# RULE: "native run" = load the source raster without redrawing its scientific content.
#       "param inherit" = deterministic vector drawing from the named project source.

from __future__ import annotations

import hashlib
import json
import math
import sys
import warnings
from collections import Counter
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
CAD_DIR = WORK / "cad_geometry"
OUT = WORK / "figures"
OUT.mkdir(parents=True, exist_ok=True)

DXF_PATH = CAD_DIR / "longyang_station_20260815.dxf"
PATHFINDER_PATH = CAD_DIR / "pathfinder_longyang_overview_20260815.png"
BASE = OUT / "fig_aa_method_architecture_real_en"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(CAD_DIR))
import extract_dxf_inventory as dxf  # noqa: E402
import network as evacuation_network  # noqa: E402


# Journal-sized, vector-first style baseline.
MM = 1 / 25.4
FIG_W_MM = 183
FIG_H_MM = 112
FONT = "Arial"

NAVY = "#315B7D"
NAVY_DARK = "#213B52"
BLUE = "#6F9FC4"
TEAL = "#3E7C78"
TEAL_LIGHT = "#E8F3F1"
ORANGE = "#C58A3B"
ORANGE_LIGHT = "#FBF1E4"
GREEN = "#668F70"
GREEN_LIGHT = "#EDF4EC"
PURPLE = "#7D6AA2"
PURPLE_LIGHT = "#F1EDF7"
RED = "#C45E52"
INK = "#26333D"
MID = "#66737C"
LIGHT = "#D7DEE3"
PALE = "#F7F9FA"
WHITE = "#FFFFFF"


mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": [FONT, "Helvetica", "DejaVu Sans"],
        "font.size": 7.0,
        "axes.linewidth": 0.6,
        "text.color": INK,
        "axes.labelcolor": INK,
        "xtick.color": MID,
        "ytick.color": MID,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "savefig.facecolor": WHITE,
        "savefig.edgecolor": WHITE,
    }
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def panel_frame(ax, fill: str, edge: str, label: str, title: str) -> None:
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(
        FancyBboxPatch(
            (0.006, 0.006),
            0.988,
            0.988,
            boxstyle="round,pad=0.004,rounding_size=0.020",
            facecolor=fill,
            edgecolor=edge,
            linewidth=0.9,
            transform=ax.transAxes,
            clip_on=False,
        )
    )
    ax.text(0.035, 0.965, label, fontsize=10.0, fontweight="bold", va="top", color=INK)
    ax.text(0.145, 0.962, title, fontsize=8.4, fontweight="bold", va="top", color=INK)
    ax.plot([0.035, 0.965], [0.915, 0.915], color=edge, linewidth=1.0, solid_capstyle="round")


def rounded_box(
    ax,
    xy,
    wh,
    text,
    *,
    face=WHITE,
    edge=LIGHT,
    color=INK,
    fontsize=6.5,
    weight="normal",
    radius=0.018,
    linewidth=0.8,
):
    x, y = xy
    w, h = wh
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=f"round,pad=0.006,rounding_size={radius}",
        facecolor=face,
        edgecolor=edge,
        linewidth=linewidth,
    )
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fontsize, color=color, fontweight=weight)
    return patch


def arrow(ax, start, end, *, color=MID, linewidth=0.9, mutation=8, rad=0.0, zorder=5):
    patch = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=mutation,
        linewidth=linewidth,
        color=color,
        connectionstyle=f"arc3,rad={rad}",
        shrinkA=1.5,
        shrinkB=1.5,
        zorder=zorder,
    )
    ax.add_patch(patch)
    return patch


# Robust 1st–99th percentile model-space envelope of the 2026-08-15 DWG export.
# It excludes remote drawing artifacts while retaining the complete station body.
CAD_VIEW = (380_000, 680_000, 80_000, 720_000)


def _dxf_number(fields, code, default=0.0):
    try:
        return float(dxf.first(fields, code, str(default)))
    except ValueError:
        return default


def render_cad(ax) -> dict:
    x0, x1, y0, y1 = CAD_VIEW
    skip_layers = {
        "PUB_DIM",
        "DIM_LEAD",
        "AXIS",
        "C-AXIS",
        "Defpoints",
        "PUB_TEXT",
        "I-TEXT",
        "DIM_COOR",
    }
    wall_segments = []
    stair_segments = []
    gate_segments = []
    other_segments = []
    entity_counts = Counter()

    for kind, fields in dxf.parse_entities(DXF_PATH):
        layer = dxf.first(fields, 8, "")
        if layer in skip_layers or kind in {"TEXT", "MTEXT", "ATTRIB", "ATTDEF", "DIMENSION", "HATCH", "INSERT"}:
            continue
        xs = []
        ys = []
        if kind == "LINE":
            xs = [_dxf_number(fields, 10), _dxf_number(fields, 11)]
            ys = [_dxf_number(fields, 20), _dxf_number(fields, 21)]
        elif kind == "LWPOLYLINE":
            xs = dxf.floats(fields, 10)
            ys = dxf.floats(fields, 20)
        elif kind in {"CIRCLE", "ARC"}:
            cx, cy = _dxf_number(fields, 10), _dxf_number(fields, 20)
            radius = _dxf_number(fields, 40)
            start = np.deg2rad(_dxf_number(fields, 50, 0.0))
            end = np.deg2rad(_dxf_number(fields, 51, 360.0))
            if end <= start:
                end += 2 * np.pi
            theta = np.linspace(start, end, 26)
            xs = list(cx + radius * np.cos(theta))
            ys = list(cy + radius * np.sin(theta))
        else:
            continue
        if len(xs) < 2 or len(ys) < 2:
            continue
        if max(xs) < x0 or min(xs) > x1 or max(ys) < y0 or min(ys) > y1:
            continue
        if math.hypot(max(xs) - min(xs), max(ys) - min(ys)) > 280_000:
            continue
        points = np.column_stack([xs, ys])
        upper = layer.upper()
        if "WALL" in upper or "墙" in layer:
            wall_segments.append(points)
        elif "STAIR" in upper or "STRS" in upper or "楼梯" in layer:
            stair_segments.append(points)
        elif "AFC" in upper or "GATE" in upper or "闸" in layer:
            gate_segments.append(points)
        else:
            other_segments.append(points)
        entity_counts[kind] += 1

    ax.add_collection(LineCollection(other_segments, colors="#A9B1B7", linewidths=0.20, alpha=0.62, rasterized=False))
    ax.add_collection(LineCollection(wall_segments, colors="#35434C", linewidths=0.36, alpha=0.90, rasterized=False))
    ax.add_collection(LineCollection(stair_segments, colors=ORANGE, linewidths=0.34, alpha=0.90, rasterized=False))
    ax.add_collection(LineCollection(gate_segments, colors=GREEN, linewidths=0.34, alpha=0.92, rasterized=False))
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")
    return {
        "rendered_entities": int(sum(entity_counts.values())),
        "entity_types": dict(entity_counts),
        "wall_paths": len(wall_segments),
        "stair_paths": len(stair_segments),
        "gate_paths": len(gate_segments),
    }


def render_network(ax) -> dict:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        graph = evacuation_network.build_graph()
    pos = {
        node: tuple(data.get("pos")[:2])
        for node, data in graph.nodes(data=True)
        if data.get("pos") is not None and len(data.get("pos")) >= 2
    }
    base_edges = []
    shared_edges = []
    transfer_edges = []
    for u, v, data in graph.edges(data=True):
        if u not in pos or v not in pos:
            continue
        segment = np.array([pos[u], pos[v]], dtype=float)
        edge_type = str(data.get("edge_type", "")).lower()
        target_type = str(graph.nodes[v].get("type", "")).lower()
        if "transfer" in edge_type:
            transfer_edges.append(segment)
        elif target_type in {"gate", "stair", "escalator"} or "gate" in target_type:
            shared_edges.append(segment)
        else:
            base_edges.append(segment)

    ax.add_collection(LineCollection(base_edges, colors="#BFC7CD", linewidths=0.22, alpha=0.42))
    ax.add_collection(LineCollection(transfer_edges, colors=PURPLE, linewidths=0.36, alpha=0.50))
    ax.add_collection(LineCollection(shared_edges, colors=ORANGE, linewidths=0.42, alpha=0.60))

    categories = {
        "source": (TEAL, 5.0),
        "connection": (BLUE, 4.0),
        "facility": (ORANGE, 7.0),
        "exit": (GREEN, 8.0),
    }
    node_groups = {key: ([], []) for key in categories}
    for node, (x, y) in pos.items():
        node_type = str(graph.nodes[node].get("type", "")).lower()
        if node_type == "exit":
            key = "exit"
        elif node_type in {"gate", "stair", "escalator", "queue_area"} or "gate" in node_type:
            key = "facility"
        elif node_type in {"train", "train_car", "platform", "platform_waiting_zone"}:
            key = "source"
        else:
            key = "connection"
        node_groups[key][0].append(x)
        node_groups[key][1].append(y)
    for key, (color, size) in categories.items():
        xs, ys = node_groups[key]
        ax.scatter(xs, ys, s=size, facecolor=color, edgecolor=WHITE, linewidth=0.18, alpha=0.92, zorder=4)

    all_x = np.array([xy[0] for xy in pos.values()], dtype=float)
    all_y = np.array([xy[1] for xy in pos.values()], dtype=float)
    dx = max(float(all_x.max() - all_x.min()), 1.0)
    dy = max(float(all_y.max() - all_y.min()), 1.0)
    ax.set_xlim(all_x.min() - 0.04 * dx, all_x.max() + 0.04 * dx)
    ax.set_ylim(all_y.min() - 0.04 * dy, all_y.max() + 0.04 * dy)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")

    for node, short in {
        "Platform_L2": "L2",
        "Platform_L7": "L7",
        "Platform_L16": "L16",
        "Platform_L18": "L18",
        "Platform_Maglev": "MAG",
    }.items():
        if node in pos:
            x, y = pos[node]
            ax.text(x, y, short, fontsize=4.4, color=NAVY_DARK, ha="center", va="center", fontweight="bold", zorder=6)

    type_counts = Counter(str(data.get("type", "")) for _, data in graph.nodes(data=True))
    return {
        "nodes_total": graph.number_of_nodes(),
        "edges_total": graph.number_of_edges(),
        "nodes_with_position": len(pos),
        "node_type_counts": dict(type_counts),
        "rendered_base_edges": len(base_edges),
        "rendered_transfer_edges": len(transfer_edges),
        "rendered_shared_resource_edges": len(shared_edges),
    }


def add_figure_arrow(fig, x0, y0, x1, y1, color=NAVY):
    fig.add_artist(
        FancyArrowPatch(
            (x0, y0),
            (x1, y1),
            transform=fig.transFigure,
            arrowstyle="-|>",
            mutation_scale=10,
            linewidth=1.15,
            color=color,
            zorder=20,
        )
    )


def inspect_dxf_coordinates():
    centers = []
    kinds = Counter()
    for kind, fields in dxf.parse_entities(DXF_PATH):
        if kind == "LINE":
            xs = [_dxf_number(fields, 10), _dxf_number(fields, 11)]
            ys = [_dxf_number(fields, 20), _dxf_number(fields, 21)]
        elif kind == "LWPOLYLINE":
            xs = dxf.floats(fields, 10)
            ys = dxf.floats(fields, 20)
        elif kind in {"CIRCLE", "ARC", "INSERT", "TEXT", "MTEXT"}:
            xs = [_dxf_number(fields, 10)]
            ys = [_dxf_number(fields, 20)]
        else:
            continue
        if not xs or not ys:
            continue
        x = float(np.mean(xs))
        y = float(np.mean(ys))
        if math.isfinite(x) and math.isfinite(y):
            centers.append((x, y))
            kinds[kind] += 1
    data = np.asarray(centers, dtype=float)
    report = {
        "count": len(centers),
        "kinds": dict(kinds),
        "x_quantiles": np.quantile(data[:, 0], [0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1]).tolist(),
        "y_quantiles": np.quantile(data[:, 1], [0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1]).tolist(),
    }
    print(json.dumps(report, indent=2))


def build_figure():
    fig = plt.figure(figsize=(FIG_W_MM * MM, FIG_H_MM * MM), facecolor=WHITE)

    ax_a = fig.add_axes([0.020, 0.055, 0.240, 0.895])
    ax_b = fig.add_axes([0.275, 0.055, 0.180, 0.895])
    ax_c = fig.add_axes([0.470, 0.055, 0.290, 0.895])
    ax_d = fig.add_axes([0.775, 0.055, 0.205, 0.895])

    panel_frame(ax_a, "#F6F9FB", NAVY, "a", "Real station geometry")
    panel_frame(ax_b, "#F7F9FA", TEAL, "b", "Dynamic network")
    panel_frame(ax_c, "#FAF8FC", PURPLE, "c", "Arrival-time-aware AA*")
    panel_frame(ax_d, "#F7FAF6", GREEN, "d", "Pathfinder assessment")

    # Panel a: current DWG-derived station geometry.
    cad_ax = ax_a.inset_axes([0.055, 0.215, 0.89, 0.675])
    cad_stats = render_cad(cad_ax)
    ax_a.text(0.07, 0.180, "LONGYANG ROAD STATION", fontsize=7.0, fontweight="bold", color=NAVY_DARK)
    ax_a.text(0.07, 0.145, "Multi-line transfer complex", fontsize=6.1, color=MID)
    line_labels = [("L2", BLUE), ("L7", ORANGE), ("L16", GREEN), ("L18", PURPLE), ("Maglev", RED)]
    x = 0.07
    for label, color in line_labels:
        width = 0.11 if label != "Maglev" else 0.22
        rounded_box(ax_a, (x, 0.070), (width, 0.050), label, face=WHITE, edge=color, color=color, fontsize=5.8, weight="bold", radius=0.012)
        x += width + 0.025
    ax_a.text(0.07, 0.040, "Geometry: DWG-derived walls and facilities", fontsize=5.1, color=MID)
    ax_a.text(0.07, 0.019, "Demand: reference occupants + arriving trains", fontsize=5.1, color=MID)

    # Panel b: actual graph constructed by the simulation code.
    graph_ax = ax_b.inset_axes([0.075, 0.245, 0.85, 0.640])
    network_stats = render_network(graph_ax)
    legend_rows = [
        (0.165, TEAL, "Passenger sources"),
        (0.125, BLUE, "Connection nodes"),
        (0.085, ORANGE, "Shared facilities"),
        (0.045, GREEN, "Evacuation exits"),
    ]
    for y, color, text_label in legend_rows:
        ax_b.scatter([0.10], [y], s=12, facecolor=color, edgecolor=WHITE, linewidth=0.3, zorder=3)
        ax_b.text(0.18, y, text_label, va="center", fontsize=5.5, color=INK)
    ax_b.text(0.07, 0.205, "G = (N, E)", fontsize=7.0, color=NAVY_DARK, fontweight="bold")
    ax_b.text(0.07, 0.185, "572 nodes  •  1,414 directed edges", fontsize=5.1, color=MID)

    # Panel c: novelty module, written as a compact evidence-linked loop.
    ax_c.text(0.055, 0.882, "CONTROLLED DIFFERENCE", fontsize=5.5, color=MID, fontweight="bold")
    rounded_box(ax_c, (0.055, 0.805), (0.405, 0.060), "Improved A*\nCurrent queue  $Q_r(t_0)$", face=WHITE, edge=NAVY, color=NAVY_DARK, fontsize=5.7, weight="bold")
    rounded_box(ax_c, (0.540, 0.805), (0.405, 0.060), "Proposed AA*\nQueue at ETA  $\\widehat{Q}_r(\\tau)$", face=WHITE, edge=PURPLE, color=PURPLE, fontsize=5.7, weight="bold")

    ax_c.text(0.055, 0.755, "ARRIVAL-EVENT FORECAST", fontsize=5.5, color=MID, fontweight="bold")
    yline = 0.675
    ax_c.plot([0.08, 0.92], [yline, yline], color=NAVY, linewidth=1.0)
    events = [(0.15, 0.055, NAVY, "$t_0$"), (0.40, 0.085, BLUE, "accepted"), (0.62, 0.060, BLUE, "accepted"), (0.86, 0.110, RED, "$\\tau$")]
    for xevent, height, color, label in events:
        ax_c.plot([xevent, xevent], [yline - 0.025, yline + height], color=color, linewidth=1.25)
        ax_c.text(xevent, yline - 0.045, label, ha="center", va="top", fontsize=5.2, color=color)
    ax_c.text(0.50, 0.715, "Committed arrival events", fontsize=5.3, color=BLUE, ha="center")
    ax_c.text(0.86, 0.755, "Candidate ETA", fontsize=5.3, color=RED, ha="center")

    ax_c.text(0.055, 0.600, "TIME-DEPENDENT PATH COST", fontsize=5.5, color=MID, fontweight="bold")
    cost_cards = [
        (0.055, 0.520, 0.168, "Movement", NAVY),
        (0.236, 0.520, 0.168, "Predicted\nqueue", ORANGE),
        (0.417, 0.520, 0.168, "Batch\nservice", GREEN),
        (0.598, 0.520, 0.168, "Spatial\nreceiving", PURPLE),
        (0.779, 0.520, 0.168, "Density\nexposure", RED),
    ]
    for xcard, ycard, wcard, text_label, color in cost_cards:
        rounded_box(ax_c, (xcard, ycard), (wcard, 0.060), text_label, face=WHITE, edge=color, color=INK, fontsize=5.1, weight="bold", radius=0.012)
    ax_c.text(0.50, 0.490, "$c_{uv}(\\tau)$", ha="center", fontsize=7.1, color=PURPLE, fontweight="bold")

    flow = [
        (0.075, 0.355, 0.245, "Multi-label\nA* search", PURPLE_LIGHT, PURPLE),
        (0.378, 0.355, 0.245, "Rolling route\nassignment", ORANGE_LIGHT, ORANGE),
        (0.681, 0.355, 0.245, "Network-flow\nexecution", TEAL_LIGHT, TEAL),
    ]
    for xcard, ycard, wcard, text_label, face, edge in flow:
        rounded_box(ax_c, (xcard, ycard), (wcard, 0.082), text_label, face=face, edge=edge, color=INK, fontsize=5.5, weight="bold")
    arrow(ax_c, (0.325, 0.396), (0.372, 0.396), color=MID)
    arrow(ax_c, (0.628, 0.396), (0.675, 0.396), color=MID)
    ax_c.text(0.50, 0.310, "accepted requests", ha="center", fontsize=5.2, color=ORANGE)
    arrow(ax_c, (0.805, 0.348), (0.805, 0.265), color=TEAL)
    rounded_box(ax_c, (0.585, 0.205), (0.340, 0.055), "State update", face=WHITE, edge=TEAL, color=TEAL, fontsize=5.7, weight="bold")
    feedback = FancyArrowPatch(
        (0.585, 0.232),
        (0.195, 0.350),
        arrowstyle="-|>",
        mutation_scale=8,
        linewidth=1.0,
        color=TEAL,
        connectionstyle="arc3,rad=-0.42",
    )
    ax_c.add_patch(feedback)
    ax_c.text(0.33, 0.215, "occupancy  •  queues  •  future arrivals", fontsize=4.9, color=TEAL, ha="center")
    rounded_box(ax_c, (0.095, 0.095), (0.810, 0.065), "In-transit route locked", face=WHITE, edge=NAVY, color=NAVY_DARK, fontsize=6.0, weight="bold")
    ax_c.text(0.50, 0.048, "Shared physical executor for both routing methods", ha="center", fontsize=5.2, color=MID)

    # Panel d: user-supplied real Pathfinder model overview and evaluation outputs.
    rounded_box(ax_d, (0.090, 0.835), (0.820, 0.055), "Route & exit allocation", face=WHITE, edge=GREEN, color=GREEN, fontsize=6.0, weight="bold")
    arrow(ax_d, (0.50, 0.825), (0.50, 0.780), color=GREEN)
    pf_ax = ax_d.inset_axes([0.070, 0.350, 0.860, 0.420])
    pf_image = Image.open(PATHFINDER_PATH).convert("RGB")
    pf_ax.imshow(pf_image)
    pf_ax.set_xticks([])
    pf_ax.set_yticks([])
    for spine in pf_ax.spines.values():
        spine.set_color(GREEN)
        spine.set_linewidth(0.7)
    ax_d.text(0.50, 0.325, "Pathfinder model • top view", ha="center", fontsize=5.4, color=INK, fontweight="bold")
    ax_d.text(0.50, 0.297, "Continuous geometry and local interactions", ha="center", fontsize=5.0, color=MID)

    rounded_box(ax_d, (0.080, 0.205), (0.840, 0.065), "Network layer\nT95  •  T100\nstationary exposure", face=WHITE, edge=NAVY, color=INK, fontsize=4.9, weight="bold")
    rounded_box(ax_d, (0.080, 0.115), (0.840, 0.065), "Continuous space\ncompletion  •  congestion\nwalking distance", face=WHITE, edge=GREEN, color=INK, fontsize=4.9, weight="bold")
    arrow(ax_d, (0.50, 0.105), (0.50, 0.075), color=GREEN)
    ax_d.text(0.50, 0.045, "CROSS-MODEL ASSESSMENT", ha="center", fontsize=5.8, color=GREEN, fontweight="bold")

    add_figure_arrow(fig, 0.260, 0.505, 0.274, 0.505, NAVY)
    add_figure_arrow(fig, 0.455, 0.505, 0.469, 0.505, NAVY)
    add_figure_arrow(fig, 0.760, 0.505, 0.774, 0.505, NAVY)

    fig.savefig(BASE.with_suffix(".png"), dpi=320, facecolor=WHITE)
    fig.savefig(BASE.with_suffix(".pdf"), facecolor=WHITE)
    fig.savefig(BASE.with_suffix(".svg"), facecolor=WHITE)
    fig.savefig(BASE.with_suffix(".tiff"), dpi=600, facecolor=WHITE, pil_kwargs={"compression": "tiff_lzw"})
    plt.close(fig)

    manifest = {
        "figure": str(BASE),
        "dimensions_mm": [FIG_W_MM, FIG_H_MM],
        "sources": {
            "dwg_sha256": sha256(CAD_DIR / "longyang_station_20260815.dwg"),
            "dxf_sha256": sha256(DXF_PATH),
            "pathfinder_png_sha256": sha256(PATHFINDER_PATH),
            "network_source": str(ROOT / "network.py"),
            "routing_source": str(ROOT / "single_path_routing.py"),
        },
        "cad": cad_stats,
        "network": network_stats,
        "quantitative_panels": False,
    }
    BASE.with_suffix(".source_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    caption = (
        "Fig. X. Integrated evacuation-analysis framework for Longyang Road Station. "
        "(a) Station geometry rendered directly from the project DWG/DXF. "
        "(b) Directed dynamic network constructed from the implemented node, edge and shared-resource definitions. "
        "(c) Arrival-time-aware AA* advances committed arrival events to each candidate ETA, evaluates a time-dependent path cost, "
        "and exchanges accepted movements and updated states with the common network-flow executor. "
        "(d) Route and exit allocations are transferred to Pathfinder for continuous-space assessment."
    )
    BASE.with_suffix(".caption.txt").write_text(caption + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    if "--inspect-dxf" in sys.argv:
        inspect_dxf_coordinates()
    else:
        result = build_figure()
        print(json.dumps(result, indent=2))
