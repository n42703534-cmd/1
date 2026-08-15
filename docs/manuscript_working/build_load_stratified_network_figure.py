# Academic Figure Skill Asset Confirmation (verified against assets/figures/)
# (a) paired-load completion profiles -> param inherit -> native matplotlib run
# (b) paired-load waiting/distance trade-off -> param inherit -> native matplotlib run
# (c) paired-load stationary exposure -> param inherit -> native matplotlib run
# (d) paired-load computational cost -> param inherit -> native matplotlib run
# RULE: "native run" = load pre-rendered PNG via Image.open().ax.imshow().
#       "param inherit" = drawing function below that copies Class A/B/C values.

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "figures_revised"
OUT.mkdir(parents=True, exist_ok=True)

BLUE = "#4F7FA5"
RED = "#C85B4E"
INK = "#282D31"
MID = "#6B7277"
GRID = "#DDE1E4"

RUNS = {
    "低负荷": ROOT / "outputs" / "algorithm_compare" / "mode1_20260812_231621",
    "高负荷": ROOT / "outputs" / "algorithm_compare" / "mode4_20260808_173528",
}


def configure() -> None:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Microsoft YaHei", "Noto Sans CJK SC", "Arial", "DejaVu Sans"],
            "font.size": 8,
            "axes.linewidth": 0.75,
            "pdf.fonttype": 42,
            "svg.fonttype": "none",
        }
    )


def read_run(label: str) -> pd.DataFrame:
    rows = []
    for method, name in [("Improved A*", "ImprovedAStar"), ("AA*", "AdaptiveQueueAwareAStar")]:
        p = RUNS[label] / name / "summary_metrics.csv"
        row = pd.read_csv(p).iloc[0]
        rows.append(
            {
                "load": label,
                "method": method,
                "n": int(float(row["target_people"])),
                "mean": float(row["mean_total_evacuation_time_seconds_per_person"]),
                "T95": float(row["T95_seconds"]),
                "T99": float(row["T99_seconds"]),
                "T100": float(row["T100_seconds"]),
                "stationary_s": float(row["cumulative_stationary_person_seconds"]),
                "distance_m": float(row["total_movement_distance_m"]),
                "runtime_s": float(row["wall_clock_runtime_seconds"]),
            }
        )
    return pd.DataFrame(rows)


def style_axis(ax):
    ax.grid(axis="y", color=GRID, linewidth=0.55, alpha=0.8)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#858C91")
    ax.tick_params(length=3, width=0.7, labelsize=7.2)


def panel(ax, letter, title):
    ax.text(-0.16, 1.10, letter, transform=ax.transAxes, fontsize=10.5, fontweight="bold")
    ax.text(-0.04, 1.10, title, transform=ax.transAxes, fontsize=9, fontweight="bold", color=INK)


def main():
    configure()
    data = pd.concat([read_run(k) for k in ["低负荷", "高负荷"]], ignore_index=True)
    data.to_csv(OUT / "fig_load_stratified_network_cn_source.csv", index=False, encoding="utf-8-sig")

    fig, axes = plt.subplots(2, 2, figsize=(183 / 25.4, 112 / 25.4))
    fig.subplots_adjust(left=0.095, right=0.985, bottom=0.12, top=0.87, wspace=0.32, hspace=0.48)
    colors = {"Improved A*": BLUE, "AA*": RED}
    loads = ["低负荷", "高负荷"]
    xload = np.arange(2)

    # a: paired T95/T100 across load; avoid a single winner statement.
    ax = axes[0, 0]
    for method in ["Improved A*", "AA*"]:
        vals = data[data.method == method].set_index("load").loc[loads]
        ax.plot(xload - 0.08 if method == "Improved A*" else xload + 0.08, vals["T95"], marker="o", ms=4.5, lw=1.7, color=colors[method], label=f"{method} · T95")
        ax.plot(xload - 0.08 if method == "Improved A*" else xload + 0.08, vals["T100"], marker="s", ms=4.0, lw=1.2, color=colors[method], alpha=0.58, label=f"{method} · T100")
    ax.set_xticks(xload, ["2,187 人\n低负荷", "17,905 人\n高负荷"])
    ax.set_ylabel("完成时间（s）")
    ax.set_ylim(0, 1600)
    ax.legend(frameon=False, fontsize=6.4, ncol=2, loc="upper left", columnspacing=1.1, handlelength=1.8)
    panel(ax, "a", "网络层：中段与尾部清空随负荷变化")
    style_axis(ax)

    # b: the mechanistic trade-off, normalized to per-person stationary burden.
    ax = axes[0, 1]
    for method in ["Improved A*", "AA*"]:
        vals = data[data.method == method].set_index("load").loc[loads]
        ax.plot(xload, vals["stationary_s"] / vals["n"], marker="o", ms=4.8, lw=1.7, color=colors[method], label=method)
    ax.set_xticks(xload, ["低负荷", "高负荷"])
    ax.set_ylabel("人均静止暴露（s）")
    ax.legend(frameon=False, fontsize=7.0, loc="upper left")
    panel(ax, "b", "等待暴露：AA* 的负荷响应")
    style_axis(ax)

    # c: distance and waiting change relative to Improved A* at each load.
    ax = axes[1, 0]
    points = []
    for load in loads:
        sub = data[data.load == load].set_index("method")
        dchg = 100 * (sub.loc["AA*", "distance_m"] / sub.loc["Improved A*", "distance_m"] - 1)
        wchg = 100 * ((sub.loc["AA*", "stationary_s"] / sub.loc["AA*", "n"]) / (sub.loc["Improved A*", "stationary_s"] / sub.loc["Improved A*", "n"]) - 1)
        points.append((dchg, wchg, load))
    for x, y, load in points:
        ax.scatter(x, y, s=50, color=RED, edgecolor="white", linewidth=0.8, zorder=3)
        ax.annotate(load, (x, y), xytext=(6, 5), textcoords="offset points", fontsize=7.0, color=INK)
    ax.axhline(0, color="#AAB0B4", lw=0.8)
    ax.axvline(0, color="#AAB0B4", lw=0.8)
    ax.set_xlabel("AA* 总移动距离变化（%）")
    ax.set_ylabel("AA* 人均静止暴露变化（%）")
    ax.set_xlim(-2, 18)
    ax.set_ylim(-40, 8)
    panel(ax, "c", "绕行—等待取舍的负荷依赖")
    style_axis(ax)

    # d: runtime cost is explicitly separated from evacuation effect.
    ax = axes[1, 1]
    for method in ["Improved A*", "AA*"]:
        vals = data[data.method == method].set_index("load").loc[loads]
        ax.plot(xload, vals["runtime_s"], marker="o", ms=4.8, lw=1.7, color=colors[method], label=method)
    ax.set_xticks(xload, ["低负荷", "高负荷"])
    ax.set_ylabel("墙钟运行时间（s）")
    ax.legend(frameon=False, fontsize=7.0, loc="upper left")
    panel(ax, "d", "计算代价：负荷升高后的放大")
    style_axis(ax)

    base = OUT / "fig_load_stratified_network_cn"
    fig.savefig(base.with_suffix(".png"), dpi=320, facecolor="white")
    fig.savefig(base.with_suffix(".tiff"), dpi=600, facecolor="white", pil_kwargs={"compression": "tiff_lzw"})
    fig.savefig(base.with_suffix(".pdf"), facecolor="white")
    fig.savefig(base.with_suffix(".svg"), facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
