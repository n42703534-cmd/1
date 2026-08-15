# Academic Figure Skill Asset Confirmation (verified against assets/figures/)
# (a) completion ECDF by load -> param inherit -> native matplotlib run
# (b) quantile profile by load -> param inherit -> native matplotlib run
# (c) paired passenger difference -> param inherit -> native matplotlib run
# (d) congestion exposure tail -> param inherit -> native matplotlib run
# RULE: "native run" = load pre-rendered PNG via Image.open().ax.imshow().
#       "param inherit" = drawing function below that copies Class A/B/C values.

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, MultipleLocator


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "龙阳路" / "低负荷"
OUT = Path(__file__).resolve().parent / "figures_revised"
OUT.mkdir(parents=True, exist_ok=True)

METHODS = {
    "Improved A*": {"color": "#547FA3", "linestyle": (0, (5.0, 2.2))},
    "AA*": {"color": "#C65A4A", "linestyle": "-"},
    "Pathfinder Goto Any Exit": {"color": "#30353B", "linestyle": (0, (1.2, 1.5))},
}
FILES = {
    "低负荷": {
        "Improved A*": RAW / "龙阳路improved低负荷 _occupants.csv",
        "AA*": RAW / "龙阳路AA低负荷 _occupants.csv",
        "Pathfinder Goto Any Exit": RAW / "any exit低负荷（test）_occupants.csv",
    },
    "高负荷": {
        "Improved A*": ROOT / "龙阳路" / "高负荷" / "龙阳路improved高负荷 _occupants.csv",
        "AA*": ROOT / "龙阳路" / "高负荷" / "龙阳路AA高负荷 _occupants.csv",
        "Pathfinder Goto Any Exit": ROOT / "龙阳路" / "高负荷" / "any exit（test）_occupants.csv",
    },
}


def configure():
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Microsoft YaHei", "Noto Sans CJK SC", "Arial Unicode MS", "DejaVu Sans"],
            "font.size": 8.2,
            "axes.labelsize": 8.6,
            "xtick.labelsize": 7.4,
            "ytick.labelsize": 7.4,
            "axes.linewidth": 0.75,
            "pdf.fonttype": 42,
            "svg.fonttype": "none",
        }
    )


def load_frames():
    frames = {}
    for load, mapping in FILES.items():
        frames[load] = {}
        for label, path in mapping.items():
            df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
            for col in ["exit time(s)", "congestion time total(s)", "distance (m)"]:
                df[col] = pd.to_numeric(df[col], errors="raise")
            frames[load][label] = df
    return frames


def ecdf(v):
    x = np.sort(v.astype(float)); y = np.arange(1, len(x) + 1) / len(x); return x, y


def ccdf(v):
    x = np.sort(v.astype(float)); y = (len(x) - np.arange(len(x))) / len(x); return x, y


def clean(ax):
    ax.grid(axis="y", color="#D6D9DC", linewidth=0.45, alpha=0.6)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    ax.tick_params(length=3, width=0.65)


def panel(ax, label, title):
    ax.text(-0.13, 1.055, label, transform=ax.transAxes, fontsize=10.5, fontweight="bold")
    ax.text(-0.03, 1.055, title, transform=ax.transAxes, fontsize=9, fontweight="semibold")


