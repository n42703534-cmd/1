from __future__ import annotations

import csv
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, MultipleLocator


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "龙阳路" / "高负荷"
OUT = ROOT / "docs" / "manuscript_working" / "figures_revised"
OUT.mkdir(parents=True, exist_ok=True)

METHODS = {
    "Improved A*": {
        "path": RAW / "龙阳路improved高负荷 _occupants.csv",
        "color": "#547FA3",
        "linestyle": (0, (5.0, 2.2)),
    },
    "AA*": {
        "path": RAW / "龙阳路AA高负荷 _occupants.csv",
        "color": "#C65A4A",
        "linestyle": "-",
    },
    "Pathfinder Goto Any Exit": {
        "path": RAW / "any exit（test）_occupants.csv",
        "color": "#30353B",
        "linestyle": (0, (1.2, 1.5)),
    },
}


def set_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [
                "Microsoft YaHei",
                "Noto Sans CJK SC",
                "Arial Unicode MS",
                "DejaVu Sans",
            ],
            "font.size": 8.2,
            "axes.labelsize": 8.6,
            "axes.titlesize": 9.0,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "legend.fontsize": 7.8,
            "axes.linewidth": 0.75,
            "xtick.major.width": 0.65,
            "ytick.major.width": 0.65,
            "xtick.major.size": 3.0,
            "ytick.major.size": 3.0,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "savefig.transparent": False,
        }
    )


def read_frames() -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for label, spec in METHODS.items():
        frame = pd.read_csv(spec["path"], encoding="utf-8-sig", low_memory=False)
        for column in (
            "exit time(s)",
            "congestion time total(s)",
            "distance (m)",
        ):
            frame[column] = pd.to_numeric(frame[column], errors="raise")
        frames[label] = frame
    return frames


