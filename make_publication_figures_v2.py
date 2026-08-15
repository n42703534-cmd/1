from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Rectangle


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs" / "publication_figures_v2"
LOW = ROOT / "outputs" / "algorithm_compare" / "mode1_20260623_163319"
HIGH = ROOT / "outputs" / "algorithm_compare" / "mode4_20260623_170538"
ABLATION = ROOT / "outputs" / "ablation" / "mode4_20260609_222716"
SENS = ROOT / "outputs" / "sensitivity" / "mode4_20260608_064817"

BASE = "ImprovedAStar"
ADAP = "AdaptiveQueueAwareAStar"
METHOD = {BASE: "Baseline", ADAP: "Adaptive"}
LOAD = {"Low-load": LOW, "High-load": HIGH}

ORANGE = "#F28E2B"
BLUE = "#4E79A7"
TEAL = "#59A14F"
RED = "#E15759"
PURPLE = "#8B63A9"
DARK = "#1F2937"
GREY = "#8C8C8C"
LIGHT = "#F6F6F4"
GRID = "#D9D9D9"


def style() -> None:
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
            "savefig.dpi": 500,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "axes.linewidth": 0.75,
            "xtick.major.width": 0.65,
            "ytick.major.width": 0.65,
        }
    )


def panel(ax: plt.Axes, letter: str) -> None:
    ax.text(-0.10, 1.08, letter, transform=ax.transAxes, fontsize=11, fontweight="bold", va="bottom")


def clean(ax: plt.Axes, grid_axis: str = "y") -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, axis=grid_axis, color=GRID, linewidth=0.5, alpha=0.65)
    ax.set_axisbelow(True)


def save(fig: plt.Figure, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf", "svg"):
        fig.savefig(OUT / f"{name}.{ext}", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def read_load(path: Path, label: str) -> dict[str, pd.DataFrame]:
    names = [
        "summary_metrics",
        "improvement_vs_baseline",
        "line_clearance",
        "exit_usage",
        "exit_by_source_group",
        "facility_throughput",
        "route_chain",
    ]
    out = {}
    for name in names:
        df = pd.read_csv(path / f"{name}.csv")
        df["load"] = label
        out[name] = df
    return out


def all_data() -> dict[str, dict[str, pd.DataFrame]]:
    return {label: read_load(path, label) for label, path in LOAD.items()}


def short_node(name: str) -> str:
    label = str(name)
    pairs = [
        ("VN_", ""),
        ("Gate_", "G "),
        ("Transfer_", "X "),
        ("Escalator_", "Esc "),
        ("Stair_", "St "),
        ("_Entrance", " ent"),
        ("_Arrival", " arr"),
        ("_Corner_", " c"),
        ("_West_Vert", " W vert"),
        ("_East_Vert", " E vert"),
        ("_down", " d"),
        ("_up", " u"),
        ("_", " "),
    ]
    for old, new in pairs:
        label = label.replace(old, new)
    label = " ".join(label.split())
    return label if len(label) <= 21 else label[:19] + "..."


def short_param(name: str) -> str:
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


def draw_box(ax, xy, w, h, text, color, edge="#333333"):
    ax.add_patch(Rectangle(xy, w, h, facecolor=color, edgecolor=edge, linewidth=0.8))
    ax.text(xy[0] + w / 2, xy[1] + h / 2, text, ha="center", va="center", fontsize=7.4)


def draw_arrow(ax, xy1, xy2):
    ax.add_patch(FancyArrowPatch(xy1, xy2, arrowstyle="-|>", mutation_scale=9, color="#333333", linewidth=0.8))


def fig1_framework(data: dict[str, dict[str, pd.DataFrame]]) -> None:
    fig = plt.figure(figsize=(7.2, 5.3))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.05, 0.95], wspace=0.30, hspace=0.42)
    ax_a = fig.add_subplot(gs[0, :])
    ax_b = fig.add_subplot(gs[1, 0])
    ax_c = fig.add_subplot(gs[1, 1])

    ax_a.set_xlim(0, 1)
    ax_a.set_ylim(0, 1)
    ax_a.axis("off")
    steps = [
        (0.03, "Demand\nscenario", "#FFF4E6"),
        (0.24, "Dynamic\nstation state", "#E8F1FA"),
        (0.45, "Adaptive\nnext-hop cost", "#E9F6ED"),
        (0.66, "Network\nsimulation", "#F2ECF7"),
        (0.84, "Safety and\nefficiency\nendpoints", "#FDECEC"),
    ]
    for x, text, color in steps:
        draw_box(ax_a, (x, 0.46), 0.145, 0.26, text, color)
    for x1, x2 in [(0.17, 0.24), (0.38, 0.45), (0.59, 0.66), (0.80, 0.84)]:
        draw_arrow(ax_a, (x1, 0.59), (x2, 0.59))
    ax_a.text(
        0.50,
        0.23,
        "Baseline and adaptive strategies are compared under low- and high-load demand.",
        ha="center",
        va="center",
        fontsize=8,
        color="#333333",
    )
    ax_a.set_title("Analysis workflow")
    panel(ax_a, "a")

    comps = ["travel", "queue", "service", "down-\nstream", "exit"]
    colors = ["#9ecae1", "#fdd0a2", "#a1d99b", "#c7b9e8", "#fcaeae"]
    left = 0
    for comp, col in zip(comps, colors):
        ax_b.barh([0], [1], left=left, color=col, edgecolor="white", height=0.44)
        ax_b.text(left + 0.5, 0, comp, ha="center", va="center", fontsize=7)
        left += 1
    ax_b.set_xlim(0, len(comps))
    ax_b.set_ylim(-0.35, 0.35)
    ax_b.set_yticks([])
    ax_b.set_xticks([])
    ax_b.set_title("Adaptive cost terms")
    for sp in ax_b.spines.values():
        sp.set_visible(False)
    panel(ax_b, "b")

    summary = []
    for label, frames in data.items():
        s = frames["summary_metrics"].set_index("method")
        summary.append(
            {
                "load": label,
                "passengers_proxy": frames["exit_usage"][[BASE, ADAP]].max(axis=1).sum(),
                "baseline_T100": s.loc[BASE, "T100"],
                "adaptive_T100": s.loc[ADAP, "T100"],
            }
        )
    sdf = pd.DataFrame(summary)
    x = np.arange(len(sdf))
    ax_c.bar(x, sdf["passengers_proxy"], color=[GREY, DARK], width=0.48)
    ax_c.set_xticks(x)
    ax_c.set_xticklabels(sdf["load"])
    ax_c.set_ylabel("Evacuated passengers")
    ax_c.set_title("Demand levels used for evaluation")
    clean(ax_c)
    panel(ax_c, "c")
    save(fig, "fig1_analysis_framework")


