# Academic Figure Skill Asset Confirmation (verified against user-supplied assets)
# (a) station CAD linework -> longyang_station_20260815.dwg/.dxf -> param inherit
# RULE: "native run" = load pre-rendered PNG via Image.open().ax.imshow().
#       "param inherit" = drawing function below that copies Class A/B/C values.
#       The source DWG/DXF is rendered as vector linework; no screenshot is used.

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt


# Print-first standalone CAD export: the portrait aspect matches the station envelope.
MM = 1 / 25.4
WIDTH_MM, HEIGHT_MM = 140, 300
HERE = Path(__file__).resolve().parent
BASE = HERE / "longyang_station_cad_highres"

mpl.rcParams.update({
    "font.family": "DejaVu Sans",
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "svg.fonttype": "none",
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
})

# Reuse the validated DXF parser, viewport, layer grouping, and restrained layer palette
# from the manuscript figure. This reads the actual 2026-08-15 DWG export (DXF).
sys.path.insert(0, str(HERE.parent))
import build_aa_method_architecture_real_en as cad_source  # noqa: E402


def build() -> None:
    fig = plt.figure(figsize=(WIDTH_MM * MM, HEIGHT_MM * MM), facecolor="white")
    ax = fig.add_axes([0.025, 0.015, 0.950, 0.970])
    cad_source.render_cad(ax)
    ax.set_axis_off()

    fig.savefig(BASE.with_suffix(".pdf"), bbox_inches="tight", pad_inches=0.0, facecolor="white")
    fig.savefig(BASE.with_suffix(".svg"), bbox_inches="tight", pad_inches=0.0, facecolor="white")
    fig.savefig(BASE.with_suffix(".png"), dpi=600, bbox_inches="tight", pad_inches=0.0, facecolor="white")
    fig.savefig(BASE.with_suffix(".tiff"), dpi=600, bbox_inches="tight", pad_inches=0.0,
                facecolor="white", pil_kwargs={"compression": "tiff_lzw"})
    plt.close(fig)


if __name__ == "__main__":
    build()
