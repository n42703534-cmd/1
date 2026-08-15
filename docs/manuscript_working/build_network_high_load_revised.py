from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "outputs" / "algorithm_compare" / "mode4_20260808_173528"
OUT = Path(__file__).resolve().parent / "figures_revised"
OUT.mkdir(parents=True, exist_ok=True)

BLUE = "#4F7FA5"
RED = "#C85B4E"
INK = "#282D31"
MID = "#6B7277"
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


def read_metrics(method: str) -> pd.Series:
    return pd.read_csv(RUN / method / "summary_metrics.csv").iloc[0]


def read_lines(method: str) -> pd.DataFrame:
    return pd.read_csv(RUN / method / "line_clearance.csv").set_index("line")


def main() -> None:
    configure()
    imp = read_metrics("ImprovedAStar")
    aa = read_metrics("AdaptiveQueueAwareAStar")
    imp_line = read_lines("ImprovedAStar")
    aa_line = read_lines("AdaptiveQueueAwareAStar")

    fig = plt.figure(figsize=(183 / 25.4, 121 / 25.4))
    gs = fig.add_gridspec(
        2,
        2,
        width_ratios=[1.08, 1.0],
        height_ratios=[1.0, 1.0],
        left=0.095,
        right=0.985,
        bottom=0.11,
        top=0.89,
        hspace=0.38,
        wspace=0.31,
    )
    ax = fig.add_subplot(gs[0, 0])
    bx = fig.add_subplot(gs[0, 1])
    cx = fig.add_subplot(gs[1, 0])
    dx = fig.add_subplot(gs[1, 1])

    # a: full evacuation-time profile derived from person-time totals and quantiles
    metrics = ["平均", r"$T_{95}$", r"$T_{99}$", r"$T_{100}$"]
    imp_v = np.array(
        [
            float(imp["mean_total_evacuation_time_seconds_per_person"]),
            float(imp["T95_seconds"]),
            float(imp["T99_seconds"]),
            float(imp["T100_seconds"]),
        ]
    )
    aa_v = np.array(
        [
            float(aa["mean_total_evacuation_time_seconds_per_person"]),
            float(aa["T95_seconds"]),
            float(aa["T99_seconds"]),
            float(aa["T100_seconds"]),
        ]
    )
    x = np.arange(len(metrics))
    ax.plot(x, imp_v, marker="o", ms=4.5, lw=1.8, color=BLUE, label="Improved A*")
    ax.plot(x, aa_v, marker="o", ms=4.5, lw=1.8, color=RED, label="AA*")
    ax.fill_between(x, aa_v, imp_v, where=imp_v >= aa_v, color=RED, alpha=0.07)
    for xi, yi, ya in zip(x, imp_v, aa_v):
        if yi > ya:
            ax.annotate(f"−{100*(yi-ya)/yi:.1f}%", (xi, (yi+ya)/2), xytext=(6, 0), textcoords="offset points", va="center", fontsize=6.7, color=RED)
    ax.set_xticks(x, metrics)
    ax.set_ylabel("完成时间（s）")
    ax.set_ylim(0, 1600)
    ax.legend(frameon=False, loc="upper left", ncol=2, handlelength=2.2)
    ax.text(-0.18, 1.12, "a", transform=ax.transAxes, fontsize=10.5, fontweight="bold")
    ax.text(-0.05, 1.12, "站级完成时间剖面", transform=ax.transAxes, fontsize=9, fontweight="bold", color=INK)

    # b: line clearance lollipop; paired connection shows redistribution across lines
    lines = ["L2", "L7", "L16", "L18", "Maglev"]
    labels = ["2号线", "7号线", "16号线", "18号线", "磁浮"]
    yi = np.arange(len(lines))[::-1]
    iv = imp_line.loc[lines, "clearance_time_seconds"].astype(float).to_numpy()
    av = aa_line.loc[lines, "clearance_time_seconds"].astype(float).to_numpy()
    for y, x0, x1 in zip(yi, iv, av):
        bx.plot([x0, x1], [y, y], color="#BBC1C5", lw=1.7, zorder=1)
    bx.scatter(iv, yi, color=BLUE, s=32, zorder=2, label="Improved A*")
    bx.scatter(av, yi, color=RED, s=32, zorder=2, label="AA*")
    bx.set_yticks(yi, labels)
    bx.set_xlabel("线路完全清空时间（s）")
    bx.set_xlim(250, 1550)
    bx.legend(frameon=False, loc="lower right", fontsize=7.0)
    bx.text(-0.18, 1.12, "b", transform=bx.transAxes, fontsize=10.5, fontweight="bold")
    bx.text(-0.05, 1.12, "线路清空时间", transform=bx.transAxes, fontsize=9, fontweight="bold", color=INK)

    # c: decompose total person time into moving and stationary components
    comp_labels = ["移动", "静止"]
    imp_comp = np.array([float(imp["moving_person_seconds"]), float(imp["cumulative_stationary_person_seconds"])]) / 1e6
    aa_comp = np.array([float(aa["moving_person_seconds"]), float(aa["cumulative_stationary_person_seconds"])]) / 1e6
    for y, name, vals, color in [(1, "Improved A*", imp_comp, BLUE), (0, "AA*", aa_comp, RED)]:
        left = 0
        for val, lab, hatch in zip(vals, comp_labels, ["//", ""]):
            cx.barh(y, val, left=left, height=0.45, color=color, alpha=0.78 if lab == "静止" else 0.40, hatch=hatch, edgecolor=color, linewidth=0.6)
            if val > 0.7:
                cx.text(left + val / 2, y, f"{lab}\n{val:.2f}", ha="center", va="center", fontsize=6.7, color="white" if lab == "静止" else INK)
            left += val
    cx.set_yticks([1, 0], ["Improved A*", "AA*"])
    cx.set_xlabel("累计人·秒（百万）")
    cx.set_xlim(0, 8.2)
    cx.text(-0.18, 1.12, "c", transform=cx.transAxes, fontsize=10.5, fontweight="bold")
    cx.text(-0.05, 1.12, "移动—静止时间构成", transform=cx.transAxes, fontsize=9, fontweight="bold", color=INK)

    # d: outcome-cost plane; one benchmark segment is more honest than two disconnected bars
    runtime_ratio = float(aa["wall_clock_runtime_seconds"]) / float(imp["wall_clock_runtime_seconds"])
    distance_change = 100 * (float(aa["total_movement_distance_m"]) / float(imp["total_movement_distance_m"]) - 1)
    stationary_change = 100 * (float(aa["cumulative_stationary_person_seconds"]) / float(imp["cumulative_stationary_person_seconds"]) - 1)
    dx.axhline(0, color="#B9BFC3", lw=0.8)
    dx.scatter([0, distance_change], [0, stationary_change], s=[34, 54], color=[BLUE, RED], edgecolor="white", linewidth=0.8, zorder=3)
    dx.plot([0, distance_change], [0, stationary_change], color="#AAB0B4", lw=1.0, zorder=1)
    dx.text(0.6, 2.0, "Improved A*", fontsize=6.8, color=BLUE)
    dx.text(distance_change - 0.4, stationary_change - 2.2, "AA*", fontsize=6.8, color=RED, ha="right", va="top")
    dx.annotate(f"运行时间 ×{runtime_ratio:.1f}", (distance_change, stationary_change), xytext=(6.4, -13), textcoords="data", fontsize=7.0, color=INK, arrowprops=dict(arrowstyle="-", color=MID, lw=0.7))
    dx.set_xlabel("总移动距离变化（%）")
    dx.set_ylabel("累计静止人·秒变化（%）")
    dx.set_xlim(-2, 25)
    dx.set_ylim(-42, 8)
    dx.text(-0.18, 1.12, "d", transform=dx.transAxes, fontsize=10.5, fontweight="bold")
    dx.text(-0.05, 1.12, "绕行—等待—计算取舍", transform=dx.transAxes, fontsize=9, fontweight="bold", color=INK)

    for panel in (ax, bx, cx, dx):
        panel.grid(axis="both", color=GRID, linewidth=0.55, alpha=0.8, zorder=0)
        panel.spines[["top", "right"]].set_visible(False)
        panel.spines[["left", "bottom"]].set_color("#858C91")
        panel.tick_params(length=3, width=0.7, labelsize=7.2)

    source = pd.DataFrame(
        {
            "metric": metrics,
            "ImprovedAStar": imp_v,
            "AAStar": aa_v,
        }
    )
    source.to_csv(OUT / "fig_network_high_load_revised_cn_station_source.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame({"line": labels, "ImprovedAStar": iv, "AAStar": av}).to_csv(
        OUT / "fig_network_high_load_revised_cn_line_source.csv", index=False, encoding="utf-8-sig"
    )

    base = OUT / "fig_network_high_load_revised_cn"
    fig.savefig(base.with_suffix(".png"), dpi=320, facecolor="white")
    fig.savefig(base.with_suffix(".tiff"), dpi=600, facecolor="white", pil_kwargs={"compression": "tiff_lzw"})
    fig.savefig(base.with_suffix(".pdf"), facecolor="white")
    fig.savefig(base.with_suffix(".svg"), facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
