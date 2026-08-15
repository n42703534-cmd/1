from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np


OUT = Path(__file__).resolve().parent / "figures_revised"
OUT.mkdir(parents=True, exist_ok=True)

COLORS = {
    "2号线": "#6EA3CA",
    "7号线": "#E79242",
    "16号线": "#77A871",
    "18号线": "#9C72AC",
    "磁浮": "#B95B52",
}
INK = "#282D31"
MID = "#687077"
GRID = "#DDE1E4"


def configure() -> None:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Microsoft YaHei", "Noto Sans CJK SC", "Arial", "DejaVu Sans"],
            "font.size": 8,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }
    )


def main() -> None:
    configure()
    lines = ["2号线", "7号线", "16号线", "18号线", "磁浮"]
    platform = np.array([236, 219, 42, 178, 0])
    hall = np.array([350, 112, 15, 125, 0])
    transfer = np.array([526, 169, 27, 188, 0])
    train_each = np.array([2400, 1620, 1230, 1650, 959])
    base = platform + hall + transfer

    fig = plt.figure(figsize=(183 / 25.4, 95 / 25.4))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.05, 1.18], left=0.105, right=0.98, bottom=0.17, top=0.88, wspace=0.31)
    ax = fig.add_subplot(gs[0, 0])
    bx = fig.add_subplot(gs[0, 1])

    # a: source composition of the frozen 2,187-person baseline
    y = np.arange(len(lines))[::-1]
    left = np.zeros(len(lines))
    for vals, label, color, hatch in [
        (platform, "站台候车", "#5B88AC", ""),
        (hall, "站厅", "#91A6B6", "//"),
        (transfer, "换乘", "#D08A4A", ""),
    ]:
        ax.barh(y, vals, left=left, height=0.55, color=color, edgecolor="white", linewidth=0.6, hatch=hatch, label=label)
        left += vals
    for yy, total in zip(y, base):
        ax.text(total + 18, yy, f"{int(total):,}", va="center", fontsize=6.8, color=INK)
    ax.set_yticks(y, lines)
    ax.set_xlabel("人数")
    ax.set_xlim(0, 1250)
    ax.legend(frameon=False, loc="lower right", fontsize=6.8, ncol=1)
    ax.text(-0.23, 1.10, "a", transform=ax.transAxes, fontsize=10.5, fontweight="bold")
    ax.text(-0.08, 1.10, "基准需求的空间来源（2,187 人）", transform=ax.transAxes, fontsize=9, fontweight="bold", color=INK)

    # b: load construction by line, retaining the actual code-level decomposition
    x = np.arange(len(lines))
    bx.bar(x, base, color=[COLORS[k] for k in lines], alpha=0.38, width=0.62, label="基准需求")
    bx.bar(x, train_each, bottom=base, color=[COLORS[k] for k in lines], alpha=0.82, width=0.62, label="列车1")
    bx.bar(x, train_each, bottom=base + train_each, color=[COLORS[k] for k in lines], alpha=0.58, width=0.62, hatch="///", edgecolor=[COLORS[k] for k in lines], linewidth=0.5, label="列车2")
    totals = base + 2 * train_each
    for xx, total in zip(x, totals):
        bx.text(xx, total + 95, f"{int(total):,}", ha="center", va="bottom", fontsize=6.8, color=INK)
    bx.set_xticks(x, lines)
    bx.set_ylabel("人数")
    bx.set_ylim(0, 6500)
    handles = [
        mpl.patches.Patch(facecolor="#9AABB7", alpha=0.45, label="基准需求"),
        mpl.patches.Patch(facecolor="#6C88A0", alpha=0.82, label="列车1"),
        mpl.patches.Patch(facecolor="#6C88A0", alpha=0.58, hatch="///", label="列车2"),
    ]
    bx.legend(handles=handles, frameon=False, loc="upper right", fontsize=6.8)
    bx.text(-0.18, 1.10, "b", transform=bx.transAxes, fontsize=10.5, fontweight="bold")
    bx.text(-0.05, 1.10, "列车到站叠加需求（17,905 人）", transform=bx.transAxes, fontsize=9, fontweight="bold", color=INK)
    bx.text(
        0.98,
        0.035,
        "15,718 名列车乘客 + 2,187 名基准客流",
        transform=bx.transAxes,
        ha="right",
        fontsize=6.9,
        color=MID,
        bbox=dict(facecolor="white", edgecolor="none", alpha=0.90, pad=1.5),
    )

    for panel in (ax, bx):
        panel.grid(axis="x" if panel is ax else "y", color=GRID, linewidth=0.55, alpha=0.8, zorder=0)
        panel.spines[["top", "right"]].set_visible(False)
        panel.spines[["left", "bottom"]].set_color("#878E93")
        panel.tick_params(length=3, width=0.7, labelsize=7.2)

    source = np.column_stack([platform, hall, transfer, base, train_each, train_each, totals])
    header = "platform_waiting,hall_people,transfer_people,baseline,train_1,train_2,total"
    np.savetxt(OUT / "fig_demand_revised_cn_source.csv", source, delimiter=",", header=header, comments="", fmt="%.0f")

    base_path = OUT / "fig_demand_revised_cn"
    fig.savefig(base_path.with_suffix(".png"), dpi=320, facecolor="white")
    fig.savefig(base_path.with_suffix(".tiff"), dpi=600, facecolor="white", pil_kwargs={"compression": "tiff_lzw"})
    fig.savefig(base_path.with_suffix(".pdf"), facecolor="white")
    fig.savefig(base_path.with_suffix(".svg"), facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
