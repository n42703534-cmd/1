from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import PowerNorm
from matplotlib.patches import FancyBboxPatch
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "figures_revised"
OUT.mkdir(parents=True, exist_ok=True)

RUN_A = ROOT / "outputs" / "ablation" / "mode4_20260813_130743" / "ablation_results.csv"
RUN_B = ROOT / "outputs" / "ablation" / "mode4_20260813_141134" / "ablation_results.csv"

INK = "#272C30"
MID = "#6B7277"
GRID = "#D9DEE2"
BLUE = "#3977A6"
RED = "#C5534C"
ORANGE = "#D49345"
GREEN = "#5A8E75"
PURPLE = "#8172A6"


def configure() -> None:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Microsoft YaHei", "Noto Sans CJK SC", "Arial", "DejaVu Sans"],
            "font.size": 8,
            "axes.labelcolor": INK,
            "xtick.color": MID,
            "ytick.color": MID,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }
    )


def load() -> tuple[pd.Series, pd.DataFrame]:
    a = pd.read_csv(RUN_A)
    b = pd.read_csv(RUN_B)
    full = a.loc[a["variant"] == "Full AA*"].iloc[0]
    variants = pd.concat([a.loc[a["variant"] != "Full AA*"], b], ignore_index=True)
    order = [
        "No resource-queue waiting cost",
        "No arrival-time queue prediction",
        "No density-risk penalty",
        "Single-label search",
        "No spatial receiving wait",
    ]
    variants = variants.set_index("variant").loc[order].reset_index()
    return full, variants


def deterioration(full: pd.Series, variants: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ("T50", "T50_s", "higher"),
        ("T95", "T95_s", "higher"),
        ("T100", "T100_s", "higher"),
        ("平均时间", "mean_total_evacuation_time_s", "higher"),
        ("静止暴露", "stationary_person_s", "higher"),
        ("出口 Jain", "exit_load_jain", "lower"),
        ("设施 Jain", "key_facility_load_jain", "lower"),
    ]
    out = pd.DataFrame(index=variants["variant"])
    for label, col, direction in specs:
        f = float(full[col])
        v = variants[col].astype(float).to_numpy()
        if direction == "higher":
            out[label] = 100 * (v / f - 1)
        else:
            out[label] = 100 * (1 - v / f)
    return out