def improvement_table(data):
    rows = []
    for load, frames in data.items():
        s = frames["summary_metrics"].set_index("method")
        for metric, label, scale, better in [
            ("T100", "Full clearance", 1, "lower"),
            ("queueing_time", "Queueing burden", 1000, "lower"),
            ("congestion_exposure", "Congestion exposure", 1000, "lower"),
            ("severe_congestion", "Severe exposure", 1000, "lower"),
            ("peak_density", "Peak density", 1, "lower"),
            ("exit_gini", "Exit imbalance", 1, "lower"),
        ]:
            base = float(s.loc[BASE, metric]) / scale
            adap = float(s.loc[ADAP, metric]) / scale
            change = (base - adap) / base * 100 if base else 0.0
            rows.append({"load": load, "metric": metric, "label": label, "base": base, "adaptive": adap, "change": change, "better": better})
    return pd.DataFrame(rows)


def fig2_main_effects(data) -> None:
    imp = improvement_table(data)
    fig = plt.figure(figsize=(7.2, 5.8))
    gs = fig.add_gridspec(2, 2, wspace=0.35, hspace=0.48)
    ax_a = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[0, 1])
    ax_c = fig.add_subplot(gs[1, 0])
    ax_d = fig.add_subplot(gs[1, 1])

    metrics = ["Full clearance", "Queueing burden", "Congestion exposure", "Severe exposure"]
    for ax, load, letter in [(ax_a, "Low-load", "a"), (ax_b, "High-load", "b")]:
        sub = imp[(imp["load"] == load) & (imp["label"].isin(metrics))].copy()
        sub["label"] = pd.Categorical(sub["label"], metrics[::-1], ordered=True)
        sub = sub.sort_values("label")
        colors = [BLUE if v >= 0 else RED for v in sub["change"]]
        ax.barh(np.arange(len(sub)), sub["change"], color=colors, height=0.55)
        ax.axvline(0, color="#333333", linewidth=0.8)
        for i, v in enumerate(sub["change"]):
            if v < 0:
                ax.text(v / 2, i, f"{v:+.1f}%", ha="center", va="center", fontsize=7, color="white")
            else:
                ax.text(max(v, 0) + 1.3, i, f"{v:+.1f}%", ha="left", va="center", fontsize=7)
        ax.set_yticks(np.arange(len(sub)))
        ax.set_yticklabels(sub["label"])
        ax.set_xlabel("Reduction relative to baseline (%)")
        ax.set_title(load)
        ax.set_xlim(-12, 48)
        clean(ax, "x")
        panel(ax, letter)

    high = data["High-load"]["summary_metrics"].set_index("method")
    qmetrics = ["T50", "T80", "T95", "T100"]
    x = np.arange(len(qmetrics))
    ax_c.plot(x, [high.loc[BASE, m] for m in qmetrics], marker="^", color=ORANGE, linewidth=1.6, label="Baseline")
    ax_c.plot(x, [high.loc[ADAP, m] for m in qmetrics], marker="o", color=BLUE, linewidth=1.6, label="Adaptive")
    ax_c.set_xticks(x)
    ax_c.set_xticklabels(qmetrics)
    ax_c.set_ylabel("Time (s)")
    ax_c.set_title("High-load evacuation quantiles")
    ax_c.legend(frameon=False, loc="upper left")
    clean(ax_c)
    panel(ax_c, "c")

    for load, marker, size in [("Low-load", "o", 54), ("High-load", "s", 82)]:
        s = data[load]["summary_metrics"].set_index("method")
        for method, color in [(BASE, ORANGE), (ADAP, BLUE)]:
            ax_d.scatter(
                s.loc[method, "T100"],
                s.loc[method, "congestion_exposure"] / 1000,
                s=size,
                marker=marker,
                color=color,
                edgecolor="white",
                linewidth=0.7,
                zorder=3,
            )
    ax_d.annotate("Low-load", xy=(321, 7), xytext=(35, 40), textcoords="offset points", arrowprops={"arrowstyle": "-", "lw": 0.6}, fontsize=7)
    ax_d.annotate("High-load adaptive", xy=(853.5, 1366), xytext=(-100, -25), textcoords="offset points", arrowprops={"arrowstyle": "-", "lw": 0.6}, fontsize=7)
    ax_d.annotate("High-load baseline", xy=(791.5, 1907), xytext=(-110, -34), textcoords="offset points", arrowprops={"arrowstyle": "-", "lw": 0.6}, fontsize=7)
    ax_d.set_xlabel("Full clearance time (s)")
    ax_d.set_ylabel("Congestion exposure (x10^3 pax s)")
    ax_d.set_title("Safety-efficiency trade-off")
    clean(ax_d)
    handles = [
        Line2D([0], [0], marker="^", color="none", markerfacecolor=ORANGE, label="Baseline", markersize=6),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=BLUE, label="Adaptive", markersize=6),
    ]
    ax_d.legend(handles=handles, frameon=False, loc="upper left")
    panel(ax_d, "d")
    save(fig, "fig2_primary_performance")


