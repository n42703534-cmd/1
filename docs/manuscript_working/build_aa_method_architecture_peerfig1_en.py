# Academic Figure Skill Asset Confirmation (verified against available project assets)
# (a) station-geometry overview -> cad_geometry/longyang_station_20260815.dxf -> param inherit
# (b) arrival-time-aware route-planning mechanism -> supplied method text + project implementation -> param inherit
# (c) Pathfinder model overview -> cad_geometry/pathfinder_longyang_overview_20260815.png -> native run
# (d) Pathfinder completion profile -> figures/fig2_pathfinder_high_load_validation.png -> native run
# RULE: "native run" = load source raster via Image.open().ax.imshow().
#       "param inherit" = deterministic vector drawing from the named project source.

"""Peer-Fig.1-informed architecture figure for arrival-time-aware AA* evacuation."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Polygon, Rectangle
from PIL import Image


WORK = Path(__file__).resolve().parent
OUT = WORK / "figures"
OUT.mkdir(parents=True, exist_ok=True)
BASE = OUT / "fig_aa_method_architecture_peerfig1_en"
CAD_DIR = WORK / "cad_geometry"
DXF_PATH = CAD_DIR / "longyang_station_20260815.dxf"
PF_PATH = CAD_DIR / "pathfinder_longyang_overview_20260815.png"
PF_PROFILE_PATH = OUT / "fig2_pathfinder_high_load_validation.png"

sys.path.insert(0, str(WORK))
import build_aa_method_architecture_real_en as cad_source  # noqa: E402


MM = 1 / 25.4
FIG_W_MM, FIG_H_MM = 183, 112
FONT = "Arial"

# Parameter-inherited palette: muted source blue, optimization orange, execution gold.
INK = "#26323D"
GRAY = "#68747E"
LINE = "#647078"
BLUE = "#466FA6"
BLUE_LIGHT = "#B9C9E4"
BLUE_PALE = "#EDF3FA"
ORANGE = "#D97725"
ORANGE_LIGHT = "#F7D4B5"
ORANGE_PALE = "#FDF0E3"
GOLD = "#E8B941"
GOLD_LIGHT = "#FBE8A9"
TEAL = "#4A8B82"
TEAL_PALE = "#ECF6F4"
PURPLE = "#7A69A2"
PURPLE_PALE = "#F3EFF8"
GREEN = "#6F9676"
WHITE = "#FFFFFF"

mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": [FONT, "Helvetica", "DejaVu Sans"],
        "font.size": 7,
        "text.color": INK,
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


def rect(ax, x, y, w, h, *, edge=LINE, fill=WHITE, lw=0.8, dashed=False, z=1):
    patch = Rectangle(
        (x, y), w, h, transform=ax.transAxes, facecolor=fill, edgecolor=edge,
        linewidth=lw, linestyle=(0, (5, 3)) if dashed else "-", zorder=z,
    )
    ax.add_patch(patch)
    return patch


def text(ax, x, y, value, *, fs=6, weight="normal", color=INK, ha="center", va="center", **kw):
    ax.text(x, y, value, transform=ax.transAxes, fontsize=fs, fontweight=weight,
            color=color, ha=ha, va=va, **kw)


def arrow(ax, p0, p1, *, color=LINE, lw=0.85, mutation=7, rad=0):
    ax.add_patch(
        FancyArrowPatch(
            p0, p1, transform=ax.transAxes, arrowstyle="-|>", mutation_scale=mutation,
            linewidth=lw, color=color, connectionstyle=f"arc3,rad={rad}",
            shrinkA=1.5, shrinkB=1.5, zorder=8,
        )
    )


def chevrons(ax, x, y, n=3, w=0.012, h=0.040, gap=0.003):
    for i in range(n):
        xx = x + i * (w + gap)
        ax.add_patch(
            Polygon(
                [[xx, y], [xx + w * 0.48, y], [xx + w, y + h / 2],
                 [xx + w * 0.48, y + h], [xx, y + h], [xx + w * 0.52, y + h / 2]],
                transform=ax.transAxes, closed=True, facecolor=BLUE, edgecolor="none", zorder=8,
            )
        )


def title_card(ax, x, y, w, h, title, *, strip=ORANGE, fill=WHITE, fs=5.7):
    rect(ax, x, y, w, h, edge=strip, fill=fill, lw=0.75)
    rect(ax, x, y + h - 0.036, w, 0.036, edge=strip, fill=strip, lw=0.0)
    text(ax, x + w / 2, y + h - 0.018, title, fs=fs, weight="bold", color=WHITE)


def parameter_card(ax, x, y, w, h, lines, color=BLUE):
    rect(ax, x, y, w, h, edge=color, fill=WHITE, lw=0.75, dashed=True)
    for j, line in enumerate(lines):
        yy = y + h - 0.023 - j * 0.023
        rect(ax, x + 0.016, yy - 0.007, 0.010, 0.013, edge=color, fill=WHITE, lw=0.45)
        text(ax, x + 0.034, y + h - 0.023 - j * 0.023, line, fs=4.7, ha="left")


def draw_timeline(ax, x, y, w):
    ax.plot([x, x + w], [y, y], transform=ax.transAxes, color=BLUE, linewidth=0.9, zorder=4)
    for frac, label, color in [(0.02, "$t_0$", BLUE), (0.40, "arrival", ORANGE), (0.70, "arrival", ORANGE), (0.96, "$\tau$", PURPLE)]:
        xx = x + w * frac
        ax.plot([xx, xx], [y - 0.016, y + 0.020], transform=ax.transAxes, color=color, linewidth=1.1, zorder=5)
        text(ax, xx, y - 0.030, label, fs=4.6, color=color)


def draw_branch(ax, x, y, w, h):
    pts = [(x + 0.07 * w, y + 0.50 * h), (x + 0.40 * w, y + 0.80 * h),
           (x + 0.40 * w, y + 0.20 * h), (x + 0.76 * w, y + 0.50 * h),
           (x + 0.94 * w, y + 0.50 * h)]
    for a, b, color, lw in [(pts[0], pts[1], BLUE, 1.0), (pts[0], pts[2], GRAY, 0.8),
                             (pts[1], pts[3], BLUE, 1.0), (pts[2], pts[3], GRAY, 0.8),
                             (pts[3], pts[4], ORANGE, 1.1)]:
        ax.plot([a[0], b[0]], [a[1], b[1]], transform=ax.transAxes, color=color, linewidth=lw, zorder=4)
    for px, py in pts:
        ax.scatter([px], [py], transform=ax.transAxes, s=10, facecolor=WHITE, edgecolor=BLUE, linewidth=0.7, zorder=5)


def draw_service_chain(ax, x, y, w, h):
    labels = ["flow", "queue", "service"]
    for i, label in enumerate(labels):
        xx = x + (0.08 + 0.31 * i) * w
        rect(ax, xx, y + 0.31 * h, 0.19 * w, 0.28 * h, edge=TEAL, fill=WHITE, lw=0.65)
        text(ax, xx + 0.095 * w, y + 0.45 * h, label, fs=4.5)
        if i < 2:
            arrow(ax, (xx + 0.19 * w, y + 0.45 * h), (xx + 0.30 * w, y + 0.45 * h), color=TEAL, lw=0.65, mutation=5)


def draw_allocation(ax, x, y, w, h):
    starts = [y + h * f for f in (0.25, 0.50, 0.75)]
    ends = [y + h * f for f in (0.70, 0.40, 0.20)]
    for yy in starts:
        ax.scatter([x + 0.12 * w], [yy], transform=ax.transAxes, s=11, facecolor=ORANGE, edgecolor=WHITE, linewidth=0.3, zorder=5)
    for yy in ends:
        ax.scatter([x + 0.86 * w], [yy], transform=ax.transAxes, s=11, facecolor=GREEN, edgecolor=WHITE, linewidth=0.3, zorder=5)
    for a, b in zip(starts, ends):
        arrow(ax, (x + 0.17 * w, a), (x + 0.80 * w, b), color=PURPLE, lw=0.65, mutation=5)


def build():
    fig = plt.figure(figsize=(FIG_W_MM * MM, FIG_H_MM * MM), facecolor=WHITE)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    # One outer container, then three operational zones. This follows Yang Fig. 1.
    rect(ax, 0.022, 0.085, 0.956, 0.850, edge="#40474D", fill=WHITE, lw=0.65)
    rect(ax, 0.038, 0.120, 0.205, 0.775, edge=ORANGE, fill=WHITE, lw=0.75, dashed=True)
    rect(ax, 0.270, 0.120, 0.500, 0.775, edge=ORANGE, fill=WHITE, lw=0.75, dashed=True)
    rect(ax, 0.800, 0.120, 0.160, 0.775, edge=ORANGE, fill=WHITE, lw=0.75, dashed=True)

    # INPUT: one authentic geometry image and one concise scenario card.
    title_card(ax, 0.052, 0.600, 0.177, 0.230, "Station geometry", strip=BLUE, fill=WHITE, fs=5.8)
    cad_ax = ax.inset_axes([0.062, 0.628, 0.157, 0.158])
    cad_source.render_cad(cad_ax)
    text(ax, 0.141, 0.614, "DWG/DXF station overview", fs=4.5, color=GRAY)

    title_card(ax, 0.052, 0.305, 0.177, 0.230, "Evacuation demand", strip=BLUE, fill=WHITE, fs=5.8)
    text(ax, 0.140, 0.478, "Reference occupants", fs=5.0, color=INK)
    text(ax, 0.140, 0.452, "+ train-arrival cohorts", fs=5.0, color=ORANGE)
    draw_timeline(ax, 0.074, 0.390, 0.132)
    rect(ax, 0.073, 0.330, 0.132, 0.035, edge=BLUE, fill=BLUE_PALE, lw=0.55)
    text(ax, 0.139, 0.348, "demand schedule", fs=4.6, color=BLUE, weight="bold")

    # Bottom ribbon used in Yang Fig.1 rather than an oversized panel heading.
    rect(ax, 0.090, 0.155, 0.100, 0.035, edge=BLUE, fill=BLUE_LIGHT, lw=0.65)
    text(ax, 0.140, 0.172, "INPUT", fs=5.6, weight="bold", color=INK)

    # Central zone: parameter cards -> four core modules -> mechanism sketches -> common execution.
    text(ax, 0.520, 0.875, "ARRIVAL-TIME-AWARE PLANNING AND EXECUTION", fs=7.2, weight="bold", color=INK)
    parameter_card(ax, 0.288, 0.760, 0.092, 0.090, ["capacity", "service rate", "receiving"], color=BLUE)
    parameter_card(ax, 0.398, 0.760, 0.092, 0.090, ["event time", "cohort size", "commitment"], color=ORANGE)
    parameter_card(ax, 0.508, 0.760, 0.092, 0.090, ["current state", "queue state", "density"], color=PURPLE)
    parameter_card(ax, 0.618, 0.760, 0.092, 0.090, ["route lock", "exit set", "update state"], color=TEAL)

    mods = [
        (0.286, "Dynamic flow\nstate", TEAL),
        (0.404, "ETA queue\nforecast", ORANGE),
        (0.522, "AA* path\nsearch", ORANGE),
        (0.640, "Rolling route\nassignment", ORANGE),
    ]
    for x, label, color in mods:
        rect(ax, x, 0.675, 0.102, 0.052, edge=color, fill=color, lw=0.6)
        text(ax, x + 0.051, 0.701, label, fs=5.15, weight="bold", color=WHITE)
        arrow(ax, (x + 0.051, 0.754), (x + 0.051, 0.729), color=LINE, lw=0.6, mutation=5)

    for x in (0.388, 0.506, 0.624):
        arrow(ax, (x, 0.701), (x + 0.014, 0.701), color=BLUE, lw=0.85, mutation=6)

    # Mechanism sketches are deliberately simple and local, as in the peer Fig. 1 figures.
    rect(ax, 0.286, 0.485, 0.102, 0.165, edge=ORANGE, fill=WHITE, lw=0.65)
    draw_service_chain(ax, 0.293, 0.505, 0.088, 0.112)
    text(ax, 0.337, 0.494, "facility service state", fs=4.55, color=INK)

    rect(ax, 0.404, 0.485, 0.102, 0.165, edge=ORANGE, fill=WHITE, lw=0.65)
    draw_timeline(ax, 0.419, 0.565, 0.070)
    text(ax, 0.455, 0.600, "advance events", fs=4.75, weight="bold")
    text(ax, 0.455, 0.520, r"$\hat Q_r(\tau)$", fs=7.0, color=ORANGE)
    text(ax, 0.455, 0.495, "queue at ETA", fs=4.55, color=GRAY)

    rect(ax, 0.522, 0.485, 0.102, 0.165, edge=ORANGE, fill=WHITE, lw=0.65)
    draw_branch(ax, 0.533, 0.535, 0.080, 0.078)
    text(ax, 0.573, 0.505, "time-labelled paths", fs=4.55, color=INK)

    rect(ax, 0.640, 0.485, 0.102, 0.165, edge=ORANGE, fill=WHITE, lw=0.65)
    draw_allocation(ax, 0.650, 0.530, 0.080, 0.088)
    text(ax, 0.691, 0.505, "source → exit allocation", fs=4.35, color=INK)

    # Short equation strip and common execution band draw from Wei/Junfeng hierarchy.
    rect(ax, 0.300, 0.435, 0.430, 0.032, edge=PURPLE, fill=PURPLE_PALE, lw=0.65)
    text(ax, 0.515, 0.451, r"$c_{uv}(\tau)$: movement + ETA queue + receiving + density exposure", fs=5.2, color=INK)
    arrow(ax, (0.515, 0.484), (0.515, 0.468), color=LINE, lw=0.65, mutation=5)

    rect(ax, 0.320, 0.315, 0.390, 0.075, edge=GOLD, fill=GOLD_LIGHT, lw=0.75)
    text(ax, 0.515, 0.365, "DYNAMIC EVACUATION-FLOW EXECUTION", fs=6.7, weight="bold", color=INK)
    text(ax, 0.515, 0.337, "accepted routes → capacity competition → state update", fs=5.25, color=INK)
    arrow(ax, (0.515, 0.433), (0.515, 0.393), color=GOLD, lw=1.1, mutation=8)
    ax.add_patch(
        FancyArrowPatch((0.342, 0.310), (0.342, 0.696), transform=ax.transAxes,
                        arrowstyle="-|>", mutation_scale=7, linewidth=0.85, color=TEAL,
                        connectionstyle="arc3,rad=0.18", zorder=7)
    )
    text(ax, 0.312, 0.495, "state feedback", fs=4.6, color=TEAL, rotation=90)
    rect(ax, 0.432, 0.225, 0.166, 0.040, edge=GOLD, fill=GOLD, lw=0.65)
    text(ax, 0.515, 0.245, "EVACUATION PLAN", fs=5.7, weight="bold", color=INK)
    arrow(ax, (0.515, 0.313), (0.515, 0.268), color=GOLD, lw=0.9, mutation=7)
    rect(ax, 0.655, 0.225, 0.072, 0.040, edge=ORANGE, fill=ORANGE, lw=0.65)
    text(ax, 0.691, 0.245, "EXPORT", fs=5.2, weight="bold", color=WHITE)

    # OUTPUT: one large true model image and one legible crop from a real result figure.
    title_card(ax, 0.815, 0.590, 0.130, 0.235, "Route allocation", strip=GREEN, fill=WHITE, fs=5.3)
    pf_ax = ax.inset_axes([0.826, 0.622, 0.108, 0.155])
    pf_img = Image.open(PF_PATH).convert("RGB")
    pf_ax.imshow(pf_img)
    pf_ax.set_xticks([]); pf_ax.set_yticks([])
    for spine in pf_ax.spines.values():
        spine.set_color(GREEN); spine.set_linewidth(0.55)
    text(ax, 0.880, 0.603, "Pathfinder execution", fs=4.55, color=GRAY)

    title_card(ax, 0.815, 0.305, 0.130, 0.235, "Completion profile", strip=GREEN, fill=WHITE, fs=5.3)
    if PF_PROFILE_PATH.exists():
        profile = Image.open(PF_PROFILE_PATH).convert("RGB")
        ww, hh = profile.size
        # Native figure content; only crop to its top-left completion-profile panel.
        crop = profile.crop((0, 0, int(ww * 0.52), int(hh * 0.54)))
        prof_ax = ax.inset_axes([0.826, 0.353, 0.108, 0.130])
        prof_ax.imshow(crop)
        prof_ax.set_xticks([]); prof_ax.set_yticks([])
        for spine in prof_ax.spines.values():
            spine.set_color(GREEN); spine.set_linewidth(0.55)
    text(ax, 0.880, 0.320, "cross-model check", fs=4.55, color=GRAY)

    rect(ax, 0.835, 0.155, 0.090, 0.035, edge=GREEN, fill="#DCEBDD", lw=0.65)
    text(ax, 0.880, 0.172, "OUTPUT", fs=5.6, weight="bold", color=INK)

    # Cross-stage blue chevrons match the peer figures' high-level flow.
    chevrons(ax, 0.246, 0.487)
    chevrons(ax, 0.773, 0.487)
    text(ax, 0.263, 0.465, "abstract", fs=4.45, color=GRAY)
    text(ax, 0.790, 0.465, "implement", fs=4.45, color=GRAY)

    fig.savefig(BASE.with_suffix(".png"), dpi=320, facecolor=WHITE)
    fig.savefig(BASE.with_suffix(".pdf"), facecolor=WHITE)
    fig.savefig(BASE.with_suffix(".svg"), facecolor=WHITE)
    fig.savefig(BASE.with_suffix(".tiff"), dpi=600, facecolor=WHITE,
                pil_kwargs={"compression": "tiff_lzw"})
    plt.close(fig)

    manifest = {
        "figure": str(BASE),
        "dimensions_mm": [FIG_W_MM, FIG_H_MM],
        "archetype": "schematic-led",
        "peer_fig1_design_sources": [
            "Junfeng et al. (2026): three-step workflow and pastel stage colors",
            "Wei et al. (2026): vertical stage hierarchy and compact analytical panels",
            "Yang et al. (2024): input-central-pipeline-output arrangement and chevron transfer arrows",
        ],
        "sources": {
            "dwg_sha256": sha256(CAD_DIR / "longyang_station_20260815.dwg"),
            "dxf_sha256": sha256(DXF_PATH),
            "pathfinder_overview_sha256": sha256(PF_PATH),
            "pathfinder_completion_profile": str(PF_PROFILE_PATH) if PF_PROFILE_PATH.exists() else None,
        },
        "text_language": "English",
        "quantitative_claims_added": False,
    }
    BASE.with_suffix(".source_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    caption = (
        "Fig. X. Reference-informed workflow of the arrival-time-aware evacuation method. "
        "Station geometry and demand events are transformed into a dynamic evacuation-flow state. "
        "The central pipeline advances committed arrivals to candidate ETAs, forecasts shared-resource queues, "
        "searches time-labelled paths, and assigns routes for common flow execution. "
        "Route and exit allocations are exported to Pathfinder for continuous-space execution and completion-profile checking."
    )
    BASE.with_suffix(".caption.txt").write_text(caption + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
