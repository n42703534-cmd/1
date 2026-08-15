from __future__ import annotations

import math
import os
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyArrowPatch, Rectangle
from matplotlib.lines import Line2D

import network


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs" / "nature_figures_v1"
MODE1 = ROOT / "outputs" / "algorithm_compare" / "mode1_20260623_163319"
MODE4 = ROOT / "outputs" / "algorithm_compare" / "mode4_20260623_170538"
ABLATION = ROOT / "outputs" / "ablation" / "mode4_20260609_222716"
SENS = ROOT / "outputs" / "sensitivity" / "mode4_20260608_064817"

METHOD_LABELS = {
    "ImprovedAStar": "Improved A*",
    "AdaptiveQueueAwareAStar": "Adaptive",
}

COLORS = {
    "ImprovedAStar": "#4C78A8",
    "AdaptiveQueueAwareAStar": "#E45756",
    "Improved A*": "#4C78A8",
    "Adaptive": "#E45756",
    "neutral": "#4D4D4D",
    "soft": "#E8EEF7",
    "grid": "#D8D8D8",
}

LINE_COLORS = {
    "L2": "#3B82F6",
    "L7": "#F59E0B",
    "L16": "#10B981",
    "L18": "#8B5CF6",
    "Maglev": "#EF4444",
}


def setup_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "Arial",
            "font.size": 8,
            "axes.titlesize": 9,
            "axes.labelsize": 8,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "legend.fontsize": 7,
            "figure.dpi": 160,
            "savefig.dpi": 450,
            "axes.linewidth": 0.7,
            "xtick.major.width": 0.6,
            "ytick.major.width": 0.6,
            "xtick.major.size": 3,
            "ytick.major.size": 3,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )


def read_mode(path: Path, scenario: str) -> dict[str, pd.DataFrame]:
    frames = {}
    for name in [
        "summary_metrics",
        "line_clearance",
        "exit_usage",
        "exit_by_source_group",
        "facility_throughput",
        "route_chain",
        "improvement_vs_baseline",
    ]:
        frames[name] = pd.read_csv(path / f"{name}.csv")
        frames[name]["scenario"] = scenario
    return frames


def clean_method_labels(df: pd.DataFrame, cols: list[str] | None = None) -> pd.DataFrame:
    out = df.copy()
    if cols is None:
        cols = [c for c in out.columns if c in METHOD_LABELS or c in {"method", "method_label"}]
    for col in cols:
        if col in out.columns:
            out[col] = out[col].replace(METHOD_LABELS)
    return out


def panel_label(ax: plt.Axes, label: str) -> None:
    ax.text(
        -0.08,
        1.06,
        label,
        transform=ax.transAxes,
        fontsize=10,
        fontweight="bold",
        va="bottom",
        ha="left",
    )


def strip_axes(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, axis="y", color=COLORS["grid"], linewidth=0.45, alpha=0.55)
    ax.set_axisbelow(True)


def short_node_label(name: str) -> str:
    label = str(name)
    replacements = {
        "VN_": "",
        "Gate_": "G ",
        "Transfer_": "X ",
        "Escalator_": "Esc ",
        "Stair_": "St ",
        "_Entrance": " ent",
        "_Arrival": " arr",
        "_Corner_": " c",
        "_West_Vert": " W vert",
        "_East_Vert": " E vert",
        "_down": " d",
        "_up": " u",
        "_": " ",
    }
    for old, new in replacements.items():
        label = label.replace(old, new)
    label = " ".join(label.split())
    if len(label) > 20:
        label = label[:18] + "..."
    return label


def short_param_label(name: str) -> str:
    return {
        "gate_queue_weight": "gate queue",
        "source_release": "source release",
        "gate_overload_factor": "gate overload",
        "exit_pressure": "exit pressure",
        "downstream_release": "downstream",
        "service_rate_weight": "service rate",
        "service_wait_time_weight": "service wait",
        "density_severe_surcharge": "severe surcharge",
        "density_moderate_factor": "moderate factor",
    }.get(str(name), str(name).replace("_", " "))