def fig3_redistribution(data) -> None:
    fig = plt.figure(figsize=(7.8, 6.0))
    gs = fig.add_gridspec(2, 2, wspace=0.48, hspace=0.50)
    ax_a = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[0, 1])
    ax_c = fig.add_subplot(gs[1, 0])
    ax_d = fig.add_subplot(gs[1, 1])

    line_rows = []
    for load, frames in data.items():
        for _, row in frames["line_clearance"].iterrows():
            line_rows.append({"load": load, "line": row["line"], "Baseline": row[BASE], "Adaptive": row[ADAP]})
    ldf = pd.DataFrame(line_rows)
    ldf = ldf[ldf["line"].isin(["L16", "L18", "L2", "L7", "Maglev"])]
    ldf["y"] = np.arange(len(ldf))
    for _, row in ldf.iterrows():
        ax_a.plot([row["Baseline"], row["Adaptive"]], [row["y"], row["y"]], color="#B9B9B9", lw=1.1)
        ax_a.scatter(row["Baseline"], row["y"], color=ORANGE, marker="^", s=36)
        ax_a.scatter(row["Adaptive"], row["y"], color=BLUE, marker="o", s=36)
    ax_a.set_yticks(ldf["y"])
    ax_a.set_yticklabels([f"{r.load.replace('-load','')} {r.line}" for r in ldf.itertuples()])
    ax_a.set_xlabel("Line clearance time (s)")
    ax_a.set_title("Line clearance by demand level")
    clean(ax_a, "x")
    panel(ax_a, "a")

    exit_df = data["High-load"]["exit_usage"].copy()
    exit_df["delta_pct"] = exit_df[f"{ADAP}_pct"] - exit_df[f"{BASE}_pct"]
    top = exit_df.reindex(exit_df["delta_pct"].abs().sort_values(ascending=False).head(12).index).sort_values("delta_pct")
    ax_b.barh(np.arange(len(top)), top["delta_pct"], color=[BLUE if x > 0 else ORANGE for x in top["delta_pct"]], height=0.58)
    ax_b.axvline(0, color="#333333", lw=0.8)
    ax_b.set_yticks(np.arange(len(top)))
    ax_b.set_yticklabels([e.replace("Exit_", "") for e in top["exit"]])
    ax_b.set_xlabel("Change in exit share (percentage points)")
    ax_b.set_title("High-load exit redistribution")
    clean(ax_b, "x")
    panel(ax_b, "b")

    sg = data["High-load"]["exit_by_source_group"].copy()
    sg = sg[sg["method_label"] == ADAP]
    sg["exit_short"] = sg["exit_name"].str.replace("Exit_", "", regex=False)
    pivot = sg.pivot_table(index="line", columns="exit_short", values="people", aggfunc="sum", fill_value=0)
    rows = [r for r in ["L16", "L18", "L2", "L7", "Maglev"] if r in pivot.index]
    cols = pivot.sum().sort_values(ascending=False).head(9).index
    pivot = pivot.loc[rows, cols]
    im = ax_c.imshow(pivot.values, aspect="auto", cmap="YlGnBu")
    ax_c.set_xticks(np.arange(len(cols)))
    ax_c.set_xticklabels(cols, rotation=50, ha="right")
    ax_c.set_yticks(np.arange(len(rows)))
    ax_c.set_yticklabels(rows)
    ax_c.set_title("Adaptive high-load source-to-exit flow")
    cb = fig.colorbar(im, ax=ax_c, fraction=0.042, pad=0.015)
    cb.set_label("Passengers")
    panel(ax_c, "c")

    gini_rows = []
    for load, frames in data.items():
        s = frames["summary_metrics"].set_index("method")
        gini_rows += [
            {"load": load, "method": "Baseline", "gini": s.loc[BASE, "exit_gini"]},
            {"load": load, "method": "Adaptive", "gini": s.loc[ADAP, "exit_gini"]},
        ]
    gdf = pd.DataFrame(gini_rows)
    x = np.arange(2)
    width = 0.32
    for i, method in enumerate(["Baseline", "Adaptive"]):
        vals = [gdf[(gdf["load"] == load) & (gdf["method"] == method)]["gini"].iloc[0] for load in ["Low-load", "High-load"]]
        ax_d.bar(x + (i - 0.5) * width, vals, width=width, color=ORANGE if method == "Baseline" else BLUE, label=method)
    ax_d.set_xticks(x)
    ax_d.set_xticklabels(["Low-load", "High-load"])
    ax_d.set_ylabel("Exit Gini coefficient")
    ax_d.set_title("Exit-use imbalance")
    ax_d.legend(frameon=False, loc="upper left")
    clean(ax_d)
    panel(ax_d, "d")
    save(fig, "fig3_flow_redistribution")


