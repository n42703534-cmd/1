from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Rectangle


OUT = Path(__file__).resolve().parent / "figures_revised"
OUT.mkdir(parents=True, exist_ok=True)

NAVY = "#315B78"
BLUE = "#5F8FB3"
RED = "#C75D50"
ORANGE = "#C58A44"
GREEN = "#5D8D75"
INK = "#282D31"
MID = "#6C7379"
PALE = "#F4F6F7"


def setup():
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Microsoft YaHei", "Noto Sans CJK SC", "DejaVu Sans"],
            "font.size": 8,
            "mathtext.fontset": "dejavusans",
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }
    )


def arrow(ax, p0, p1, color=INK, width=1.1, rad=0.0, style="-|>"):
    ax.add_patch(
        FancyArrowPatch(
            p0,
            p1,
            arrowstyle=style,
            mutation_scale=8,
            linewidth=width,
            color=color,
            connectionstyle=f"arc3,rad={rad}",
            shrinkA=4,
            shrinkB=4,
        )
    )


def node(ax, xy, label, color, radius=0.037):
    ax.add_patch(Circle(xy, radius, facecolor=color, edgecolor="white", linewidth=1.0, zorder=4))
    ax.text(*xy, label, ha="center", va="center", color="white", fontsize=7.2, fontweight="bold", zorder=5)


def box(ax, x, y, w, h, title, text, color):
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.009,rounding_size=0.018",
            facecolor="white",
            edgecolor=color,
            linewidth=1.0,
        )
    )
    ax.add_patch(Rectangle((x, y + h - 0.025), w, 0.025, facecolor=color, edgecolor="none"))
    ax.text(x + 0.018, y + h - 0.044, title, ha="left", va="top", fontsize=8.0, fontweight="bold", color=INK)
    ax.text(x + 0.018, y + h - 0.105, text, ha="left", va="top", fontsize=6.55, color="#555D63", linespacing=1.30)