def main():
    configure(); frames = load_frames()
    rows = []
    for load, methods in frames.items():
        for label, d in methods.items():
            rows.append({"load": load, "method": label, "n": len(d), "mean": d["exit time(s)"].mean(), "T95": d["exit time(s)"].quantile(.95), "T100": d["exit time(s)"].max(), "mean_cong": d["congestion time total(s)"].mean(), "mean_distance": d["distance (m)"].mean()})
    pd.DataFrame(rows).to_csv(OUT / "fig_load_stratified_pathfinder_cn_summary.csv", index=False, encoding="utf-8-sig")

    fig, axes = plt.subplots(2, 2, figsize=(183 / 25.4, 145 / 25.4))
    fig.subplots_adjust(left=0.105, right=0.985, bottom=0.10, top=0.875, wspace=0.30, hspace=0.42)
    load_colors = {"低负荷": "#8BA9BF", "高负荷": "#C65A4A"}
    load_styles = {"低负荷": "-", "高负荷": "--"}
    # a: all people completion process, with line style encoding load and color encoding protocol.
    ax = axes[0, 0]
    for load, methods in frames.items():
        for label, d in methods.items():
            x, y = ecdf(d["exit time(s)"].to_numpy())
            ax.plot(x, y * 100, color=METHODS[label]["color"], linestyle=load_styles[load], linewidth=1.5, alpha=0.92)
    ax.axhline(95, color="#8B9095", lw=.7, ls=(0,(2,2)))
    ax.set_xlim(0, 1500); ax.set_ylim(0, 101); ax.xaxis.set_major_locator(MultipleLocator(300)); ax.yaxis.set_major_locator(MultipleLocator(20))
    ax.set_xlabel("完成时间（s）"); ax.set_ylabel("累计完成比例（%）")
    panel(ax, "a", "负荷分层的疏散完成过程"); clean(ax)

    # b: quantile profile; this is the main evidence for tail ordering.
    ax = axes[0, 1]
    probabilities = np.r_[np.arange(.05, 1.0, .05), [.99, 1.0]]
    for load, methods in frames.items():
        for label, d in methods.items():
            q = np.quantile(d["exit time(s)"].to_numpy(), probabilities, method="linear")
            ax.plot(probabilities * 100, q, color=METHODS[label]["color"], linestyle=load_styles[load], linewidth=1.45)
    ax.set_xlim(5, 100); ax.set_ylim(0, 1510); ax.xaxis.set_major_locator(MultipleLocator(20)); ax.yaxis.set_major_locator(MultipleLocator(300))
    ax.set_xlabel("乘客完成时间分位数（%）"); ax.set_ylabel("完成时间（s）")
    panel(ax, "b", "完成时间分位剖面"); clean(ax)

    # c: scenario-level mean-to-tail comparison across load and protocol.
    ax = axes[1, 0]
    for load, methods in frames.items():
        for label, d in methods.items():
            mean = float(d["exit time(s)"].mean())
            t100 = float(d["exit time(s)"].max())
            ax.plot([mean, t100], [0, 1], color=METHODS[label]["color"], linestyle=load_styles[load], linewidth=1.5, marker="o", markersize=3.2)
    ax.set_xlim(0, 1500); ax.set_ylim(-0.1, 1.1)
    ax.set_yticks([0, 1], ["平均完成时间", "T100"])
    ax.xaxis.set_major_locator(MultipleLocator(300))
    ax.set_xlabel("完成时间（s）")
    panel(ax, "c", "平均值与最终清空时间"); clean(ax)

    # d: congestion exposure tail, all protocols/load combinations.
    ax = axes[1, 1]
    for load, methods in frames.items():
        for label, d in methods.items():
            x, y = ccdf(d["congestion time total(s)"].to_numpy())
            ax.plot(x, y * 100, color=METHODS[label]["color"], linestyle=load_styles[load], linewidth=1.4)
    ax.set_yscale("log"); ax.set_xlim(0, 1450); ax.set_ylim(.1, 110); ax.xaxis.set_major_locator(MultipleLocator(300)); ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
    ax.set_xlabel("累计拥堵暴露时间（s）"); ax.set_ylabel("暴露时间不低于横轴值的乘客比例（%）")
    panel(ax, "d", "拥堵暴露尾部的负荷分层"); clean(ax)

    handles = [Line2D([0], [0], color=METHODS[l]["color"], lw=2, label=l) for l in METHODS]
    handles += [Line2D([0], [0], color="#454A4F", lw=1.5, linestyle="-", label="低负荷"), Line2D([0], [0], color="#454A4F", lw=1.5, linestyle="--", label="高负荷")]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.53, .985), ncol=5, frameon=False, fontsize=7.1, handlelength=2.4, columnspacing=1.3)
    base = OUT / "fig_load_stratified_pathfinder_cn"
    fig.savefig(base.with_suffix(".png"), dpi=320, facecolor="white")
    fig.savefig(base.with_suffix(".tiff"), dpi=600, facecolor="white", pil_kwargs={"compression": "tiff_lzw"})
    fig.savefig(base.with_suffix(".pdf"), facecolor="white")
    fig.savefig(base.with_suffix(".svg"), facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