def fig4_bottlenecks(data) -> None:
    fac = data["High-load"]["facility_throughput"].copy()
    route = data["High-load"]["route_chain"].copy()
    fig = plt.figure(figsize=(7.8, 5.8))
    gs = fig.add_gridspec(2, 2, wspace=0.52, hspace=0.48)
    ax_a = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[0, 1])
    ax_c = fig.add_subplot(gs[1, 0])
    ax_d = fig.add_subplot(gs[1, 1])

    top = fac.assign(total=lambda d: d[[BASE, ADAP]].max(axis=1)).sort_values("total", ascending=False).head(10)
    y = np.arange(len(top))
    ax_a.barh(y + 0.16, top[BASE], height=0.30, color=ORANGE, label="Baseline")
    ax_a.barh(y - 0.16, top[ADAP], height=0.30, color=BLUE, label="Adaptive")
    ax_a.set_yticks(y)
    ax_a.set_yticklabels([short_node(x) for x in top["facility"]])
    ax_a.invert_yaxis()
    ax_a.set_xlabel("Passengers")
    ax_a.set_title("High-load bottleneck candidates")
    ax_a.legend(frameon=False, loc="lower right")
    clean(ax_a, "x")
    panel(ax_a, "a")

    fac["delta"] = fac[ADAP] - fac[BASE]
    changed = fac.reindex(fac["delta"].abs().sort_values(ascending=False).head(12).index).sort_values("delta")
    ax_b.barh(np.arange(len(changed)), changed["delta"], color=[BLUE if v > 0 else ORANGE for v in changed["delta"]], height=0.56)
    ax_b.axvline(0, color="#333333", lw=0.8)
    ax_b.set_yticks(np.arange(len(changed)))
    ax_b.set_yticklabels([short_node(x) for x in changed["facility"]])
    ax_b.set_xlabel("Adaptive - baseline passengers")
    ax_b.set_title("Largest facility-load shifts")
    clean(ax_b, "x")
    panel(ax_b, "b")

    layer = route.groupby(["method", "chain_type"])["people"].sum().reset_index()
    pivot = layer.pivot(index="chain_type", columns="method", values="people").fillna(0).loc[["facility", "exit"]]
    x = np.arange(len(pivot))
    ax_c.bar(x - 0.17, pivot[BASE], width=0.34, color=ORANGE, label="Baseline")
    ax_c.bar(x + 0.17, pivot[ADAP], width=0.34, color=BLUE, label="Adaptive")
    ax_c.set_xticks(x)
    ax_c.set_xticklabels(["Facilities", "Exits"])
    ax_c.set_ylabel("Passenger appearances in route chains")
    ax_c.set_title("Route-chain burden")
    clean(ax_c)
    panel(ax_c, "c")

    for method, color, label in [(BASE, ORANGE, "Baseline"), (ADAP, BLUE, "Adaptive")]:
        vals = np.sort(fac[method].to_numpy(dtype=float))[::-1]
        cum = np.cumsum(vals) / vals.sum()
        ax_d.plot(np.arange(1, len(cum) + 1), cum, color=color, lw=1.6, label=label)
    ax_d.axhline(0.5, color=GREY, ls=":", lw=0.9)
    ax_d.set_xlim(1, 40)
    ax_d.set_ylim(0, 1)
    ax_d.set_xlabel("Top facilities ranked by flow")
    ax_d.set_ylabel("Cumulative share")
    ax_d.set_title("Facility-load concentration")
    ax_d.legend(frameon=False, loc="lower right")
    clean(ax_d)
    panel(ax_d, "d")
    save(fig, "fig4_bottleneck_mechanism")