def savefig(fig: plt.Figure, stem: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf", "svg"):
        fig.savefig(OUT / f"{stem}.{ext}", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def rescale_positions(pos: dict[str, tuple[float, float]]) -> dict[str, tuple[float, float]]:
    xs = np.array([p[0] for p in pos.values()], dtype=float)
    ys = np.array([p[1] for p in pos.values()], dtype=float)
    x_mid, y_mid = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
    scale = max(xs.max() - xs.min(), ys.max() - ys.min(), 1.0)
    return {k: ((v[0] - x_mid) / scale, (v[1] - y_mid) / scale) for k, v in pos.items()}


def draw_box(ax: plt.Axes, xy, w, h, text, fc="#F7F7F7", ec="#555555") -> None:
    rect = Rectangle(xy, w, h, facecolor=fc, edgecolor=ec, linewidth=0.8)
    ax.add_patch(rect)
    ax.text(xy[0] + w / 2, xy[1] + h / 2, text, ha="center", va="center", fontsize=7)


def arrow(ax: plt.Axes, a, b, color="#555555", rad=0.0) -> None:
    ax.add_patch(
        FancyArrowPatch(
            a,
            b,
            arrowstyle="-|>",
            mutation_scale=8,
            linewidth=0.75,
            color=color,
            connectionstyle=f"arc3,rad={rad}",
        )
    )


def figure_1(mode4: dict[str, pd.DataFrame]) -> None:
    G = network.build_graph()
    keep_types = {
        "platform",
        "platform_waiting_zone",
        "gate",
        "gate_wide",
        "stair",
        "escalator",
        "passageway",
        "virtual",
        "exit",
    }
    nodes = [
        n
        for n, d in G.nodes(data=True)
        if d.get("pos") is not None and str(d.get("type", "")).lower() in keep_types
    ]
    H = G.subgraph(nodes).copy()
    pos = rescale_positions(nx.get_node_attributes(H, "pos"))
    node_type_color = {
        "platform": "#111827",
        "platform_waiting_zone": "#9CA3AF",
        "gate": "#2563EB",
        "gate_wide": "#2563EB",
        "stair": "#059669",
        "escalator": "#059669",
        "passageway": "#6B7280",
        "virtual": "#D1D5DB",
        "exit": "#DC2626",
    }
    sizes = []
    colors = []
    for n, d in H.nodes(data=True):
        t = str(d.get("type", "")).lower()
        sizes.append(42 if t in {"platform", "exit"} else 14 if t == "virtual" else 24)
        colors.append(node_type_color.get(t, "#999999"))

    fig = plt.figure(figsize=(7.2, 5.2))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.2, 1.0], height_ratios=[1.05, 0.95], hspace=0.38, wspace=0.30)
    ax_net = fig.add_subplot(gs[:, 0])
    ax_flow = fig.add_subplot(gs[0, 1])
    ax_demand = fig.add_subplot(gs[1, 1])

    nx.draw_networkx_edges(H, pos, ax=ax_net, width=0.35, alpha=0.18, arrows=False, edge_color="#6B7280")
    nx.draw_networkx_nodes(
        H,
        pos,
        ax=ax_net,
        node_size=sizes,
        node_color=colors,
        linewidths=0.25,
        edgecolors="white",
        alpha=0.95,
    )
    important = [n for n in H.nodes if H.nodes[n].get("type") in {"platform", "exit"}]
    for n in important:
        x, y = pos[n]
        ax_net.text(x, y + 0.018, n.replace("Platform_", "").replace("Exit_", "E"), fontsize=5.2, ha="center")
    ax_net.set_title("Station evacuation network")
    ax_net.set_xticks([])
    ax_net.set_yticks([])
    for spine in ax_net.spines.values():
        spine.set_visible(False)
    panel_label(ax_net, "a")

    ax_flow.set_xlim(0, 1)
    ax_flow.set_ylim(0, 1)
    ax_flow.axis("off")
    boxes = [
        ((0.06, 0.62), 0.26, 0.18, "Network\nstate", "#EEF2FF"),
        ((0.38, 0.62), 0.26, 0.18, "Local queue\npressure", "#FEF3C7"),
        ((0.70, 0.62), 0.24, 0.18, "Exit\npressure", "#FEE2E2"),
        ((0.22, 0.28), 0.26, 0.18, "Candidate\nnext hops", "#ECFDF5"),
        ((0.58, 0.28), 0.28, 0.18, "Minimum\ncomposite cost", "#F3F4F6"),
    ]
    for xy, w, h, text, fc in boxes:
        draw_box(ax_flow, xy, w, h, text, fc=fc)
    arrow(ax_flow, (0.32, 0.71), (0.38, 0.71))
    arrow(ax_flow, (0.64, 0.71), (0.70, 0.71))
    arrow(ax_flow, (0.19, 0.62), (0.32, 0.46), rad=-0.1)
    arrow(ax_flow, (0.51, 0.62), (0.43, 0.46), rad=0.1)
    arrow(ax_flow, (0.82, 0.62), (0.71, 0.46), rad=0.1)
    arrow(ax_flow, (0.48, 0.37), (0.58, 0.37))
    ax_flow.text(
        0.50,
        0.12,
        "Cost = travel time + queue + service + downstream + exit terms",
        ha="center",
        va="center",
        fontsize=7,
        color="#333333",
    )
    ax_flow.set_title("Adaptive next-hop decision")
    panel_label(ax_flow, "b")

    demand = (
        mode4["exit_by_source_group"]
        .drop_duplicates(["source_group", "configured_people"])
        .assign(line=lambda d: d["line"].fillna("Other"))
        .groupby("line")["configured_people"]
        .sum()
        .sort_values(ascending=False)
    )
    demand = demand[[x for x in demand.index if x in LINE_COLORS] + [x for x in demand.index if x not in LINE_COLORS]]
    ax_demand.bar(
        np.arange(len(demand)),
        demand.values,
        color=[LINE_COLORS.get(x, "#9CA3AF") for x in demand.index],
        edgecolor="white",
        linewidth=0.7,
    )
    ax_demand.set_xticks(np.arange(len(demand)))
    ax_demand.set_xticklabels(demand.index)
    ax_demand.set_ylabel("Configured passengers")
    ax_demand.set_title("Demand composition, mode 4")
    strip_axes(ax_demand)
    panel_label(ax_demand, "c")

    savefig(fig, "fig1_system_and_algorithm")


