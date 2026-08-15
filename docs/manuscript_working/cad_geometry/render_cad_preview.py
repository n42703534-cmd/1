from __future__ import annotations

import sys
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_dxf_inventory as dxf


VIEW = (-6_950_000, -6_400_000, -9_750_000, -9_050_000)


def number(fields, code, default=0.0):
    try:
        return float(dxf.first(fields, code, str(default)))
    except ValueError:
        return default


def render():
    mpl.rcParams["font.sans-serif"] = ["Microsoft YaHei", "DejaVu Sans"]
    fig, ax = plt.subplots(figsize=(9, 9))
    x0, x1, y0, y1 = VIEW
    count = 0
    for kind, fields in dxf.parse_entities(dxf.DXF):
        layer = dxf.first(fields, 8, "")
        if layer in {"PUB_DIM", "DIM_LEAD", "AXIS", "C-AXIS", "Defpoints"}:
            continue
        if kind == "LINE":
            xs = [number(fields, 10), number(fields, 11)]
            ys = [number(fields, 20), number(fields, 21)]
        elif kind == "LWPOLYLINE":
            xs = dxf.floats(fields, 10)
            ys = dxf.floats(fields, 20)
        elif kind in {"CIRCLE", "ARC"}:
            cx, cy = number(fields, 10), number(fields, 20)
            radius = number(fields, 40)
            start = np.deg2rad(number(fields, 50, 0.0))
            end = np.deg2rad(number(fields, 51, 360.0))
            if end <= start:
                end += 2 * np.pi
            theta = np.linspace(start, end, 30)
            xs = list(cx + radius * np.cos(theta))
            ys = list(cy + radius * np.sin(theta))
        else:
            continue
        if not xs or not ys:
            continue
        if max(xs) < x0 or min(xs) > x1 or max(ys) < y0 or min(ys) > y1:
            continue
        color = "#5F666C"
        width = 0.22
        if layer in {"STAIR", "A-STRS"}:
            color, width = "#A86D32", 0.35
        elif layer in {"ARWALL", "WALL", "地墙"}:
            color, width = "#22272B", 0.42
        ax.plot(xs, ys, color=color, linewidth=width, alpha=0.72)
        count += 1

    texts = []
    for kind, fields in dxf.parse_entities(dxf.DXF):
        if kind not in {"TEXT", "MTEXT"}:
            continue
        x, y = number(fields, 10), number(fields, 20)
        if not (x0 <= x <= x1 and y0 <= y <= y1):
            continue
        label = dxf.first(fields, 1, "")
        if any(key in label for key in ("站厅", "出入口", "换乘通道", "站台")):
            texts.append((x, y, label))
    for x, y, label in texts:
        ax.text(x, y, label, fontsize=5.5, color="#9E3131", ha="center", va="center")

    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")
    ax.set_title(f"CAD model-space preview ({count:,} geometry entities)", loc="left", fontsize=10)
    fig.tight_layout()
    fig.savefig(Path(__file__).resolve().parent / "cad_preview.png", dpi=260, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    render()
