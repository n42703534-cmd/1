from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "龙阳路" / "高负荷"
OUT = Path(__file__).resolve().parent / "figures_revised"
OUT.mkdir(parents=True, exist_ok=True)

FILES = {
    "Improved A*": DATA / "龙阳路improved高负荷 _occupants.csv",
    "AA*": DATA / "龙阳路AA高负荷 _occupants.csv",
    "Pathfinder Goto Any Exit": DATA / "any exit（test）_occupants.csv",
}
COLORS = {"Improved A*": "#5684A8", "AA*": "#C85B4E", "Pathfinder Goto Any Exit": "#30353A"}
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
    frames = {name: pd.read_csv(path) for name, path in FILES.items()}
    names = list(FILES)

    summary = []
    for name, df in frames.items():
        summary.append(
            {
                "method": name,
                "level": df["level congestion time"].astype(float).mean(),
                "stair": df["stair congestion time"].astype(float).mean(),
                "distance": df["distance (m)"].astype(float).mean(),
                "mean_exit": df["exit time(s)"].astype(float).mean(),
                "T100": df["exit time(s)"].astype(float).max(),
            }
        )
    summary = pd.DataFrame(summary).set_index("method")

    fig = plt.figure(figsize=(183 / 25.4, 97 / 25.4))
    gs = fig.add_gridspec(1, 3, left=0.125, right=0.985, bottom=0.20, top=0.84, wspace=0.42)
    ax = fig.add_subplot(gs[0, 0])
    bx = fig.add_subplot(gs[0, 1])
    cx = fig.add_subplot(gs[0, 2])

    # a: congestion exposure composition
    y = np.arange(len(names))[::-1]
    level = summary.loc[names, "level"].to_numpy()
    stair = summary.loc[names, "stair"].to_numpy()
    cols = [COLORS[n] for n in names]
    ax.barh(y, level, height=0.55, color=cols, alpha=0.78, label="水平区域")
    ax.barh(y, stair, left=level, height=0.55, color=cols, alpha=0.34, hatch="///", edgecolor=cols, linewidth=0.6, label="楼梯")
    ax.set_yticks(y, ["Improved A*", "AA*", "Goto Any Exit"])
    ax.set_xlabel("人均拥堵时间（s）")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.55, 1.01), fontsize=6.5, ncol=2)
    ax.text(-0.25, 1.14, "a", transform=ax.transAxes, fontsize=10.5, fontweight="bold")
    ax.text(-0.08, 1.14, "拥堵暴露构成", transform=ax.transAxes, fontsize=9.0, fontweight="bold", color=INK)

    # b: distribution of travelled distance
    positions = np.arange(1, 4)
    vp = bx.violinplot([frames[n]["distance (m)"].astype(float) for n in names], positions=positions, widths=0.72, showmeans=False, showextrema=False, showmedians=False, bw_method=0.22)
    for body, name in zip(vp["bodies"], names):
        body.set_facecolor(COLORS[name]); body.set_edgecolor("none"); body.set_alpha(0.48)
    for pos, name in zip(positions, names):
        vals = frames[name]["distance (m)"].astype(float).to_numpy()
        q = np.quantile(vals, [0.25, 0.5, 0.75])
        bx.plot([pos, pos], [q[0], q[2]], color=COLORS[name], lw=3.2, solid_capstyle="round")
        bx.scatter([pos], [q[1]], color="white", edgecolor=COLORS[name], s=17, linewidth=1.0, zorder=3)
    bx.set_xticks(positions, ["Improved A*", "AA*", "Goto Any\nExit"])
    bx.set_ylabel("移动距离（m）")
    bx.set_ylim(bottom=0)
    bx.text(-0.22, 1.14, "b", transform=bx.transAxes, fontsize=10.5, fontweight="bold")
    bx.text(-0.05, 1.14, "乘客移动距离分布", transform=bx.transAxes, fontsize=9.0, fontweight="bold", color=INK)

    # c: average-tail frontier
    for name in names:
        x = summary.loc[name, "mean_exit"]
        yv = summary.loc[name, "T100"]
        cx.scatter(x, yv, s=55, color=COLORS[name], edgecolor="white", linewidth=0.8, zorder=3)
    cx.annotate("Improved A*", (summary.loc["Improved A*", "mean_exit"], summary.loc["Improved A*", "T100"]), xytext=(-6, 8), textcoords="offset points", ha="right", fontsize=6.8, color=COLORS["Improved A*"])
    cx.annotate("AA*", (summary.loc["AA*", "mean_exit"], summary.loc["AA*", "T100"]), xytext=(6, -12), textcoords="offset points", fontsize=6.8, color=COLORS["AA*"])
    cx.annotate("Goto Any Exit", (summary.loc["Pathfinder Goto Any Exit", "mean_exit"], summary.loc["Pathfinder Goto Any Exit", "T100"]), xytext=(-7, -13), textcoords="offset points", ha="right", fontsize=6.8, color=COLORS["Pathfinder Goto Any Exit"])
    cx.annotate("平均更快", xy=(0.06, 0.08), xycoords="axes fraction", xytext=(0.48, 0.08), textcoords="axes fraction", arrowprops=dict(arrowstyle="-|>", color=MID, lw=0.8), ha="center", va="center", fontsize=6.6, color=MID)
    cx.annotate("尾部更短", xy=(0.08, 0.06), xycoords="axes fraction", xytext=(0.08, 0.47), textcoords="axes fraction", arrowprops=dict(arrowstyle="-|>", color=MID, lw=0.8), ha="center", va="center", rotation=90, fontsize=6.6, color=MID)
    cx.set_xlabel("人均完成时间（s）")
    cx.set_ylabel(r"$T_{100}$（s）")
    cx.set_xlim(340, 455)
    cx.set_ylim(1260, 1490)
    cx.text(-0.24, 1.14, "c", transform=cx.transAxes, fontsize=10.5, fontweight="bold")
    cx.text(-0.07, 1.14, "平均—尾部运行点", transform=cx.transAxes, fontsize=9.0, fontweight="bold", color=INK)

    for panel in (ax, bx, cx):
        panel.grid(axis="x" if panel is ax else "y", color=GRID, linewidth=0.55, alpha=0.8, zorder=0)
        panel.spines[["top", "right"]].set_visible(False)
        panel.spines[["left", "bottom"]].set_color("#858C91")
        panel.tick_params(length=3, width=0.7, labelsize=7.0)

    summary.to_csv(OUT / "fig_pathfinder_tradeoff_revised_cn_source.csv", encoding="utf-8-sig")
    base = OUT / "fig_pathfinder_tradeoff_revised_cn"
    fig.savefig(base.with_suffix(".png"), dpi=320, facecolor="white")
    fig.savefig(base.with_suffix(".tiff"), dpi=600, facecolor="white", pil_kwargs={"compression": "tiff_lzw"})
    fig.savefig(base.with_suffix(".pdf"), facecolor="white")
    fig.savefig(base.with_suffix(".svg"), facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