def figure_2(mode1: dict[str, pd.DataFrame], mode4: dict[str, pd.DataFrame]) -> None:
    summary = pd.concat([mode1["summary_metrics"], mode4["summary_metrics"]], ignore_index=True)
    summary["method_label"] = summary["method"].replace(METHOD_LABELS)
    summary["scenario_label"] = summary["scenario"].map({"Mode 1": "Mode 1\nregular", "Mode 4": "Mode 4\nfull-train"})
    quant_cols = ["T50", "T80", "T95", "T100"]
    safety_cols = ["queueing_time", "congestion_exposure", "severe_congestion"]

    fig = plt.figure(figsize=(7.2, 6.2))
    gs = fig.add_gridspec(2, 2, hspace=0.42, wspace=0.32)
    ax_q = fig.add_subplot(gs[0, 0])
    ax_s = fig.add_subplot(gs[0, 1])
    ax_imp = fig.add_subplot(gs[1, 0])
    ax_trade = fig.add_subplot(gs[1, 1])

    x_base = np.arange(len(quant_cols))
    for i, scenario in enumerate(["Mode 1", "Mode 4"]):
        block = summary[summary["scenario"] == scenario]
        offset = -0.18 if scenario == "Mode 1" else 0.18
        for method in ["ImprovedAStar", "AdaptiveQueueAwareAStar"]:
            row = block[block["method"] == method].iloc[0]
            linestyle = "-" if method == "AdaptiveQueueAwareAStar" else "--"
            marker = "o" if method == "AdaptiveQueueAwareAStar" else "s"
            ax_q.plot(
                x_base + offset,
                [row[c] for c in quant_cols],
                marker=marker,
                linestyle=linestyle,
                linewidth=1.2,
                markersize=4,
                color=COLORS[method],
                alpha=0.95,
                label=f"{scenario}, {METHOD_LABELS[method]}",
            )
    ax_q.set_xticks(x_base)
    ax_q.set_xticklabels(quant_cols)
    ax_q.set_ylabel("Evacuation time (s)")
    ax_q.set_title("Evacuation quantiles")
    strip_axes(ax_q)
    ax_q.legend(frameon=False, loc="upper left", bbox_to_anchor=(0.0, 1.04), ncol=2, columnspacing=0.8)
    panel_label(ax_q, "a")

    safety = summary.melt(
        id_vars=["scenario", "method", "method_label"],
        value_vars=safety_cols,
        var_name="metric",
        value_name="value",
    )
    metric_labels = {
        "queueing_time": "Queueing",
        "congestion_exposure": "Moderate\nexposure",
        "severe_congestion": "Severe\nexposure",
    }
    group_positions = np.arange(len(safety_cols))
    width = 0.18
    offsets = {
        ("Mode 1", "ImprovedAStar"): -0.27,
        ("Mode 1", "AdaptiveQueueAwareAStar"): -0.09,
        ("Mode 4", "ImprovedAStar"): 0.09,
        ("Mode 4", "AdaptiveQueueAwareAStar"): 0.27,
    }
    for (scenario, method), off in offsets.items():
        vals = [
            safety[(safety["scenario"] == scenario) & (safety["method"] == method) & (safety["metric"] == m)]["value"].iloc[0]
            / 1000.0
            for m in safety_cols
        ]
        hatch = "" if scenario == "Mode 4" else "///"
        ax_s.bar(
            group_positions + off,
            vals,
            width=width,
            color=COLORS[method],
            edgecolor="white",
            linewidth=0.5,
            hatch=hatch,
            alpha=0.9,
            label=f"{scenario}, {METHOD_LABELS[method]}",
        )
    ax_s.set_yscale("symlog", linthresh=1.0)
    ax_s.set_xticks(group_positions)
    ax_s.set_xticklabels([metric_labels[m] for m in safety_cols])
    ax_s.set_ylabel("Passenger-seconds (x10^3)")
    ax_s.set_title("Safety burden")
    strip_axes(ax_s)
    panel_label(ax_s, "b")

    improvements = pd.concat([mode1["improvement_vs_baseline"], mode4["improvement_vs_baseline"]], ignore_index=True)
    improvements["metric_clean"] = improvements["metric"].str.replace(r" \(AdaptiveQueueAwareAStar\)", "", regex=True)
    order = ["T100", "QueueingTime", "CongestionExposure", "SevereCongestion"]
    label_map = {
        "T100": "T100",
        "QueueingTime": "Queueing",
        "CongestionExposure": "Moderate exposure",
        "SevereCongestion": "Severe exposure",
    }
    y = np.arange(len(order))
    for i, scenario in enumerate(["Mode 1", "Mode 4"]):
        vals = [
            improvements[(improvements["scenario"] == scenario) & (improvements["metric_clean"] == m)]["improvement_pct"].iloc[0]
            if len(improvements[(improvements["scenario"] == scenario) & (improvements["metric_clean"] == m)])
            else np.nan
            for m in order
        ]
        ax_imp.barh(y + (-0.16 if scenario == "Mode 1" else 0.16), vals, height=0.28, color="#9CA3AF" if scenario == "Mode 1" else "#111827", label=scenario)
    ax_imp.axvline(0, color="#333333", linewidth=0.7)
    ax_imp.set_yticks(y)
    ax_imp.set_yticklabels([label_map[m] for m in order])
    ax_imp.set_xlabel("Improvement vs Improved A* (%)")
    ax_imp.set_title("Relative change by scenario")
    strip_axes(ax_imp)
    ax_imp.grid(True, axis="x", color=COLORS["grid"], linewidth=0.45, alpha=0.55)
    ax_imp.legend(frameon=False, loc="lower right")
    panel_label(ax_imp, "c")

    for scenario in ["Mode 1", "Mode 4"]:
        block = summary[summary["scenario"] == scenario]
        for method in ["ImprovedAStar", "AdaptiveQueueAwareAStar"]:
            row = block[block["method"] == method].iloc[0]
            ax_trade.scatter(
                row["T100"],
                row["congestion_exposure"] / 1000.0,
                s=95 if scenario == "Mode 4" else 55,
                color=COLORS[method],
                edgecolor="white",
                linewidth=0.8,
                alpha=0.92,
            )
            if scenario == "Mode 4":
                ax_trade.annotate(
                    f"M4 {METHOD_LABELS[method]}",
                    xy=(row["T100"], row["congestion_exposure"] / 1000.0),
                    xytext=(10, 0),
                    textcoords="offset points",
                    fontsize=6.5,
                    va="center",
                )
    ax_trade.annotate(
        "Mode 1 cluster",
        xy=(321, 8),
        xytext=(24, 34),
        textcoords="offset points",
        arrowprops={"arrowstyle": "-", "linewidth": 0.6, "color": "#555555"},
        fontsize=6.5,
    )
    ax_trade.set_xlabel("T100 (s)")
    ax_trade.set_ylabel("Moderate exposure (x10^3 pax s)")
    ax_trade.set_title("Efficiency-safety trade-off")
    strip_axes(ax_trade)
    panel_label(ax_trade, "d")

    savefig(fig, "fig2_macro_performance_tradeoff")


