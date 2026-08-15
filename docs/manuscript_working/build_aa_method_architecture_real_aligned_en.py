"""Build a reference-aligned, source-grounded architecture figure.

Layout is intentionally close to the user's three reference figures:
input strip on the left, a dense model/optimization block in the centre,
and a real-model verification strip on the right.  CAD, network and
Pathfinder content are loaded from project assets; only the explanatory
workflow elements are drawn as vector graphics.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle
from PIL import Image


WORK = Path(__file__).resolve().parent
OUT = WORK / "figures"
OUT.mkdir(parents=True, exist_ok=True)
BASE = OUT / "fig_aa_method_architecture_real_aligned_en"
CAD_DIR = WORK / "cad_geometry"
DXF_PATH = CAD_DIR / "longyang_station_20260815.dxf"
PATHFINDER_PATH = CAD_DIR / "pathfinder_longyang_overview_20260815.png"
PF_RESULT_PATH = OUT / "fig2_pathfinder_high_load_validation.png"

sys.path.insert(0, str(WORK))
import build_aa_method_architecture_real_en as source_figure  # noqa: E402


MM = 1 / 25.4
FIG_W_MM, FIG_H_MM = 183, 130

NAVY = "#315B7D"
NAVY_DARK = "#1F3B55"
BLUE = "#6F9FC4"
TEAL = "#4A8A82"
ORANGE = "#C98C3F"
GREEN = "#6D9676"
PURPLE = "#7B6AA1"
RED = "#C55E53"
INK = "#25313B"
MID = "#64717A"
LIGHT = "#C9D1D6"
PALE_BLUE = "#F3F7FA"
PALE_ORANGE = "#FCF7EE"
PALE_GREEN = "#F4F8F3"
PALE_PURPLE = "#F8F5FB"
WHITE = "#FFFFFF"

mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 6.6,
        "text.color": INK,
        "axes.linewidth": 0.55,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "savefig.facecolor": WHITE,
        "savefig.edgecolor": WHITE,
    }
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def frame(ax, x, y, w, h, edge, fill, title, subtitle=None, dashed=True):
    style = "round,pad=0.003,rounding_size=0.008"
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h, boxstyle=style, facecolor=fill, edgecolor=edge,
            linewidth=0.9, linestyle=(0, (3, 2)) if dashed else "-",
            transform=ax.transAxes, zorder=1,
        )
    )
    ax.text(x + 0.018, y + h - 0.020, title, ha="left", va="top",
            fontsize=8.4, fontweight="bold", color=INK, transform=ax.transAxes, zorder=6)
    if subtitle:
        ax.text(x + 0.018, y + h - 0.047, subtitle, ha="left", va="top",
                fontsize=5.5, color=MID, transform=ax.transAxes, zorder=6)


def box(ax, x, y, w, h, title, text="", edge=LIGHT, fill=WHITE,
        title_color=INK, fs=5.7, lw=0.75, dashed=False):
    style = "round,pad=0.003,rounding_size=0.006"
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h, boxstyle=style, facecolor=fill, edgecolor=edge,
            linewidth=lw, linestyle=(0, (2, 1.4)) if dashed else "-",
            transform=ax.transAxes, zorder=2,
        )
    )
    ax.text(x + w / 2, y + h - 0.020, title, ha="center", va="top",
            fontsize=fs, fontweight="bold", color=title_color,
            transform=ax.transAxes, zorder=6)
    if text:
        ax.text(x + w / 2, y + h / 2 - 0.008, text, ha="center", va="center",
                fontsize=max(fs - 0.35, 4.5), color=INK, linespacing=1.18,
                transform=ax.transAxes, zorder=6)


def arrow(ax, x0, y0, x1, y1, color=NAVY, lw=0.9, mutation=8, rad=0):
    ax.add_patch(
        FancyArrowPatch(
            (x0, y0), (x1, y1), transform=ax.transAxes,
            arrowstyle="-|>", mutation_scale=mutation, linewidth=lw,
            color=color, connectionstyle=f"arc3,rad={rad}",
            shrinkA=2.5, shrinkB=2.5, zorder=8,
        )
    )


def chevron(ax, x, y, w=0.020, h=0.050, color=NAVY):
    ax.add_patch(
        plt.Polygon(
            [[x, y + h * 0.5], [x + w * 0.42, y + h],
             [x + w, y + h], [x + w * 0.58, y + h * 0.5],
             [x + w, y], [x + w * 0.42, y]],
            closed=True, facecolor=color, edgecolor="none",
            transform=ax.transAxes, zorder=8,
        )
    )


def render_network_compact(ax):
    stats = source_figure.render_network(ax)
    return stats


def draw_timeline(ax, x, y, w, h, labels=None):
    ax.plot([x + 0.02, x + w - 0.02], [y + h * 0.47, y + h * 0.47],
            color=NAVY, linewidth=0.8, transform=ax.transAxes, zorder=4)
    event_labels = labels or ["t0", "arrival 1", "arrival 2", "candidate ETA"]
    for frac, label, color in zip(
        (0.08, 0.34, 0.60, 0.86), event_labels, (NAVY, ORANGE, ORANGE, RED)
    ):
        xx = x + w * frac
        ax.plot([xx], [y + h * 0.47], marker="o", markersize=2.8, color=color,
                markeredgecolor=WHITE, markeredgewidth=0.35,
                transform=ax.transAxes, zorder=5)
        ax.text(xx, y + h * 0.10, label, ha="center", va="top", fontsize=4.55,
                color=color, transform=ax.transAxes, zorder=6)


def draw_people(ax, x, y, color=TEAL, scale=1.0):
    # Minimal flat symbol used only as a module cue, not a scientific result.
    for dx in (0.0, 0.020, 0.040):
        ax.add_patch(plt.Circle((x + dx, y + 0.020 * scale), 0.007 * scale,
                                facecolor=color, edgecolor="none",
                                transform=ax.transAxes, zorder=5))
        ax.plot([x + dx, x + dx], [y - 0.015 * scale, y + 0.010 * scale],
                color=color, linewidth=1.0, transform=ax.transAxes, zorder=5)


def build():
    fig = plt.figure(figsize=(FIG_W_MM * MM, FIG_H_MM * MM), facecolor=WHITE)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    ax.text(0.030, 0.972, "Arrival-time-aware evacuation analysis for a multi-line metro station",
            fontsize=10.4, fontweight="bold", color=NAVY_DARK, va="top", transform=ax.transAxes)
    ax.text(0.030, 0.952, "Longyang Road Station - dynamic network flow - continuous-space verification",
            fontsize=6.2, color=MID, va="top", transform=ax.transAxes)

    # The three large blocks follow the input/model/output arrangement in the references.
    frame(ax, 0.024, 0.070, 0.235, 0.860, NAVY, PALE_BLUE,
          "1. INPUT", "Station geometry and scenario definition")
    frame(ax, 0.278, 0.070, 0.470, 0.860, PURPLE, PALE_PURPLE,
          "2. MODEL / OPTIMIZATION", "Arrival-time-aware planning coupled to dynamic execution")
    frame(ax, 0.767, 0.070, 0.209, 0.860, GREEN, PALE_GREEN,
          "3. OUTPUT", "Pathfinder verification and metrics")

    # INPUT - only source assets that remain legible at the final figure size.
    box(ax, 0.040, 0.555, 0.223, 0.315, "Station geometry", "",
        edge=BLUE, fill=WHITE, fs=6.4)
    cad_ax = ax.inset_axes([0.052, 0.585, 0.199, 0.235])
    source_figure.render_cad(cad_ax)
    ax.text(0.151, 0.570, "Longyang Road Station - DWG/DXF-derived layout", ha="center",
            fontsize=4.9, color=MID, transform=ax.transAxes)

    box(ax, 0.040, 0.315, 0.223, 0.205, "Demand and scenario inputs", "",
        edge=BLUE, fill=WHITE, fs=6.2)
    ax.text(0.151, 0.465, "Reference occupants + train arrivals", ha="center",
            fontsize=5.3, color=INK, transform=ax.transAxes)
    ax.text(0.151, 0.445, "arrival-event timeline", ha="center", fontsize=4.7,
            color=ORANGE, transform=ax.transAxes)
    draw_timeline(ax, 0.052, 0.355, 0.199, 0.085,
                  labels=["t0", "arrival 1", "arrival 2", "candidate ETA"])
    ax.text(0.052, 0.337, "baseline demand", fontsize=4.8, color=TEAL, transform=ax.transAxes)
    ax.text(0.251, 0.337, "arrival events", ha="right", fontsize=4.8, color=ORANGE, transform=ax.transAxes)

    box(ax, 0.040, 0.145, 0.223, 0.135, "Shared-resource parameters", "",
        edge=BLUE, fill=WHITE, fs=6.0)
    box(ax, 0.052, 0.165, 0.060, 0.065, "Service", r"$\mu_r$",
        edge=BLUE, fill=WHITE, fs=5.2)
    box(ax, 0.120, 0.165, 0.060, 0.065, "Receiving", r"$K_j$",
        edge=ORANGE, fill=WHITE, fs=5.2)
    box(ax, 0.188, 0.165, 0.063, 0.065, "Speed–density", r"$v(\rho)$",
        edge=GREEN, fill=WHITE, fs=4.8)
    ax.text(0.151, 0.117, "stairs / escalators / gates", ha="center",
            fontsize=4.9, color=MID, transform=ax.transAxes)

    # MODEL / OPTIMIZATION - fewer, larger modules with dedicated equation space.
    box(ax, 0.300, 0.805, 0.426, 0.050, "", "", edge=PURPLE, fill=WHITE, lw=0.8)
    ax.text(0.513, 0.838, "CONTROLLED COMPARISON", ha="center", fontsize=5.0,
            fontweight="bold", color=PURPLE, transform=ax.transAxes)
    ax.text(0.513, 0.819, "Improved A*: current queue   |   Proposed AA*: queue at ETA   |   common executor",
            ha="center", fontsize=4.45, color=INK, transform=ax.transAxes)

    ax.text(0.304, 0.785, "ARRIVAL-TIME-AWARE AA* ROUTING DECISION", fontsize=6.5,
            fontweight="bold", color=NAVY_DARK, transform=ax.transAxes)
    alg = [
        ("Candidate paths", "feasible route set", BLUE),
        ("ETA propagation", r"$\tau_j$ at each node", NAVY),
        ("Queue forecast", r"$\hat Q_r(\tau)$", ORANGE),
        ("Multi-label search", r"$C(P)$ + Pareto labels", PURPLE),
    ]
    x0, y0, bw, bh, gap = 0.306, 0.635, 0.096, 0.120, 0.013
    for i, (title, detail, color) in enumerate(alg):
        xx = x0 + i * (bw + gap)
        box(ax, xx, y0, bw, bh, title, detail, edge=color, fill=WHITE, fs=5.3, lw=0.8)
        if i < len(alg) - 1:
            arrow(ax, xx + bw + 0.002, y0 + bh / 2, xx + bw + gap - 0.002,
                  y0 + bh / 2, color=MID, lw=0.75, mutation=7)
    ax.text(0.394, 0.705, "arrival-event timeline", ha="center", fontsize=4.45,
            color=ORANGE, transform=ax.transAxes)
    draw_timeline(ax, 0.319, 0.650, 0.150, 0.050,
                  labels=["t0", "a1", "a2", "candidate ETA"])

    # A separate equation band prevents the formula from colliding with module titles.
    box(ax, 0.300, 0.585, 0.426, 0.045, "", "", edge=ORANGE, fill=PALE_ORANGE, lw=0.8)
    ax.text(0.323, 0.614, "TIME-DEPENDENT PATH COST", fontsize=5.3, fontweight="bold",
            color=ORANGE, transform=ax.transAxes)
    ax.text(0.550, 0.603, r"$C(P)=\sum[t^{move}+w^{queue}+w^{space}]+\lambda R(P)$",
            ha="center", fontsize=6.0, color=INK, transform=ax.transAxes)

    box(ax, 0.420, 0.515, 0.178, 0.050, "", "", edge=PURPLE, fill=WHITE, lw=0.8)
    ax.text(0.509, 0.548, "Route assignment", ha="center", fontsize=5.7,
            fontweight="bold", color=INK, transform=ax.transAxes)
    ax.text(0.509, 0.528, "rolling replanning", ha="center", fontsize=4.8,
            color=MID, transform=ax.transAxes)
    arrow(ax, 0.509, 0.583, 0.509, 0.566, color=PURPLE, lw=0.8, mutation=7)
    arrow(ax, 0.509, 0.512, 0.509, 0.475, color=ORANGE, lw=0.8, mutation=7)
    ax.text(0.528, 0.490, "accepted requests", fontsize=4.9, color=ORANGE, transform=ax.transAxes)

    box(ax, 0.300, 0.135, 0.426, 0.335, "DYNAMIC NETWORK-FLOW EXECUTION", "",
        edge=TEAL, fill="#F2F8F7", fs=6.6, lw=0.8)
    exec_cards = [
        ("Shared-resource\nservice", "stairs / gates", TEAL),
        ("Capacity +\nreceiving", r"$\mu_r$, $K_j$", ORANGE),
        ("Density-speed\nupdate", r"$v(\rho)$", PURPLE),
        ("In-transit events\n+ route lock", "state update", NAVY),
    ]
    ex, ey, ew, eh, eg = 0.315, 0.235, 0.091, 0.150, 0.014
    for i, (title, detail, color) in enumerate(exec_cards):
        xx = ex + i * (ew + eg)
        box(ax, xx, ey, ew, eh, title, detail, edge=color, fill=WHITE, fs=5.05, lw=0.75)
    ax.text(0.513, 0.178, "In-transit route locked - committed passengers keep their route",
            ha="center", fontsize=5.0, color=NAVY_DARK, fontweight="bold", transform=ax.transAxes)

    ax.add_patch(
        FancyArrowPatch((0.301, 0.285), (0.301, 0.745), transform=ax.transAxes,
                        arrowstyle="-|>", mutation_scale=7, linewidth=0.9,
                        color=TEAL, connectionstyle="arc3,rad=0.0", zorder=8)
    )
    ax.text(0.291, 0.515, "state feedback: occupancy / queues / future arrivals", rotation=90,
            ha="center", va="center", fontsize=4.8, color=TEAL, transform=ax.transAxes)

    # OUTPUT / VERIFICATION - real Pathfinder image and readable metric cards.
    box(ax, 0.781, 0.805, 0.181, 0.050, "Export route & exit allocation", "",
        edge=GREEN, fill=WHITE, fs=5.3)
    arrow(ax, 0.872, 0.802, 0.872, 0.795, color=GREEN, lw=0.8, mutation=7)
    box(ax, 0.781, 0.500, 0.181, 0.310, "Pathfinder execution", "",
        edge=GREEN, fill=WHITE, fs=5.8)
    pf_ax = ax.inset_axes([0.792, 0.550, 0.159, 0.210])
    pf_image = Image.open(PATHFINDER_PATH).convert("RGB")
    pf_ax.imshow(pf_image)
    pf_ax.set_xticks([]); pf_ax.set_yticks([])
    for spine in pf_ax.spines.values():
        spine.set_color(GREEN); spine.set_linewidth(0.6)
    ax.text(0.872, 0.522, "continuous geometry - local interactions", ha="center",
            fontsize=4.6, color=MID, transform=ax.transAxes)

    box(ax, 0.781, 0.325, 0.086, 0.135, "Network layer",
        "mean / T95 / T100\nstationary exposure\nload balance", edge=NAVY, fill=WHITE, fs=5.0)
    box(ax, 0.876, 0.325, 0.086, 0.135, "Continuous space",
        "completion time\ncongestion time\nwalking distance", edge=GREEN, fill=WHITE, fs=4.9)
    box(ax, 0.781, 0.100, 0.181, 0.175, "Cross-model assessment", "",
        edge=GREEN, fill=WHITE, fs=5.2)
    ax.text(0.872, 0.226, "route transfer -> Pathfinder validation", ha="center",
            fontsize=4.55, color=INK, transform=ax.transAxes)
    if PF_RESULT_PATH.exists():
        result_ax = ax.inset_axes([0.792, 0.115, 0.159, 0.095])
        result_img = Image.open(PF_RESULT_PATH).convert("RGB")
        result_ax.imshow(result_img)
        result_ax.set_xticks([]); result_ax.set_yticks([])
        for spine in result_ax.spines.values():
            spine.set_color(GREEN); spine.set_linewidth(0.55)

    # Cross-stage arrows are kept large and sparse, as in the supplied references.
    chevron(ax, 0.262, 0.492, color=NAVY)
    chevron(ax, 0.751, 0.492, color=NAVY)
    ax.text(0.267, 0.462, "abstract", ha="center", fontsize=4.7, color=MID, transform=ax.transAxes)
    ax.text(0.756, 0.462, "transfer", ha="center", fontsize=4.7, color=MID, transform=ax.transAxes)

    fig.savefig(BASE.with_suffix(".png"), dpi=320, facecolor=WHITE)
    fig.savefig(BASE.with_suffix(".pdf"), facecolor=WHITE)
    fig.savefig(BASE.with_suffix(".svg"), facecolor=WHITE)
    fig.savefig(BASE.with_suffix(".tiff"), dpi=600, facecolor=WHITE,
                pil_kwargs={"compression": "tiff_lzw"})
    plt.close(fig)

    manifest = {
        "figure": str(BASE),
        "dimensions_mm": [FIG_W_MM, FIG_H_MM],
        "layout": "reference-aligned input-model-optimization-output",
        "sources": {
            "dwg": str(CAD_DIR / "longyang_station_20260815.dwg"),
            "dwg_sha256": sha256(CAD_DIR / "longyang_station_20260815.dwg"),
            "dxf": str(DXF_PATH),
            "dxf_sha256": sha256(DXF_PATH),
            "pathfinder_png": str(PATHFINDER_PATH),
            "pathfinder_png_sha256": sha256(PATHFINDER_PATH),
            "network_source": str(WORK.parent.parent / "network.py"),
            "pathfinder_validation_thumbnail": str(PF_RESULT_PATH) if PF_RESULT_PATH.exists() else None,
        },
        "network": {
            "rendered_in_figure": False,
            "reason": "The implemented network graph was omitted because it was not legible at the reference-aligned figure scale.",
        },
        "text_language": "English",
        "quantitative_claims_added": False,
    }
    BASE.with_suffix(".source_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    caption = (
        "Fig. X. Reference-aligned architecture of the proposed arrival-time-aware evacuation method. "
        "The input block combines the Longyang Road Station DWG/DXF geometry, arrival-demand events and shared-resource parameters. "
        "The central block couples ETA propagation and "
        "committed arrival-event forecasting with a time-dependent path cost, rolling route assignment and "
        "dynamic network-flow execution; passengers already in transit retain their committed routes. "
        "The output block transfers route and exit allocations to Pathfinder for continuous-space verification "
        "and cross-model assessment, with the supplied Pathfinder validation results shown in the output block."
    )
    BASE.with_suffix(".caption.txt").write_text(caption + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