def main() -> None:
    configure()
    full, variants = load()
    effects = deterioration(full, variants)

    label_map = {
        "No resource-queue waiting cost": "去除资源队列等待代价",
        "No arrival-time queue prediction": "去除到达时刻队列预测",
        "No density-risk penalty": "去除密度暴露代价",
        "Single-label search": "单标签搜索",
        "No spatial receiving wait": "去除空间接纳等待",
    }
    row_labels = [label_map[x] for x in effects.index]

    fig = plt.figure(figsize=(183 / 25.4, 123 / 25.4))
    gs = fig.add_gridspec(
        1,
        2,
        width_ratios=[1.62, 1.0],
        left=0.18,
        right=0.98,
        bottom=0.29,
        top=0.90,
        wspace=0.34,
    )
    ax = fig.add_subplot(gs[0, 0])
    bx = fig.add_subplot(gs[0, 1])

    # a: outcome deterioration relative to the complete method
    values = np.clip(effects.to_numpy(), 0, None)
    cmap = mpl.colors.LinearSegmentedColormap.from_list(
        "paper_red", ["#F7F8F8", "#F1D4CF", "#D9867C", "#A93C39"]
    )
    norm = PowerNorm(gamma=0.52, vmin=0, vmax=max(200, float(values.max())))
    im = ax.imshow(values, cmap=cmap, norm=norm, aspect="auto")
    ax.set_xticks(np.arange(effects.shape[1]), effects.columns, rotation=31, ha="right", rotation_mode="anchor")
    ax.set_yticks(np.arange(effects.shape[0]), row_labels)
    ax.tick_params(length=0, labelsize=7.2)
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            raw = effects.iloc[i, j]
            color = "white" if values[i, j] >= 75 else INK
            txt = "0" if abs(raw) < 0.05 else f"{raw:+.1f}"
            ax.text(j, i, txt, ha="center", va="center", color=color, fontsize=7.0, fontweight="bold" if abs(raw) >= 10 else "normal")
    ax.set_xticks(np.arange(-0.5, effects.shape[1], 1), minor=True)
    ax.set_yticks(np.arange(-0.5, effects.shape[0], 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.5)
    ax.tick_params(which="minor", bottom=False, left=False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.text(-0.30, 1.075, "a", transform=ax.transAxes, fontsize=10.5, fontweight="bold", color="black")
    ax.text(-0.20, 1.075, "相对完整 AA* 的结果退化（%）", transform=ax.transAxes, fontsize=9.0, fontweight="bold", color=INK)
    cax = fig.add_axes([0.18, 0.065, 0.39, 0.020])
    cbar = fig.colorbar(im, cax=cax, orientation="horizontal")
    cbar.set_ticks([0, 25, 50, 100, 200])
    cbar.set_label("0 表示汇总结果不变；数值越大，去除该模块后的表现越差", fontsize=6.8, labelpad=3)
    cbar.ax.tick_params(labelsize=6.6, length=2)
    cbar.outline.set_visible(False)

    # b: tail clearance versus computational cost
    names = list(variants["variant"])
    runtime = 100 * (variants["wall_clock_s"].astype(float).to_numpy() / float(full["wall_clock_s"]) - 1)
    tail = 100 * (variants["T100_s"].astype(float).to_numpy() / float(full["T100_s"]) - 1)
    colors = [RED, ORANGE, GREEN, PURPLE, BLUE]
    bx.axvline(0, color="#B7BDC1", linewidth=0.8, zorder=0)
    bx.axhline(0, color="#B7BDC1", linewidth=0.8, zorder=0)
    bx.scatter(runtime, tail, s=44, c=colors, edgecolors="white", linewidths=0.9, zorder=3)
    label_xy = {
        names[0]: (97, 166),
        names[1]: (-6, 26),
        names[2]: (11, 12),
        names[3]: (-8, -9),
        names[4]: (24, -8),
    }
    short = {
        names[0]: "无资源队列等待",
        names[1]: "无到达时刻预测",
        names[2]: "无密度项",
        names[3]: "单标签",
        names[4]: "无空间接纳等待",
    }
    for x, y, name, color in zip(runtime, tail, names, colors):
        tx, ty = label_xy[name]
        bx.annotate(
            short[name],
            (x, y),
            xytext=(tx, ty),
            textcoords="data",
            ha="right" if name == names[0] else "left",
            va="bottom",
            fontsize=6.8,
            color=color,
            arrowprops=dict(arrowstyle="-", color=color, lw=0.6, shrinkA=1, shrinkB=4),
        )
    bx.set_xlim(-18, 115)
    bx.set_ylim(-15, 198)
    bx.set_xlabel("仿真运行时间变化（%）", fontsize=7.5)
    bx.set_ylabel(r"$T_{100}$ 变化（%）", fontsize=7.5)
    bx.set_xticks([-10, 0, 25, 50, 75, 100])
    bx.set_yticks([0, 50, 100, 150])
    bx.grid(axis="both", color=GRID, linewidth=0.55, alpha=0.8)
    bx.spines[["top", "right"]].set_visible(False)
    bx.spines[["left", "bottom"]].set_color("#8A9196")
    bx.text(-0.20, 1.075, "b", transform=bx.transAxes, fontsize=10.5, fontweight="bold", color="black")
    bx.text(-0.07, 1.075, "尾部清空与运行代价", transform=bx.transAxes, fontsize=9.0, fontweight="bold", color=INK)
    bx.add_patch(
        FancyBboxPatch(
            (0.04, 0.78),
            0.54,
            0.14,
            transform=bx.transAxes,
            boxstyle="round,pad=0.02,rounding_size=0.015",
            facecolor="white",
            edgecolor="#D0D5D8",
            linewidth=0.7,
            zorder=1,
        )
    )
    bx.text(0.075, 0.875, "← 计算更省", transform=bx.transAxes, fontsize=6.6, color=MID, zorder=2)
    bx.text(0.075, 0.815, "↑ 尾部清空更差", transform=bx.transAxes, fontsize=6.6, color=MID, zorder=2)

    source = effects.copy()
    source.insert(0, "variant_cn", row_labels)
    source["runtime_change_pct"] = runtime
    source["T100_change_pct"] = tail
    source.to_csv(OUT / "fig_ablation_revised_cn_source.csv", encoding="utf-8-sig", index=True)

    base = OUT / "fig_ablation_revised_cn"
    fig.savefig(base.with_suffix(".png"), dpi=320, facecolor="white")
    fig.savefig(base.with_suffix(".tiff"), dpi=600, facecolor="white", pil_kwargs={"compression": "tiff_lzw"})
    fig.savefig(base.with_suffix(".pdf"), facecolor="white")
    fig.savefig(base.with_suffix(".svg"), facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