def top_exits(exit_df: pd.DataFrame, n: int = 10) -> list[str]:
    cols = [c for c in ["ImprovedAStar", "AdaptiveQueueAwareAStar"] if c in exit_df.columns]
    ranked = exit_df.assign(total=exit_df[cols].sum(axis=1)).sort_values("total", ascending=False)
    return ranked.head(n)["exit"].tolist()


def figure_3(mode1: dict[str, pd.DataFrame], mode4: dict[str, pd.DataFrame]) -> None:
    fig = plt.figure(figsize=(8.0, 6.5))
    gs = fig.add_gridspec(2, 2, hspace=0.50, wspace=0.58)
    ax_line = fig.add_subplot(gs[0, 0])
    ax_exit = fig.add_subplot(gs[0, 1])
    ax_heat = fig.add_subplot(gs[1, 0])
    ax_fac = fig.add_subplot(gs[1, 1])

    line = pd.concat([mode1["line_clearance"], mode4["line_clearance"]], ignore_index=True)
    line_long = line.melt(id_vars=["line", "scenario"], value_vars=["ImprovedAStar", "AdaptiveQueueAwareAStar"], var_name="method", value_name="time")
    line_long["method_label"] = line_long["method"].replace(METHOD_LABELS)
    line_order = ["L16", "L18", "L2", "L7", "Maglev"]
    scenarios = ["Mode 1", "Mode 4"]
    y_positions = []
    y_labels = []
    idx = 0
    for scenario in scenarios:
        for ln in line_order:
            sub = line_long[(line_long["scenario"] == scenario) & (line_long["line"] == ln)]
            if sub.empty:
                continue
            base = sub[sub["method"] == "ImprovedAStar"]["time"].iloc[0]
            adap = sub[sub["method"] == "AdaptiveQueueAwareAStar"]["time"].iloc[0]
            ax_line.plot([base, adap], [idx, idx], color="#B8B8B8", linewidth=1.1, zorder=1)
            ax_line.scatter(base, idx, color=COLORS["ImprovedAStar"], s=26, zorder=2)
            ax_line.scatter(adap, idx, color=COLORS["AdaptiveQueueAwareAStar"], s=26, zorder=3)
            y_positions.append(idx)
            y_labels.append(f"{scenario[-1]} {ln}")
            idx += 1
    ax_line.set_yticks(y_positions)
    ax_line.set_yticklabels(y_labels)
    ax_line.set_xlabel("Line clearance time (s)")
    ax_line.set_title("Line-level clearance redistribution")
    strip_axes(ax_line)
    handles = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=COLORS["ImprovedAStar"], markeredgecolor="none", label="Improved A*"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=COLORS["AdaptiveQueueAwareAStar"], markeredgecolor="none", label="Adaptive"),
    ]
    ax_line.legend(handles=handles, frameon=False, loc="lower right")
    panel_label(ax_line, "a")

    exits = mode4["exit_usage"].copy()
    exits = exits[exits["exit"].isin(top_exits(exits, 11))]
    exits = exits.sort_values("AdaptiveQueueAwareAStar", ascending=False)
    x = np.arange(len(exits))
    ax_exit.bar(x - 0.18, exits["ImprovedAStar"], width=0.36, color=COLORS["ImprovedAStar"], label="Improved A*")
    ax_exit.bar(x + 0.18, exits["AdaptiveQueueAwareAStar"], width=0.36, color=COLORS["AdaptiveQueueAwareAStar"], label="Adaptive")
    ax_exit.set_xticks(x)
    ax_exit.set_xticklabels([e.replace("Exit_", "") for e in exits["exit"]], rotation=50, ha="right")
    ax_exit.set_ylabel("Passengers")
    ax_exit.set_title("Top exit loads, mode 4")
    strip_axes(ax_exit)
    ax_exit.legend(frameon=False)
    panel_label(ax_exit, "b")

    sg = mode4["exit_by_source_group"].copy()
    sg["exit_short"] = sg["exit_name"].str.replace("Exit_", "", regex=False)
    sg["line"] = sg["line"].fillna("Other")
    pivot = sg[sg["method_label"] == "AdaptiveQueueAwareAStar"].pivot_table(
        index="line",
        columns="exit_short",
        values="people",
        aggfunc="sum",
        fill_value=0,
    )
    top_cols = pivot.sum(axis=0).sort_values(ascending=False).head(10).index
    pivot = pivot.loc[[x for x in line_order if x in pivot.index], top_cols]
    im = ax_heat.imshow(pivot.values, cmap="YlGnBu", aspect="auto")
    ax_heat.set_xticks(np.arange(len(pivot.columns)))
    ax_heat.set_xticklabels(pivot.columns, rotation=50, ha="right")
    ax_heat.set_yticks(np.arange(len(pivot.index)))
    ax_heat.set_yticklabels(pivot.index)
    ax_heat.set_title("Adaptive source-line to exit matrix")
    cbar = fig.colorbar(im, ax=ax_heat, fraction=0.040, pad=0.015)
    cbar.set_label("Passengers")
    panel_label(ax_heat, "c")

    fac = mode4["facility_throughput"].copy()
    fac["delta"] = fac["AdaptiveQueueAwareAStar"] - fac["ImprovedAStar"]
    fac = fac.reindex(fac["delta"].abs().sort_values(ascending=False).head(12).index)
    fac = fac.sort_values("delta")
    colors = np.where(fac["delta"] >= 0, COLORS["AdaptiveQueueAwareAStar"], COLORS["ImprovedAStar"])
    ax_fac.barh(np.arange(len(fac)), fac["delta"], color=colors, alpha=0.9)
    ax_fac.axvline(0, color="#333333", linewidth=0.7)
    ax_fac.set_yticks(np.arange(len(fac)))
    ax_fac.set_yticklabels([short_node_label(x) for x in fac["facility"]])
    ax_fac.tick_params(axis="y", labelsize=6.5)
    ax_fac.set_xlabel("Adaptive - Improved A* passengers")
    ax_fac.set_title("Largest facility load shifts")
    strip_axes(ax_fac)
    ax_fac.grid(True, axis="x", color=COLORS["grid"], linewidth=0.45, alpha=0.55)
    panel_label(ax_fac, "d")

    savefig(fig, "fig3_spatial_redistribution")