def fig5_mechanism() -> None:
    abl = pd.read_csv(ABLATION / "ablation_results.csv")
    comp = pd.read_csv(ABLATION / "component_contributions.csv")
    ss = pd.read_csv(SENS / "sensitivity_summary.csv")
    sr = pd.read_csv(SENS / "sensitivity_results.csv")

    fig = plt.figure(figsize=(7.8, 6.2))
    gs = fig.add_gridspec(2, 2, wspace=0.50, hspace=0.52)
    ax_a = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[0, 1])
    ax_c = fig.add_subplot(gs[1, 0])
    ax_d = fig.add_subplot(gs[1, 1])

    metrics = ["T100", "queue", "congestion", "severe", "gini"]
    variants = ["ImprovedAStar", "Full model", "NoWaitingTime (Density)"]
    labels = ["Baseline", "Full adaptive", "No waiting-density"]
    plot = abl.set_index("variant").loc[variants, metrics]
    norm = plot.copy()
    for m in metrics:
        norm[m] = norm[m] / float(plot.loc["ImprovedAStar", m] or 1)
    x = np.arange(len(metrics))
    width = 0.25
    for i, (variant, label, color) in enumerate(zip(variants, labels, [ORANGE, BLUE, TEAL])):
        ax_a.bar(x + (i - 1) * width, norm.loc[variant], width=width, color=color, label=label)
    ax_a.axhline(1, color="#333333", lw=0.8, ls=":")
    ax_a.set_xticks(x)
    ax_a.set_xticklabels(["T100", "Queue", "Cong.", "Severe", "Gini"])
    ax_a.set_ylabel("Ratio to baseline")
    ax_a.set_title("Ablation profile", pad=10)
    ax_a.legend(frameon=False, loc="upper left", bbox_to_anchor=(0.0, -0.16), ncol=3, fontsize=6.5, columnspacing=0.9)
    clean(ax_a)
    panel(ax_a, "a")

    comp = comp.set_index("variant")[["queue_pct", "congestion_pct", "severe_pct", "r_area_pct"]]
    vals = comp.to_numpy(dtype=float)
    im = ax_b.imshow(vals, aspect="auto", cmap="YlOrRd", vmin=0, vmax=max(100, vals.max()))
    ax_b.set_yticks(np.arange(len(comp.index)))
    ax_b.set_yticklabels(["No waiting-density"])
    ax_b.set_xticks(np.arange(4))
    ax_b.set_xticklabels(["Queue", "Cong.", "Severe", "R area"], rotation=35, ha="right")
    for i in range(vals.shape[0]):
        for j in range(vals.shape[1]):
            ax_b.text(j, i, f"{vals[i, j]:.1f}", ha="center", va="center", fontsize=7)
    ax_b.set_title("Loss after removing queue-density term (%)")
    cb = fig.colorbar(im, ax=ax_b, fraction=0.044, pad=0.015)
    cb.set_label("Increase (%)")
    panel(ax_b, "b")

    ss = ss.sort_values("J_range", ascending=True)
    ax_c.barh(np.arange(len(ss)), ss["J_range"], color=DARK, height=0.56)
    ax_c.set_yticks(np.arange(len(ss)))
    ax_c.set_yticklabels([short_param(x) for x in ss["parameter"]])
    ax_c.set_xlabel("Objective-score range")
    ax_c.set_title("Parameter sensitivity")
    clean(ax_c, "x")
    panel(ax_c, "c")

    top_params = pd.read_csv(SENS / "sensitivity_summary.csv").sort_values("J_range", ascending=False).head(6)["parameter"].tolist()
    prm = sr[sr["parameter"].isin(top_params)].pivot(index="parameter", columns="level", values="J").loc[top_params]
    prm["nominal"] = pd.read_csv(SENS / "sensitivity_summary.csv").set_index("parameter").loc[top_params, "J_nom"]
    prm = prm[["low", "nominal", "high"]]
    cmap = LinearSegmentedColormap.from_list("white_orange_red", ["#F7FBFF", "#FEE8A8", "#F28E2B", "#C7362F"])
    im2 = ax_d.imshow(prm.values, aspect="auto", cmap=cmap)
    ax_d.set_yticks(np.arange(len(prm.index)))
    ax_d.set_yticklabels([short_param(x) for x in prm.index])
    ax_d.set_xticks(np.arange(3))
    ax_d.set_xticklabels(["Low", "Nominal", "High"])
    for i in range(prm.shape[0]):
        for j in range(prm.shape[1]):
            ax_d.text(j, i, f"{prm.iloc[i, j]:.2f}", ha="center", va="center", fontsize=7)
    ax_d.set_title("Response of top parameters")
    cb2 = fig.colorbar(im2, ax=ax_d, fraction=0.044, pad=0.015)
    cb2.set_label("Objective score")
    panel(ax_d, "d")
    save(fig, "fig5_ablation_sensitivity")


def manifest() -> None:
    lines = [
        "# Publication figure set v2",
        "",
        "Internal source directories are relabeled as:",
        "- mode1_20260623_163319 -> Low-load",
        "- mode4_20260623_170538 -> High-load",
        "",
        "Figures:",
    ]
    lines += [f"- {p.name}" for p in sorted(OUT.glob("*")) if p.suffix in {".png", ".pdf", ".svg"}]
    (OUT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    style()
    data = all_data()
    fig1_framework(data)
    fig2_main_effects(data)
    fig3_redistribution(data)
    fig4_bottlenecks(data)
    fig5_mechanism()
    manifest()
    print(f"Generated publication figures in {OUT}")


if __name__ == "__main__":
    main()