def ecdf(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = np.sort(values.astype(float))
    y = np.arange(1, x.size + 1, dtype=float) / x.size
    return x, y


def ccdf(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = np.sort(values.astype(float))
    y = (x.size - np.arange(x.size, dtype=float)) / x.size
    return x, y


def clean_axis(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color="#D6D9DC", linewidth=0.45, alpha=0.6)
    ax.set_axisbelow(True)


def panel_label(ax: plt.Axes, label: str) -> None:
    ax.text(
        -0.13,
        1.055,
        label,
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=10.5,
        fontweight="bold",
        color="#111111",
    )


def export_source(frames: dict[str, pd.DataFrame]) -> None:
    with (OUT / "fig_pathfinder_high_load_revised_source.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "method",
                "occupant_name",
                "exit_time_s",
                "congestion_time_total_s",
                "distance_m",
            ]
        )
        for label, frame in frames.items():
            for row in frame.itertuples(index=False):
                writer.writerow(
                    [
                        label,
                        getattr(row, "name"),
                        getattr(row, "_2"),
                        getattr(row, "_4"),
                        getattr(row, "_12"),
                    ]
                )


def build() -> None:
    set_style()
    frames = read_frames()

    width_in = 183 / 25.4
    height_in = 150 / 25.4
    fig, axes = plt.subplots(2, 2, figsize=(width_in, height_in))
    fig.subplots_adjust(left=0.105, right=0.985, bottom=0.105, top=0.895, wspace=0.30, hspace=0.43)

    # a: complete evacuation process
    ax = axes[0, 0]
    for label, frame in frames.items():
        x, y = ecdf(frame["exit time(s)"].to_numpy())
        spec = METHODS[label]
        ax.plot(x, y * 100, color=spec["color"], linestyle=spec["linestyle"], linewidth=1.75)
    ax.axhline(95, color="#8B9095", linewidth=0.7, linestyle=(0, (2, 2)))
    ax.text(27, 96.2, "$T_{95}$", color="#666A6E", fontsize=7.5)
    ax.set_xlim(0, 1500)
    ax.set_ylim(0, 101)
    ax.xaxis.set_major_locator(MultipleLocator(300))
    ax.yaxis.set_major_locator(MultipleLocator(20))
    ax.set_xlabel("完成时间（s）")
    ax.set_ylabel("累计完成比例（%）")
    ax.set_title("疏散完成过程", loc="left", pad=6, fontweight="semibold")
    clean_axis(ax)
    panel_label(ax, "a")

    # b: quantile profile, emphasizing that the ordering changes across the distribution
    ax = axes[0, 1]
    probabilities = np.r_[np.arange(0.05, 1.0, 0.05), [0.99, 1.0]]
    for label, frame in frames.items():
        values = frame["exit time(s)"].to_numpy(dtype=float)
        q = np.quantile(values, probabilities, method="linear")
        spec = METHODS[label]
        ax.plot(
            probabilities * 100,
            q,
            color=spec["color"],
            linestyle=spec["linestyle"],
            linewidth=1.65,
        )
    ax.set_xlim(5, 100)
    ax.set_ylim(0, 1510)
    ax.xaxis.set_major_locator(MultipleLocator(20))
    ax.yaxis.set_major_locator(MultipleLocator(300))
    ax.set_xlabel("乘客完成时间分位数（%）")
    ax.set_ylabel("完成时间（s）")
    ax.set_title("完成时间的分位剖面", loc="left", pad=6, fontweight="semibold")
    clean_axis(ax)
    panel_label(ax, "b")

    # c: movement-distance distributions, reported at the scenario level
    ax = axes[1, 0]
    for label, frame in frames.items():
        values = np.sort(frame["distance (m)"].to_numpy(dtype=float))
        cumulative = np.arange(1, values.size + 1, dtype=float) / values.size * 100.0
        spec = METHODS[label]
        ax.plot(values, cumulative, color=spec["color"], linestyle=spec["linestyle"], linewidth=1.65, label=label)
    ax.set_xlim(0, 350)
    ax.set_ylim(0, 101)
    ax.xaxis.set_major_locator(MultipleLocator(70))
    ax.yaxis.set_major_locator(MultipleLocator(20))
    ax.set_xlabel("乘客移动距离（m）")
    ax.set_ylabel("累计乘客比例（%）")
    ax.set_title("移动距离的经验累计分布", loc="left", pad=6, fontweight="semibold")
    clean_axis(ax)
    panel_label(ax, "c")

    # d: congestion-exposure survival curves
    ax = axes[1, 1]
    for label, frame in frames.items():
        x, y = ccdf(frame["congestion time total(s)"].to_numpy())
        spec = METHODS[label]
        ax.plot(x, y * 100, color=spec["color"], linestyle=spec["linestyle"], linewidth=1.65)
    ax.set_yscale("log")
    ax.set_xlim(0, 1450)
    ax.set_ylim(0.1, 110)
    ax.xaxis.set_major_locator(MultipleLocator(300))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
    ax.set_xlabel("累计拥堵暴露时间（s）")
    ax.set_ylabel("暴露时间不低于横轴值的乘客比例（%）")
    ax.set_title("拥堵暴露的尾部分布", loc="left", pad=6, fontweight="semibold")
    clean_axis(ax)
    panel_label(ax, "d")

    handles = [
        Line2D(
            [0],
            [0],
            color=spec["color"],
            linestyle=spec["linestyle"],
            linewidth=2.0,
            label=label,
        )
        for label, spec in METHODS.items()
    ]
    fig.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.545, 0.985),
        ncol=3,
        frameon=False,
        handlelength=3.0,
        columnspacing=1.8,
    )

    base = OUT / "fig_pathfinder_high_load_revised_cn"
    fig.savefig(base.with_suffix(".png"), dpi=320, facecolor="white")
    fig.savefig(base.with_suffix(".tiff"), dpi=600, facecolor="white", pil_kwargs={"compression": "tiff_lzw"})
    fig.savefig(base.with_suffix(".pdf"), facecolor="white")
    fig.savefig(base.with_suffix(".svg"), facecolor="white")
    plt.close(fig)
    export_source(frames)


if __name__ == "__main__":
    build()