def figure_4(mode4: dict[str, pd.DataFrame]) -> None:
    route = mode4["route_chain"].copy()
    fac = mode4["facility_throughput"].copy()
    fig = plt.figure(figsize=(8.0, 6.0))
    gs = fig.add_gridspec(2, 2, hspace=0.45, wspace=0.56)
    ax_rank = fig.add_subplot(gs[0, 0])
    ax_change = fig.add_subplot(gs[0, 1])
    ax_type = fig.add_subplot(gs[1, 0])
    ax_conc = fig.add_subplot(gs[1, 1])

    top_imp = fac.sort_values("ImprovedAStar", ascending=False).head(12)
    y = np.arange(len(top_imp))
    ax_rank.barh(y + 0.18, top_imp["ImprovedAStar"], height=0.34, color=COLORS["ImprovedAStar"], label="Improved A*")
    ax_rank.barh(y - 0.18, top_imp["AdaptiveQueueAwareAStar"], height=0.34, color=COLORS["AdaptiveQueueAwareAStar"], label="Adaptive")
    ax_rank.set_yticks(y)
    ax_rank.set_yticklabels([short_node_label(x) for x in top_imp["facility"]])
    ax_rank.tick_params(axis="y", labelsize=6.5)
    ax_rank.invert_yaxis()
    ax_rank.set_xlabel("Passengers")
    ax_rank.set_title("High-throughput bottleneck candidates")
    strip_axes(ax_rank)
    panel_label(ax_rank, "a")

    route_fac = route[route["chain_type"] == "facility"].copy()
    pivot = route_fac.pivot_table(index="node", columns="method", values="people", aggfunc="sum", fill_value=0)
    for method in ["ImprovedAStar", "AdaptiveQueueAwareAStar"]:
        if method not in pivot.columns:
            pivot[method] = 0
    pivot["delta"] = pivot["AdaptiveQueueAwareAStar"] - pivot["ImprovedAStar"]
    changed = pivot.reindex(pivot["delta"].abs().sort_values(ascending=False).head(12).index).sort_values("delta")
    ax_change.barh(
        np.arange(len(changed)),
        changed["delta"],
        color=np.where(changed["delta"] >= 0, COLORS["AdaptiveQueueAwareAStar"], COLORS["ImprovedAStar"]),
    )
    ax_change.axvline(0, color="#333333", linewidth=0.7)
    ax_change.set_yticks(np.arange(len(changed)))
    ax_change.set_yticklabels([short_node_label(x) for x in changed.index])
    ax_change.tick_params(axis="y", labelsize=6.5)
    ax_change.set_xlabel("Route-chain flow shift")
    ax_change.set_title("Pathway-level reallocation")
    strip_axes(ax_change)
    ax_change.grid(True, axis="x", color=COLORS["grid"], linewidth=0.45, alpha=0.55)
    panel_label(ax_change, "b")

    type_flow = (
        route.groupby(["method", "chain_type"])["people"]
        .sum()
        .reset_index()
        .pivot(index="chain_type", columns="method", values="people")
        .fillna(0)
    )
    type_flow = type_flow.reindex(["facility", "exit"]).dropna(how="all")
    x = np.arange(len(type_flow))
    ax_type.bar(x - 0.18, type_flow.get("ImprovedAStar", 0), width=0.36, color=COLORS["ImprovedAStar"], label="Improved A*")
    ax_type.bar(x + 0.18, type_flow.get("AdaptiveQueueAwareAStar", 0), width=0.36, color=COLORS["AdaptiveQueueAwareAStar"], label="Adaptive")
    ax_type.set_xticks(x)
    ax_type.set_xticklabels(type_flow.index.str.title())
    ax_type.set_ylabel("Passenger appearances in route chains")
    ax_type.set_title("Route-chain burden by layer")
    strip_axes(ax_type)
    panel_label(ax_type, "c")

    shares = []
    for method in ["ImprovedAStar", "AdaptiveQueueAwareAStar"]:
        values = fac[method].sort_values(ascending=False).to_numpy(dtype=float)
        total = values.sum()
        cum = np.cumsum(values) / total if total else values
        shares.append((method, cum))
        ax_conc.plot(np.arange(1, len(cum) + 1), cum, color=COLORS[method], linewidth=1.4, label=METHOD_LABELS[method])
    ax_conc.axhline(0.5, color="#999999", linewidth=0.7, linestyle=":")
    ax_conc.set_xlim(1, min(40, len(fac)))
    ax_conc.set_ylim(0, 1.02)
    ax_conc.set_xlabel("Top facilities ranked by flow")
    ax_conc.set_ylabel("Cumulative share")
    ax_conc.set_title("Facility-load concentration")
    strip_axes(ax_conc)
    ax_conc.legend(frameon=False, loc="lower right")
    panel_label(ax_conc, "d")

    savefig(fig, "fig4_bottleneck_mechanism")


