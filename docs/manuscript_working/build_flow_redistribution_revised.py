from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "outputs" / "algorithm_compare" / "mode4_20260808_173528"
SRC = RUN / "charts" / "compiled_exit_source_by_line.csv"
OUT = Path(__file__).resolve().parent / "figures_revised"
OUT.mkdir(parents=True, exist_ok=True)

BLUE = "#4F7FA5"
RED = "#C85B4E"
INK = "#282D31"
MID = "#6B7277"


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


def pretty_exit(name: str) -> str:
    return (
        name.replace("Exit_", "")
        .replace("L2_", "2-")
        .replace("L7_", "7-")
        .replace("L16_", "16-")
        .replace("L18_", "18-")
        .replace("Maglev_", "磁-")
        .replace("_east", "东")
        .replace("_west", "西")
    )


def main() -> None:
    configure()
    df = pd.read_csv(SRC)
    line_order = ["L2", "L7", "L16", "L18", "Maglev"]
    exits = sorted(df["exit_name"].unique(), key=lambda x: (x.split("_")[1], x))
    mats = {}
    for method in ["Improved", "AA"]:
        p = df.loc[df["method"] == method].pivot_table(index="line", columns="exit_name", values="people", aggfunc="sum", fill_value=0)
        mats[method] = p.reindex(index=line_order, columns=exits, fill_value=0)
    delta = mats["AA"] - mats["Improved"]

    fig = plt.figure(figsize=(183 / 25.4, 104 / 25.4))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.55, 1.0], left=0.09, right=0.98, bottom=0.25, top=0.88, wspace=0.28)
    ax = fig.add_subplot(gs[0, 0])
    bx = fig.add_subplot(gs[0, 1])

    limit = float(np.abs(delta.to_numpy()).max())
    cmap = mpl.colors.LinearSegmentedColormap.from_list("delta", [BLUE, "#F7F8F8", RED])
    norm = TwoSlopeNorm(vmin=-limit, vcenter=0, vmax=limit)
    im = ax.imshow(delta.to_numpy(), cmap=cmap, norm=norm, aspect="auto")
    ax.set_xticks(np.arange(len(exits)), [pretty_exit(x) for x in exits], rotation=50, ha="right", rotation_mode="anchor")
    ax.set_yticks(np.arange(len(line_order)), ["2号线", "7号线", "16号线", "18号线", "磁浮"])
    ax.tick_params(length=0, labelsize=6.7)
    for i in range(delta.shape[0]):
        for j in range(delta.shape[1]):
            val = int(delta.iloc[i, j])
            if val == 0:
                continue
            color = "white" if abs(val) > 0.42 * limit else INK
            ax.text(j, i, f"{val:+d}", ha="center", va="center", fontsize=5.9, color=color, fontweight="bold" if abs(val) > 200 else "normal")
    ax.set_xticks(np.arange(-0.5, len(exits), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(line_order), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.1)
    ax.tick_params(which="minor", bottom=False, left=False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.text(-0.16, 1.12, "a", transform=ax.transAxes, fontsize=10.5, fontweight="bold")
    ax.text(-0.03, 1.12, "AA* 相对 Improved A* 的来源—出口人数变化", transform=ax.transAxes, fontsize=9.0, fontweight="bold", color=INK)
    cax = fig.add_axes([0.16, 0.08, 0.38, 0.021])
    cbar = fig.colorbar(im, cax=cax, orientation="horizontal")
    cbar.set_label("人数变化：蓝色为减少，红色为增加", fontsize=6.8)
    cbar.ax.tick_params(labelsize=6.5, length=2)
    cbar.outline.set_visible(False)

    # b: show where the largest reallocations occur without repeating all matrix cells
    long = delta.stack().reset_index()
    long.columns = ["line", "exit_name", "change"]
    long = long.loc[long["change"] != 0].copy()
    long["label"] = long["line"].map({"L2": "2号线", "L7": "7号线", "L16": "16号线", "L18": "18号线", "Maglev": "磁浮"}) + " → " + long["exit_name"].map(pretty_exit)
    strongest = long.reindex(long["change"].abs().sort_values(ascending=False).index).head(9).sort_values("change")
    y = np.arange(len(strongest))
    colors = np.where(strongest["change"] >= 0, RED, BLUE)
    bx.axvline(0, color="#959CA1", linewidth=0.8)
    bx.hlines(y, 0, strongest["change"], color=colors, linewidth=1.7)
    bx.scatter(strongest["change"], y, color=colors, s=34, edgecolor="white", linewidth=0.7, zorder=3)
    bx.set_yticks(y, strongest["label"])
    bx.set_xlabel("分配人数变化")
    span = max(abs(strongest["change"].min()), abs(strongest["change"].max()))
    bx.set_xlim(-1.18 * span, 1.18 * span)
    bx.tick_params(labelsize=6.7)
    bx.tick_params(axis="y", length=0)
    bx.grid(axis="x", color="#DDE1E4", linewidth=0.55)
    bx.spines[["top", "right", "left"]].set_visible(False)
    bx.spines["bottom"].set_color("#858C91")
    bx.text(-0.20, 1.12, "b", transform=bx.transAxes, fontsize=10.5, fontweight="bold")
    bx.text(-0.07, 1.12, "最大重分配流向", transform=bx.transAxes, fontsize=9.0, fontweight="bold", color=INK)
    bx.text(0.02, -0.19, "同一来源线路总人数守恒；变化反映出口路径重新组织。", transform=bx.transAxes, fontsize=6.6, color=MID)

    delta.to_csv(OUT / "fig_flow_redistribution_revised_cn_source.csv", encoding="utf-8-sig")
    strongest.to_csv(OUT / "fig_flow_redistribution_revised_cn_top_changes.csv", index=False, encoding="utf-8-sig")
    base = OUT / "fig_flow_redistribution_revised_cn"
    fig.savefig(base.with_suffix(".png"), dpi=320, facecolor="white")
    fig.savefig(base.with_suffix(".tiff"), dpi=600, facecolor="white", pil_kwargs={"compression": "tiff_lzw"})
    fig.savefig(base.with_suffix(".pdf"), facecolor="white")
    fig.savefig(base.with_suffix(".svg"), facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
