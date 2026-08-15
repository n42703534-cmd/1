from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle


OUT = Path(__file__).resolve().parents[1] / "figures_revised"
OUT.mkdir(parents=True, exist_ok=True)

LINE_COLORS = {
    "2号线": "#71A6D2",
    "7号线": "#E48B3C",
    "16号线": "#75A66F",
    "18号线": "#9D6CAD",
    "磁浮": "#B5534A",
}


def style():
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Microsoft YaHei", "Noto Sans CJK SC", "DejaVu Sans"],
            "font.size": 8,
            "axes.linewidth": 0.7,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }
    )


def card(ax, x, y, w, h, title, subtitle, color, radius=0.018):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=f"round,pad=0.008,rounding_size={radius}",
        facecolor="#FFFFFF",
        edgecolor=color,
        linewidth=1.2,
    )
    ax.add_patch(patch)
    ax.add_patch(Rectangle((x, y + h - 0.026), w, 0.026, facecolor=color, edgecolor="none"))
    ax.text(x + 0.018, y + h - 0.045, title, ha="left", va="top", fontsize=8.7, fontweight="bold", color="#22272B")
    ax.text(x + 0.018, y + h - 0.081, subtitle, ha="left", va="top", fontsize=7.0, color="#596067", linespacing=1.28)
    return patch


def arrow(ax, start, end, color="#70777D", width=1.0, rad=0.0, label=None, label_xy=None):
    patch = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=8,
        linewidth=width,
        color=color,
        connectionstyle=f"arc3,rad={rad}",
        shrinkA=3,
        shrinkB=3,
    )
    ax.add_patch(patch)
    if label and label_xy:
        ax.text(*label_xy, label, fontsize=6.8, color=color, ha="center", va="center")


def main():
    style()
    fig = plt.figure(figsize=(183 / 25.4, 116 / 25.4))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.52, 1.0], left=0.045, right=0.985, bottom=0.075, top=0.94, wspace=0.14)
    ax = fig.add_subplot(gs[0, 0])
    bx = fig.add_subplot(gs[0, 1])
    for panel in (ax, bx):
        panel.set_xlim(0, 1)
        panel.set_ylim(0, 1)
        panel.axis("off")

    ax.text(-0.02, 1.02, "a", transform=ax.transAxes, fontsize=10.5, fontweight="bold")
    ax.text(0.04, 1.02, "楼层—线路—换乘关系", transform=ax.transAxes, fontsize=9.2, fontweight="bold")

    # Draw the station as stacked spatial bands rather than a raw graph.
    floor_x, floor_w = 0.08, 0.82
    floors = [
        (0.76, 0.17, "地上二层", "16号线站厅 / 磁浮站厅", ["16号线", "磁浮"]),
        (0.54, 0.17, "地面一层", "2号线站厅 / 主要地面出入口", ["2号线"]),
        (0.32, 0.17, "地下一层", "7号线站厅 / 18号线站厅", ["7号线", "18号线"]),
        (0.10, 0.17, "站台层", "2、7、16、18号线与磁浮站台", ["2号线", "7号线", "16号线", "18号线", "磁浮"]),
    ]
    centers = {}
    for y, h, floor, description, lines in floors:
        ax.add_patch(
            FancyBboxPatch(
                (floor_x, y),
                floor_w,
                h,
                boxstyle="round,pad=0.006,rounding_size=0.015",
                facecolor="#F6F7F8",
                edgecolor="#B8BDC2",
                linewidth=0.8,
            )
        )
        ax.text(floor_x + 0.02, y + h - 0.035, floor, fontsize=8.2, fontweight="bold", color="#2B3035", va="top")
        ax.text(floor_x + 0.19, y + h - 0.035, description, fontsize=7.5, color="#3E4449", va="top")
        usable_x0 = floor_x + 0.19
        usable_x1 = floor_x + floor_w - 0.03
        positions = np.linspace(usable_x0, usable_x1, len(lines))
        for x, line in zip(positions, lines):
            ax.add_patch(
                FancyBboxPatch(
                    (x - 0.055, y + 0.035),
                    0.11,
                    0.052,
                    boxstyle="round,pad=0.006,rounding_size=0.012",
                    facecolor=LINE_COLORS[line],
                    edgecolor="none",
                    alpha=0.95,
                )
            )
            ax.text(x, y + 0.061, line, ha="center", va="center", fontsize=6.8, color="white", fontweight="bold")
            centers[(floor, line)] = (x, y + 0.061)

    # Vertical facilities and interchange corridors.
    for x, label in [(0.22, "楼梯/扶梯"), (0.72, "换乘通道")]:
        arrow(ax, (x, 0.29), (x, 0.72), color="#6D747A", width=1.15)
        ax.text(x + 0.018, 0.51, label, rotation=90, ha="left", va="center", fontsize=7, color="#555C62")
    for x in (0.33, 0.49, 0.63, 0.80):
        arrow(ax, (x, 0.095), (x, 0.30), color="#9AA0A5", width=0.8)

    # Exit-node groups follow lines_config.py; "8/9" and the two Exit 11 nodes are
    # distinct modelled objects even though they share a number in the drawings.
    for x, label in [
        (0.15, "2、3、4、6"),
        (0.33, "7、8/9"),
        (0.51, "10、11西/东"),
        (0.70, "12、13、17"),
        (0.87, "18–21"),
    ]:
        arrow(ax, (x, 0.71), (x, 0.965), color="#3F474E", width=0.9)
        ax.text(x, 0.975, f"出口 {label}", ha="center", va="bottom", fontsize=6.7, color="#33393F")

    ax.text(
        0.08,
        0.025,
        "依据 CAD 与 Pathfinder 建模对象抽象；用于解释线路、楼层和关键换乘设施的连通关系，不按比例绘制。",
        fontsize=6.6,
        color="#636A70",
    )

    bx.text(-0.03, 1.02, "b", transform=bx.transAxes, fontsize=10.5, fontweight="bold")
    bx.text(0.05, 1.02, "模型中的空间对象", transform=bx.transAxes, fontsize=9.2, fontweight="bold")

    card(bx, 0.06, 0.73, 0.86, 0.17, "活动区域", "站厅、站台与换乘通道\n承担乘客生成、行走与空间拥堵", "#768B9B")
    card(bx, 0.06, 0.49, 0.86, 0.17, "竖向设施", "楼梯与自动扶梯连接不同标高\n容量与服务过程形成关键瓶颈", "#B47C42")
    card(
        bx,
        0.06,
        0.25,
        0.86,
        0.17,
        "出口集合",
        "16 个最终出口节点\n2号线4个、7号线2个、16号线3个\n18号线3个、磁浮4个",
        "#4C6E91",
    )

    arrow(bx, (0.49, 0.72), (0.49, 0.67), color="#7B8288", width=1.0)
    arrow(bx, (0.49, 0.48), (0.49, 0.43), color="#7B8288", width=1.0)
    bx.text(0.49, 0.165, "CAD 几何 → 可通行区域与设施边界\nPathfinder → 连续空间运动与拥堵过程\n网络模型 → 路径决策与容量传播", ha="center", va="center", fontsize=7.2, color="#3D4348", linespacing=1.55)

    base = OUT / "fig_station_spatial_structure_cn"
    fig.savefig(base.with_suffix(".png"), dpi=320, facecolor="white")
    fig.savefig(base.with_suffix(".tiff"), dpi=600, facecolor="white", pil_kwargs={"compression": "tiff_lzw"})
    fig.savefig(base.with_suffix(".pdf"), facecolor="white")
    fig.savefig(base.with_suffix(".svg"), facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