def main():
    setup()
    fig = plt.figure(figsize=(183 / 25.4, 137 / 25.4))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.06, 1.0], width_ratios=[1.14, 1.0], left=0.055, right=0.985, bottom=0.08, top=0.95, wspace=0.17, hspace=0.22)
    ax = fig.add_subplot(gs[0, 0])
    bx = fig.add_subplot(gs[0, 1])
    cx = fig.add_subplot(gs[1, :])
    for panel in (ax, bx, cx):
        panel.set_xlim(0, 1)
        panel.set_ylim(0, 1)
        panel.axis("off")

    # a: same physical network and the decision difference
    ax.text(-0.04, 1.01, "a", fontsize=10.5, fontweight="bold")
    ax.text(0.035, 1.01, "候选路径共享后续瓶颈", fontsize=9.0, fontweight="bold")
    positions = {"o": (0.11, 0.53), "u": (0.35, 0.75), "v": (0.35, 0.31), "r": (0.66, 0.53), "e": (0.90, 0.53)}
    arrow(ax, positions["o"], positions["u"], color=BLUE, width=1.8)
    arrow(ax, positions["o"], positions["v"], color=RED, width=1.8)
    arrow(ax, positions["u"], positions["r"], color=BLUE, width=1.8)
    arrow(ax, positions["v"], positions["r"], color=RED, width=1.8)
    arrow(ax, positions["r"], positions["e"], color=INK, width=1.8)
    node(ax, positions["o"], "O", NAVY)
    node(ax, positions["u"], r"$P_1$", BLUE)
    node(ax, positions["v"], r"$P_2$", RED)
    node(ax, positions["r"], "R", ORANGE, radius=0.045)
    node(ax, positions["e"], "E", GREEN)
    ax.text(0.66, 0.44, "容量设施\n" + r"服务率 $\mu_R$", ha="center", va="top", fontsize=6.8, color=MID)
    ax.text(0.11, 0.44, "决策时刻 $t_0$", ha="center", va="top", fontsize=6.8, color=MID)
    ax.text(0.90, 0.44, "最终出口", ha="center", va="top", fontsize=6.8, color=MID)
    ax.text(0.36, 0.10, "两条路径的几何长度可以接近，\n差别来自到达瓶颈 R 时面对的队列状态。", ha="center", va="center", fontsize=7.0, color="#464D53")

    # b: event-based queue prediction
    bx.text(-0.04, 1.01, "b", fontsize=10.5, fontweight="bold")
    bx.text(0.035, 1.01, "把队列推进到预计到达时刻", fontsize=9.0, fontweight="bold")
    y = 0.49
    bx.plot([0.08, 0.94], [y, y], color="#7C8388", linewidth=1.0)
    times = [(0.12, r"$t_0$", NAVY), (0.35, r"$a_1$", BLUE), (0.58, r"$a_2$", BLUE), (0.84, r"$\tau_R$", RED)]
    for x, label, color in times:
        bx.plot([x, x], [y - 0.035, y + 0.035], color=color, linewidth=1.2)
        bx.text(x, y - 0.075, label, ha="center", va="top", fontsize=7.5, color=color)
    bx.text(0.12, y + 0.09, "当前队列 $Q_R(t_0)$", ha="left", va="bottom", fontsize=7.0, color=INK)
    bx.add_patch(Rectangle((0.12, y + 0.06), 0.19, 0.055, facecolor="#D9DDE0", edgecolor="none"))
    bx.annotate(r"服务消化 $\mu_R\Delta t$", xy=(0.51, y + 0.11), xytext=(0.51, y + 0.22), ha="center", fontsize=6.9, color=GREEN, arrowprops=dict(arrowstyle="-|>", color=GREEN, lw=0.9))
    for x in (0.35, 0.58):
        bx.add_patch(Circle((x, y + 0.09), 0.018, facecolor=BLUE, edgecolor="white", linewidth=0.6))
    bx.text(0.47, y + 0.14, "已承诺但尚未到达的流量", ha="center", va="bottom", fontsize=6.8, color=BLUE)
    bx.add_patch(Rectangle((0.76, y + 0.06), 0.16, 0.055, facecolor="#E6B0AA", edgecolor="none"))
    bx.text(0.84, y + 0.14, "预计剩余队列", ha="center", va="bottom", fontsize=6.8, color=RED)
    bx.text(0.50, 0.19, r"$\hat Q_R(\tau_R)=\mathcal{F}\!\left(Q_R(t_0),\{(a_k,m_k)\},\mu_R,\tau_R\right)$", ha="center", va="center", fontsize=8.8, color=INK)
    bx.text(0.50, 0.085, "事件按到达时间排序；相邻事件间先服务，再叠加已承诺到达量。", ha="center", va="center", fontsize=6.8, color="#5C6369")

    # c: cumulative route evaluation and search
    cx.text(-0.02, 1.01, "c", fontsize=10.5, fontweight="bold")
    cx.text(0.025, 1.01, "逐段累计物理到达时间与广义代价", fontsize=9.0, fontweight="bold")
    boxes = [
        (0.02, "物理行走", "$t^{move}_{ij}$\n共享速度—密度关系\n及设施运动规则", BLUE),
        (0.27, "服务等待", r"$\hat Q_r(\tau)/\mu_r$" + "\n预计到达时刻的\n资源队列等待", ORANGE),
        (0.52, "空间接纳", r"$t^{space}_j(\tau)$" + "\n下游容量与回溢\n引起的进入等待", GREEN),
        (0.77, "密度暴露", r"$\lambda\,\Delta R_{ij}$" + "\n等待和移动阶段的\n密度等级积分", RED),
    ]
    for x, title, text, color in boxes:
        box(cx, x, 0.54, 0.21, 0.31, title, text, color)
    for x in (0.24, 0.49, 0.74):
        arrow(cx, (x, 0.69), (x + 0.025, 0.69), color="#7D848A", width=0.9)

    cx.add_patch(FancyBboxPatch((0.10, 0.13), 0.80, 0.23, boxstyle="round,pad=0.012,rounding_size=0.02", facecolor=PALE, edgecolor="#B6BBC0", linewidth=0.8))
    cx.text(0.50, 0.290, r"$\tau_j=\tau_i+t^{move}_{ij}+\hat Q_r(\tau_i)/\mu_r+t^{batch}_r+t^{space}_j$", ha="center", va="center", fontsize=9.2, color=INK)
    cx.text(0.50, 0.205, r"$C_j=C_i+(\tau_j-\tau_i)+\lambda\,\Delta R_{ij}$", ha="center", va="center", fontsize=9.2, color=INK)
    cx.text(0.50, 0.060, r"以 $(\tau,C)$ 保留互不支配的时间标签；从全部可达出口中选择最小广义代价路径。", ha="center", va="center", fontsize=7.2, color="#4F565C")

    base = OUT / "fig_aa_method_revised_cn"
    fig.savefig(base.with_suffix(".png"), dpi=320, facecolor="white")
    fig.savefig(base.with_suffix(".tiff"), dpi=600, facecolor="white", pil_kwargs={"compression": "tiff_lzw"})
    fig.savefig(base.with_suffix(".pdf"), facecolor="white")
    fig.savefig(base.with_suffix(".svg"), facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