def figure_5() -> None:
    abl = pd.read_csv(ABLATION / "ablation_results.csv")
    comp = pd.read_csv(ABLATION / "component_contributions.csv")
    sens_summary = pd.read_csv(SENS / "sensitivity_summary.csv")
    sens_results = pd.read_csv(SENS / "sensitivity_results.csv")

    fig = plt.figure(figsize=(8.0, 6.6))
    gs = fig.add_gridspec(2, 2, hspace=0.50, wspace=0.48)
    ax_abl = fig.add_subplot(gs[0, 0])
    ax_comp = fig.add_subplot(gs[0, 1])
    ax_tornado = fig.add_subplot(gs[1, 0])
    ax_param = fig.add_subplot(gs[1, 1])

    metrics = ["T100", "queue", "congestion", "severe", "gini"]
    plot_abl = abl.set_index("variant").loc[["ImprovedAStar", "Full model", "NoWaitingTime (Density)"], metrics]
    norm = plot_abl.copy()
    for c in norm.columns:
        denom = float(norm.loc["ImprovedAStar", c]) if float(norm.loc["ImprovedAStar", c]) != 0 else 1.0
        norm[c] = norm[c] / denom
    x = np.arange(len(metrics))
    width = 0.24
    palette = ["#4C78A8", "#E45756", "#72B7B2"]
    variant_labels = {
        "ImprovedAStar": "Improved A*",
        "Full model": "Full model",
        "NoWaitingTime (Density)": "No waiting-density",
    }
    for i, variant in enumerate(norm.index):
        ax_abl.bar(x + (i - 1) * width, norm.loc[variant].values, width=width, color=palette[i], label=variant_labels.get(variant, variant))
    ax_abl.axhline(1, color="#333333", linewidth=0.7, linestyle=":")
    ax_abl.set_xticks(x)
    ax_abl.set_xticklabels(["T100", "Queue", "Moderate", "Severe", "Gini"])
    ax_abl.set_ylabel("Ratio to Improved A*")
    ax_abl.set_title("Ablation profile")
    strip_axes(ax_abl)
    ax_abl.legend(frameon=False, loc="upper left", bbox_to_anchor=(0, 1.32), ncol=2, columnspacing=0.9)
    panel_label(ax_abl, "a")

    comp = comp.sort_values("queue_pct")
    contribution_metrics = ["queue_pct", "congestion_pct", "severe_pct", "r_area_pct"]
    data = comp[contribution_metrics].to_numpy(dtype=float)
    im = ax_comp.imshow(data, aspect="auto", cmap="RdBu_r", vmin=-100, vmax=100)
    ax_comp.set_yticks(np.arange(len(comp)))
    ax_comp.set_yticklabels(comp["variant"])
    ax_comp.set_xticks(np.arange(len(contribution_metrics)))
    ax_comp.set_xticklabels(["Queue", "Moderate", "Severe", "R area"], rotation=35, ha="right")
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            ax_comp.text(j, i, f"{data[i, j]:.1f}", ha="center", va="center", fontsize=6.5)
    ax_comp.set_title("Component contribution (%)")
    cbar = fig.colorbar(im, ax=ax_comp, fraction=0.046, pad=0.02)
    cbar.set_label("Change (%)")
    panel_label(ax_comp, "b")

    ss = sens_summary.sort_values("J_range", ascending=True)
    labels = ss["parameter"].map(short_param_label)
    ax_tornado.barh(np.arange(len(ss)), ss["J_range"], color="#111827")
    ax_tornado.set_yticks(np.arange(len(ss)))
    ax_tornado.set_yticklabels(labels)
    ax_tornado.tick_params(axis="y", labelsize=6.8)
    ax_tornado.set_xlabel("J-score range")
    ax_tornado.set_title("Global sensitivity ranking")
    strip_axes(ax_tornado)
    ax_tornado.grid(True, axis="x", color=COLORS["grid"], linewidth=0.45, alpha=0.55)
    panel_label(ax_tornado, "c")

    top_params = sens_summary.sort_values("J_range", ascending=False).head(6)["parameter"].tolist()
    param = sens_results[sens_results["parameter"].isin(top_params)].copy()
    metric = "J"
    param_piv = param.pivot(index="parameter", columns="level", values=metric).loc[top_params]
    param_piv["nominal"] = sens_summary.set_index("parameter").loc[top_params, "J_nom"]
    param_piv = param_piv[["low", "nominal", "high"]]
    cmap = LinearSegmentedColormap.from_list("soft_heat", ["#EFF6FF", "#FDE68A", "#EF4444"])
    im2 = ax_param.imshow(param_piv.values, cmap=cmap, aspect="auto")
    ax_param.set_yticks(np.arange(len(param_piv)))
    ax_param.set_yticklabels([short_param_label(x) for x in param_piv.index])
    ax_param.tick_params(axis="y", labelsize=6.8)
    ax_param.set_xticks(np.arange(3))
    ax_param.set_xticklabels(["Low", "Nominal", "High"])
    for i in range(param_piv.shape[0]):
        for j in range(param_piv.shape[1]):
            ax_param.text(j, i, f"{param_piv.iloc[i, j]:.2f}", ha="center", va="center", fontsize=6.5)
    ax_param.set_title("Parameter response surface")
    cbar2 = fig.colorbar(im2, ax=ax_param, fraction=0.046, pad=0.02)
    cbar2.set_label("J-score")
    panel_label(ax_param, "d")

    savefig(fig, "fig5_ablation_sensitivity")


def write_manifest() -> None:
    files = sorted(p.name for p in OUT.glob("*") if p.suffix.lower() in {".png", ".pdf", ".svg"})
    lines = [
        "# Nature-style figure set v1",
        "",
        "Data sources:",
        f"- {MODE1.relative_to(ROOT)}",
        f"- {MODE4.relative_to(ROOT)}",
        f"- {ABLATION.relative_to(ROOT)}",
        f"- {SENS.relative_to(ROOT)}",
        "",
        "Generated files:",
    ]
    lines.extend(f"- {name}" for name in files)
    (OUT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    setup_style()
    mode1 = read_mode(MODE1, "Mode 1")
    mode4 = read_mode(MODE4, "Mode 4")

    figure_1(mode4)
    figure_2(mode1, mode4)
    figure_3(mode1, mode4)
    figure_4(mode4)
    figure_5()
    write_manifest()
    print(f"Generated figures in {OUT}")


if __name__ == "__main__":
    main()
