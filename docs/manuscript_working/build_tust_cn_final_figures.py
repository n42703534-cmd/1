from __future__ import annotations

from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch


ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
OUT = WORK / "figures_tust_cn_final"
OUT.mkdir(exist_ok=True)

BLUE = "#477EA8"
BLUE_L = "#9DBCD2"
RED = "#C95D4D"
RED_L = "#E6AAA0"
GREEN = "#5E9279"
ORANGE = "#C78E45"
PURPLE = "#8E6BAE"
INK = "#1F2933"
GREY = "#6B7280"
GRID = "#D9DEE3"

plt.rcParams.update({
    "font.family": "Microsoft YaHei",
    "axes.unicode_minus": False,
    "font.size": 10,
    "axes.titlesize": 13,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.dpi": 160,
    "savefig.dpi": 300,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def save(fig, name: str):
    fig.savefig(OUT / f"{name}.png", bbox_inches="tight", facecolor="white")
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight", facecolor="white")
    fig.savefig(OUT / f"{name}.svg", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def copy_existing(src_name: str, out_name: str):
    src = WORK / "figures_revised" / src_name
    shutil.copy2(src, OUT / out_name)


def figure_2_mechanism():
    fig = plt.figure(figsize=(12.8, 7.2))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    def box(x, y, w, h, title, lines, color):
        patch = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.02",
                               linewidth=1.5, edgecolor=color, facecolor="white")
        ax.add_patch(patch)
        ax.add_patch(plt.Rectangle((x, y+h-0.012), w, 0.012, color=color, clip_on=False))
        ax.text(x+0.018, y+h-0.045, title, ha="left", va="top", fontsize=13,
                fontweight="bold", color=INK)
        for i, line in enumerate(lines):
            ax.text(x+0.018, y+h-0.085-0.035*i, line, ha="left", va="top", fontsize=10,
                    color=INK)

    ax.text(0.03, 0.95, "a  三类状态：物理状态、已接受承诺与规划意图", fontsize=14,
            fontweight="bold", color=INK)
    box(0.04, 0.66, 0.26, 0.20, "物理状态", ["乘客当前位于节点或边", "真实队列由执行器推进"], BLUE)
    box(0.37, 0.66, 0.26, 0.20, "已接受承诺", ["整数批次已确定路线", "未来到达事件写回资源索引"], ORANGE)
    box(0.70, 0.66, 0.26, 0.20, "规划意图", ["候选路径暂不占用物理空间", "未接受批次不进入真实队列"], GREEN)
    ax.add_patch(FancyArrowPatch((0.30, 0.76), (0.37, 0.76), arrowstyle="-|>", mutation_scale=14,
                                 linewidth=1.5, color=GREY))
    ax.add_patch(FancyArrowPatch((0.63, 0.76), (0.70, 0.76), arrowstyle="-|>", mutation_scale=14,
                                 linewidth=1.5, color=GREY))

    ax.text(0.03, 0.58, "b  队列事件推进的数值例子", fontsize=14, fontweight="bold", color=INK)
    x0, x1 = 0.10, 0.90
    y = 0.47
    ax.plot([x0, x1], [y, y], color=GREY, linewidth=2)
    for x, label, col in [(0.14, "t₀", BLUE), (0.36, "a₁=20 s", BLUE),
                          (0.59, "a₂=35 s", BLUE), (0.82, "τ=50 s", RED)]:
        ax.plot([x, x], [y-0.035, y+0.035], color=col, linewidth=2)
        ax.text(x, y-0.065, label, ha="center", va="top", color=col, fontsize=10)
    ax.text(0.14, y+0.08, "Q(t₀)=80 人", ha="center", fontsize=10, color=INK)
    ax.text(0.36, y+0.08, "+30 人", ha="center", fontsize=10, color=BLUE)
    ax.text(0.59, y+0.08, "+20 人", ha="center", fontsize=10, color=BLUE)
    ax.text(0.82, y+0.08, "候选批次到达", ha="center", fontsize=10, color=RED)
    ax.text(0.50, 0.37, "μ=2 人/s；0–20 s 消化 40 人，Q=40；\n20 s 加入 30 人，20–35 s 再消化 30 人，Q=10；\n35 s 加入 20 人，35–50 s 消化 30 人，故 Q̂(50)=0。",
            ha="center", va="top", fontsize=10.5, color=INK, linespacing=1.45)

    ax.text(0.03, 0.25, "c  候选路径的逐段时间与目标值", fontsize=14, fontweight="bold", color=INK)
    labels = [("物理移动", "tᵐᵒᵛᵉ", BLUE), ("资源等待", "Q̂/μ", ORANGE),
              ("批次服务", "bᵣ(m)", GREEN), ("空间接纳", "sˢᵖᵃᶜᵉ", PURPLE),
              ("密度暴露", "λΔR", RED)]
    xs = np.linspace(0.06, 0.82, len(labels))
    for x, (title, formula, col) in zip(xs, labels):
        box(x, 0.07, 0.15, 0.12, title, [formula], col)
        if x < xs[-1]:
            ax.add_patch(FancyArrowPatch((x+0.15, 0.13), (x+0.18, 0.13), arrowstyle="-|>",
                                         mutation_scale=12, linewidth=1.2, color=GREY))
    ax.text(0.90, 0.13, "选择最小广义代价路径\n并回写未来事件", ha="center", va="center",
            fontsize=10, color=INK)
    save(fig, "fig2_aa_mechanism_numeric_cn")


def figure_3_workflow():
    fig, ax = plt.subplots(figsize=(12.8, 3.5))
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.02, 0.90, "图 4  网络规划—共同执行层—Pathfinder 连续空间评估", fontsize=14,
            fontweight="bold", color=INK)
    items = [
        ("需求输入", "2,187 / 17,905 人\n站内客流 + 列车到站", BLUE),
        ("网络建模", "CAD 抽象\n节点—边—资源", BLUE),
        ("批次级路径规划", "Improved A* / AA*\n路径与出口分配", RED),
        ("共同物理执行层", "速度、容量、接纳、溢回\n1 s 时间步长", ORANGE),
        ("Pathfinder 执行", "P-Improved / P-AA\nGoto Any Exit", GREEN),
        ("指标评价", "平均、T95/T100\n等待、距离、Jain", PURPLE),
    ]
    y, w, h = 0.40, 0.135, 0.27
    xs = [0.02, 0.185, 0.35, 0.515, 0.68, 0.845]
    for i, (title, lines, col) in enumerate(items):
        patch = FancyBboxPatch((xs[i], y), w, h, boxstyle="round,pad=0.012,rounding_size=0.018",
                               linewidth=1.5, edgecolor=col, facecolor="white")
        ax.add_patch(patch)
        ax.add_patch(plt.Rectangle((xs[i], y+h-0.012), w, 0.012, color=col, clip_on=False))
        ax.text(xs[i]+w/2, y+h-0.045, title, ha="center", va="top", fontweight="bold", color=INK)
        ax.text(xs[i]+w/2, y+0.105, lines, ha="center", va="center", fontsize=9.2, color=INK,
                linespacing=1.35)
        if i < len(items)-1:
            ax.add_patch(FancyArrowPatch((xs[i]+w+0.007, y+h/2), (xs[i+1]-0.007, y+h/2),
                                         arrowstyle="-|>", mutation_scale=14, linewidth=1.5, color=GREY))
    ax.text(0.50, 0.15, "网络层比较用于识别路径机制；Pathfinder 用于评估连续空间中的方向一致性，不作为网络模型的真实值。",
            ha="center", va="center", fontsize=10, color=GREY)
    save(fig, "fig3_workflow_cn")


def figure_4_network():
    df = pd.read_csv(WORK / "figures_revised" / "fig_load_stratified_network_cn_source.csv")
    fig, axes = plt.subplots(2, 4, figsize=(13.0, 6.3), constrained_layout=True)
    metrics = [
        ("mean", "平均完成时间 (s)"), ("T95", "T95 (s)"), ("T100", "T100 (s)"),
        ("stationary_s", "累计静止暴露 (人·s)"), ("distance_m", "总移动距离 (m)"),
        ("runtime_s", "墙钟运行时间 (s)"), ("jain_exit", "出口 Jain 指数"),
        ("jain_facility", "关键设施 Jain 指数"),
    ]
    df["jain_exit"] = [0.590344, 0.577066, 0.625575, 0.710769]
    df["jain_facility"] = [0.116507, 0.166175, 0.161981, 0.408838]
    for idx, (metric, ylabel) in enumerate(metrics):
        ax = axes.flat[idx]
        load = "低负荷" if idx < 4 else "高负荷"
        subdf = df[df["load"] == load]
        x = np.array([0, 1])
        vals_plot = [float(subdf.loc[subdf["method"] == m, metric].iloc[0]) for m in ["Improved A*", "AA*"]]
        labels = ["Improved A*", "AA*"]
        colors = [BLUE, RED]
        title = f"{load}（{2_187 if load == '低负荷' else 17_905:,} 人）"
        bars = ax.bar(x, vals_plot, width=0.56, color=colors, edgecolor="white", linewidth=0.8)
        ax.set_xticks(x, labels, rotation=18)
        ax.set_title(title, loc="left", fontsize=11, fontweight="bold")
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for b, value in zip(bars, vals_plot):
            if metric in {"stationary_s", "distance_m"}:
                text = f"{value:,.0f}"
            elif metric in {"jain_exit", "jain_facility"}:
                text = f"{value:.3f}"
            elif metric == "runtime_s":
                text = f"{value:.1f}"
            else:
                text = f"{value:.1f}"
            ax.text(b.get_x()+b.get_width()/2, b.get_height(), text, ha="center", va="bottom", fontsize=8)
    fig.suptitle("图 5  两种负荷下的网络层结果（分面柱状图）", x=0.02, ha="left", fontsize=15, fontweight="bold")
    save(fig, "fig4_network_load_stratified_cn")


def read_queue(path: Path):
    df = pd.read_csv(path)
    df["sim_time_seconds"] = pd.to_numeric(df["sim_time_seconds"])
    df["gate_routing_queue_people"] = pd.to_numeric(df["gate_routing_queue_people"])
    return df


def figure_5_bottleneck():
    base = ROOT / "outputs" / "algorithm_compare"
    hi_i = read_queue(base / "mode4_20260808_173528" / "ImprovedAStar" / "gate_backlog_step_trace.csv")
    hi_a = read_queue(base / "mode4_20260808_173528" / "AdaptiveQueueAwareAStar" / "gate_backlog_step_trace.csv")
    lo_i = read_queue(base / "mode1_20260812_231621" / "ImprovedAStar" / "gate_backlog_step_trace.csv")
    lo_a = read_queue(base / "mode1_20260812_231621" / "AdaptiveQueueAwareAStar" / "gate_backlog_step_trace.csv")
    hi_i_agg = hi_i.groupby("sim_time_seconds")["gate_routing_queue_people"].sum()
    hi_a_agg = hi_a.groupby("sim_time_seconds")["gate_routing_queue_people"].sum()
    lo_i_agg = lo_i.groupby("sim_time_seconds")["gate_routing_queue_people"].sum()
    lo_a_agg = lo_a.groupby("sim_time_seconds")["gate_routing_queue_people"].sum()
    gates = sorted(set(hi_i["gate"]) | set(hi_a["gate"]))
    maxq = (hi_i.groupby("gate")["gate_routing_queue_people"].max().add(
        hi_a.groupby("gate")["gate_routing_queue_people"].max(), fill_value=0))
    gates = list(maxq.sort_values(ascending=False).head(8).index)
    pivot_i = hi_i[hi_i["gate"].isin(gates)].pivot(index="gate", columns="sim_time_seconds", values="gate_routing_queue_people").fillna(0)
    pivot_a = hi_a[hi_a["gate"].isin(gates)].pivot(index="gate", columns="sim_time_seconds", values="gate_routing_queue_people").fillna(0)
    common_t = sorted(set(pivot_i.columns) & set(pivot_a.columns))
    diff = pivot_a[common_t] - pivot_i[common_t]
    # Use 20 s bins to keep the mechanism panel readable while preserving the raw time series.
    bins = np.arange(0, max(common_t)+20, 20)
    binned = pd.DataFrame(index=diff.index)
    for left, right in zip(bins[:-1], bins[1:]):
        cols = [c for c in common_t if left <= c < right]
        binned[f"{left:.0f}"] = diff[cols].mean(axis=1) if cols else 0

    lc = pd.read_csv(base / "mode4_20260808_173528" / "AdaptiveQueueAwareAStar" / "line_clearance.csv")
    # line_clearance files contain both methods in separate runs only; use the saved summary rows from the two folders.
    lc_i = pd.read_csv(base / "mode4_20260808_173528" / "ImprovedAStar" / "line_clearance.csv")
    lc_a = pd.read_csv(base / "mode4_20260808_173528" / "AdaptiveQueueAwareAStar" / "line_clearance.csv")
    line_col = "line" if "line" in lc_i.columns else lc_i.columns[0]
    clear_col = "clearance_time" if "clearance_time" in lc_i.columns else [c for c in lc_i.columns if "clear" in c.lower()][0]
    fig, axes = plt.subplots(2, 2, figsize=(12.8, 7.2), constrained_layout=True)
    ax = axes[0, 0]
    ax.plot(hi_i_agg.index, hi_i_agg.values, color=BLUE, lw=2.2, label="Improved A*")
    ax.plot(hi_a_agg.index, hi_a_agg.values, color=RED, lw=2.2, label="AA*")
    ax.set_title("a  高负荷聚合闸机队列", loc="left", fontweight="bold")
    ax.set_xlabel("时间 (s)"); ax.set_ylabel("闸机路由队列 (人)"); ax.legend(frameon=False)
    ax.grid(color=GRID, linewidth=0.8); ax.set_axisbelow(True)
    ax = axes[0, 1]
    ax.plot(lo_i_agg.index, lo_i_agg.values, color=BLUE, lw=2.2, label="Improved A*")
    ax.plot(lo_a_agg.index, lo_a_agg.values, color=RED, lw=2.2, label="AA*")
    ax.set_title("b  低负荷聚合闸机队列", loc="left", fontweight="bold")
    ax.set_xlabel("时间 (s)"); ax.set_ylabel("闸机路由队列 (人)")
    ax.grid(color=GRID, linewidth=0.8); ax.set_axisbelow(True)
    ax = axes[1, 0]
    im = ax.imshow(binned.values, aspect="auto", cmap="RdBu_r", norm=TwoSlopeNorm(vcenter=0),
                   extent=[-0.5, binned.shape[1]-0.5, -0.5, binned.shape[0]-0.5])
    ax.set_yticks(np.arange(len(binned.index)), [str(x).replace("Gate_", "") for x in binned.index], fontsize=8)
    ax.set_xticks(np.arange(0, binned.shape[1], max(1, binned.shape[1]//6)))
    ax.set_xticklabels([list(binned.columns)[i] for i in ax.get_xticks().astype(int)])
    ax.set_title("c  高负荷 AA*−Improved A* 闸机队列差值", loc="left", fontweight="bold")
    ax.set_xlabel("时间分箱起点 (s)"); ax.set_ylabel("闸机")
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04); cb.set_label("队列差值 (人)")
    ax = axes[1, 1]
    lines = sorted(set(lc_i[line_col].astype(str)) | set(lc_a[line_col].astype(str)))
    y = np.arange(len(lines))
    vi = [float(lc_i.loc[lc_i[line_col].astype(str) == line, clear_col].iloc[0]) for line in lines]
    va = [float(lc_a.loc[lc_a[line_col].astype(str) == line, clear_col].iloc[0]) for line in lines]
    ax.barh(y+0.18, vi, height=0.32, color=BLUE, label="Improved A*")
    ax.barh(y-0.18, va, height=0.32, color=RED, label="AA*")
    ax.set_yticks(y, lines); ax.invert_yaxis(); ax.set_xlabel("线路清空时间 (s)")
    ax.set_title("d  高负荷线路清空时间", loc="left", fontweight="bold")
    ax.legend(frameon=False); ax.grid(axis="x", color=GRID, linewidth=0.8); ax.set_axisbelow(True)
    fig.suptitle("图 6  共享闸机瓶颈的时序证据", x=0.02, ha="left", fontsize=15, fontweight="bold")
    save(fig, "fig5_shared_bottleneck_timeseries_cn")


def main():
    copy_existing("fig_station_spatial_structure_cn.png", "fig1_station_structure_cn.png")
    figure_2_mechanism()
    figure_3_workflow()
    figure_4_network()
    figure_5_bottleneck()
    copy_existing("fig_ablation_revised_cn.png", "fig6_ablation_cn.png")
    copy_existing("fig_load_stratified_pathfinder_cn.png", "fig7_pathfinder_load_stratified_cn.png")
    print(OUT)


if __name__ == "__main__":
    main()
