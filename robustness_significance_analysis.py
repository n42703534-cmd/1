from __future__ import annotations

import argparse
import copy
import csv
import math
import random
import statistics
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENDORED_SITE_PACKAGES = ROOT / "__vendor_site_packages"
if VENDORED_SITE_PACKAGES.exists():
    sys.path.insert(0, str(VENDORED_SITE_PACKAGES))

import matplotlib.pyplot as plt  # noqa: E402

import network  # noqa: E402
import single_path_routing as spr  # noqa: E402


OUTPUT_RAW = ROOT / "216_robustness_raw_samples.csv"
OUTPUT_SUMMARY = ROOT / "217_robustness_summary.csv"
OUTPUT_SIGNIFICANCE = ROOT / "218_robustness_significance_tests.csv"
OUTPUT_BOXPLOT = ROOT / "219_robustness_boxplots.png"
OUTPUT_REPORT = ROOT / "220_robustness_report.md"

DEFAULT_RUNS = 30
BASE_SEED = 20260513
PERMUTATION_DRAWS = 20000
BOOTSTRAP_DRAWS = 10000
DEFAULT_CAPACITY_LOW = 0.95
DEFAULT_CAPACITY_HIGH = 1.05

METHODS = [
    ("PaperImprovedAStar", spr.PAPER_SINGLE_PATH_METHOD),
    ("AdaptiveQueueAwareAStar", spr.OUR_SINGLE_PATH_METHOD),
]

METRICS = [
    ("evacuation_time_s", "总疏散时间 (s)"),
    ("queueing_time_person_s", "累计排队时间 (人·秒)"),
    ("moderate_congestion_exposure_time_person_s", "中度拥挤暴露 (density > 3)"),
    ("severe_congestion_exposure_time_person_s", "重度拥挤暴露 (density > 5)"),
]

EXTRA_METRICS = [
    ("peak_density_p_per_m2", "峰值密度 (人/m^2)"),
]

STATION_BASE_LOADS = {
    "L2": {"platform_waiting": 236, "hall_people": 350, "transfer_people": 526},
    "L7": {"platform_waiting": 219, "hall_people": 112, "transfer_people": 169},
    "L16": {"platform_waiting": 42, "hall_people": 15, "transfer_people": 27},
    "L18": {"platform_waiting": 178, "hall_people": 125, "transfer_people": 188},
    "Maglev": {"platform_waiting": 0, "hall_people": 0, "transfer_people": 0},
}


def build_scenario1_pop_dict():
    pop_dict = {}
    for line in network.TRAIN_PHYSICS:
        base = STATION_BASE_LOADS[line]
        pop_dict[line] = {
            "train_1": 0,
            "train_2": 0,
            "platform_waiting": int(base["platform_waiting"]),
            "hall_people": int(base["hall_people"]),
            "transfer_people": int(base["transfer_people"]),
        }
    return pop_dict


def write_csv(path: Path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def percentile(sorted_values, q):
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = (len(sorted_values) - 1) * q
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return float(sorted_values[low])
    frac = pos - low
    return float(sorted_values[low]) * (1.0 - frac) + float(sorted_values[high]) * frac


def summarize_samples(values):
    ordered = sorted(float(v) for v in values)
    mean = statistics.mean(ordered)
    std = statistics.stdev(ordered) if len(ordered) > 1 else 0.0
    return {
        "mean": mean,
        "std": std,
        "min": ordered[0],
        "q1": percentile(ordered, 0.25),
        "median": percentile(ordered, 0.50),
        "q3": percentile(ordered, 0.75),
        "max": ordered[-1],
    }


def paired_permutation_pvalue(diffs, draws=PERMUTATION_DRAWS, seed=1234):
    rng = random.Random(seed)
    diffs = [float(d) for d in diffs]
    observed = abs(statistics.mean(diffs))
    if observed <= 1e-12:
        return 1.0
    extreme = 0
    for _ in range(draws):
        signed_mean = statistics.mean(d if rng.random() < 0.5 else -d for d in diffs)
        if abs(signed_mean) >= observed - 1e-12:
            extreme += 1
    return (extreme + 1) / (draws + 1)


def bootstrap_mean_ci(diffs, draws=BOOTSTRAP_DRAWS, seed=5678):
    rng = random.Random(seed)
    diffs = [float(d) for d in diffs]
    samples = []
    for _ in range(draws):
        picked = [diffs[rng.randrange(len(diffs))] for _ in range(len(diffs))]
        samples.append(statistics.mean(picked))
    samples.sort()
    return percentile(samples, 0.025), percentile(samples, 0.975)


def build_perturbed_graph(graph, run_seed, capacity_low, capacity_high, failure_facility=None):
    scenario_graph = copy.deepcopy(graph)
    if failure_facility:
        if failure_facility not in scenario_graph.nodes:
            raise ValueError(f"Failure facility {failure_facility} not found in graph.")
        network._apply_node_disruption(scenario_graph, failure_facility, factor=0.0)
    network.apply_capacity_noise(scenario_graph, random.Random(run_seed), capacity_low, capacity_high)
    return scenario_graph


def collect_raw_rows(graph, pop_dict, runs, capacity_low, capacity_high, failure_facility=None):
    rows = []
    for run_idx in range(1, runs + 1):
        run_seed = BASE_SEED + run_idx
        print(f"Running robustness sample {run_idx}/{runs}")
        for method_label, method in METHODS:
            scenario_graph = build_perturbed_graph(
                graph,
                run_seed,
                capacity_low,
                capacity_high,
                failure_facility=failure_facility,
            )
            metrics = network.run_simulation_for_metrics_timed(
                scenario_graph,
                pop_dict,
                method=method,
                apply_noise=False,
            )
            rows.append(
                {
                    "run_id": run_idx,
                    "noise_seed": run_seed,
                    "capacity_low": capacity_low,
                    "capacity_high": capacity_high,
                    "failure_facility": failure_facility or "",
                    "method_label": method_label,
                    "evacuation_time_s": float(metrics["time"]),
                    "queueing_time_person_s": float(metrics["queueing_time"]),
                    "moderate_congestion_exposure_time_person_s": float(
                        metrics.get("moderate_congestion_exposure_time", metrics["congestion_exposure_time"])
                    ),
                    "severe_congestion_exposure_time_person_s": float(
                        metrics.get("severe_congestion_exposure_time", 0.0)
                    ),
                    "peak_density_p_per_m2": float(metrics.get("peak_density", 0.0)),
                    "avg_speed_m_per_s": float(metrics.get("avg_speed", 0.0)),
                    "wall_clock_runtime_s": float(metrics.get("wall_clock_runtime_s", 0.0)),
                }
            )
    return rows


def build_summary_rows(raw_rows):
    rows = []
    for method_label, _ in METHODS:
        method_rows = [row for row in raw_rows if row["method_label"] == method_label]
        for metric_key, metric_label in METRICS + EXTRA_METRICS:
            stats = summarize_samples(row[metric_key] for row in method_rows)
            rows.append(
                {
                    "method_label": method_label,
                    "metric_key": metric_key,
                    "metric_label": metric_label,
                    **stats,
                }
            )
    return rows


def build_significance_rows(raw_rows, runs):
    by_run_method = {(row["run_id"], row["method_label"]): row for row in raw_rows}
    comparisons = [
        ("AdaptiveQueueAwareAStar", "PaperImprovedAStar"),
    ]
    rows = []
    for better, worse in comparisons:
        for metric_key, metric_label in METRICS + EXTRA_METRICS:
            diffs = []
            wins = 0
            ties = 0
            for run_id in range(1, runs + 1):
                delta = float(by_run_method[(run_id, better)][metric_key]) - float(by_run_method[(run_id, worse)][metric_key])
                diffs.append(delta)
                if delta < -1e-9:
                    wins += 1
                elif abs(delta) <= 1e-9:
                    ties += 1
            ci_low, ci_high = bootstrap_mean_ci(diffs, seed=9000 + len(rows))
            rows.append(
                {
                    "comparison": f"{better} vs {worse}",
                    "metric_key": metric_key,
                    "metric_label": metric_label,
                    "mean_delta_our_minus_baseline": statistics.mean(diffs),
                    "median_delta_our_minus_baseline": statistics.median(diffs),
                    "wins_our": wins,
                    "ties": ties,
                    "losses_our": runs - wins - ties,
                    "win_rate_our": wins / runs,
                    "permutation_p_value": paired_permutation_pvalue(diffs, seed=7000 + len(rows)),
                    "bootstrap_ci95_low": ci_low,
                    "bootstrap_ci95_high": ci_high,
                }
            )
    return rows


def draw_boxplots(raw_rows):
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    axes = axes.flatten()
    colors = {
        "PaperImprovedAStar": "#59A14F",
        "AdaptiveQueueAwareAStar": "#E15759",
    }
    for ax, (metric_key, metric_label) in zip(axes, METRICS):
        data = []
        labels = []
        for method_label, _ in METHODS:
            values = [float(row[metric_key]) for row in raw_rows if row["method_label"] == method_label]
            data.append(values)
            labels.append(method_label)
        bp = ax.boxplot(data, labels=labels, patch_artist=True, showmeans=True)
        for patch, label in zip(bp["boxes"], labels):
            patch.set_facecolor(colors[label])
            patch.set_alpha(0.70)
        ax.set_title(metric_label, fontweight="bold")
        ax.grid(True, axis="y", linestyle=":", alpha=0.5)
    fig.suptitle("Scenario 1 + 容量扰动鲁棒性箱线图", fontsize=16, fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(OUTPUT_BOXPLOT, dpi=300, bbox_inches="tight")
    plt.close()


def build_report(summary_rows, significance_rows, runs, capacity_low, capacity_high, failure_facility=None):
    summary_lookup = {(row["method_label"], row["metric_key"]): row for row in summary_rows}
    sig_lookup = {(row["comparison"], row["metric_key"]): row for row in significance_rows}

    def fmt(value):
        return f"{float(value):.2f}"

    lines = [
        "# 鲁棒性与统计显著性检验",
        "",
        "- 场景：Scenario 1 + Pathfinder 几何",
        f"- 扰动方式：边容量独立乘以 `U({capacity_low:.2f}, {capacity_high:.2f})` 随机因子",
        f"- 固定设施失效：`{failure_facility}`" if failure_facility else "- 固定设施失效：无",
        f"- 重复次数：`{runs}`",
        "- 比较算法：`PaperImprovedAStar`、`AdaptiveQueueAwareAStar`",
        "- 显著性方法：配对符号翻转置换检验（paired sign-flip permutation test）",
        "",
        "## 各算法均值 ± 标准差",
        "",
    ]

    for metric_key, metric_label in METRICS:
        lines.append(f"### {metric_label}")
        for method_label, _ in METHODS:
            row = summary_lookup[(method_label, metric_key)]
            lines.append(f"- `{method_label}`: `{fmt(row['mean'])} ± {fmt(row['std'])}`")
        lines.append("")

    lines.extend(["## 显著性结果", ""])
    for comparison in ["AdaptiveQueueAwareAStar vs PaperImprovedAStar"]:
        lines.append(f"### {comparison}")
        for metric_key, metric_label in METRICS:
            row = sig_lookup[(comparison, metric_key)]
            lines.append(
                f"- `{metric_label}`: 均值差（Our - Baseline）=`{fmt(row['mean_delta_our_minus_baseline'])}`，"
                f"95% CI=`[{fmt(row['bootstrap_ci95_low'])}, {fmt(row['bootstrap_ci95_high'])}]`，"
                f"`p={row['permutation_p_value']:.4f}`，Our 胜率=`{row['win_rate_our']:.1%}`"
            )
        lines.append("")

    lines.extend(
        [
            "## 输出文件",
            "",
            f"- [216_robustness_raw_samples.csv]({OUTPUT_RAW.as_posix()})",
            f"- [217_robustness_summary.csv]({OUTPUT_SUMMARY.as_posix()})",
            f"- [218_robustness_significance_tests.csv]({OUTPUT_SIGNIFICANCE.as_posix()})",
            f"- [219_robustness_boxplots.png]({OUTPUT_BOXPLOT.as_posix()})",
        ]
    )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Scenario 1 鲁棒性与统计显著性分析")
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS, help="Monte Carlo 重复次数，默认 30")
    parser.add_argument("--capacity-low", type=float, default=DEFAULT_CAPACITY_LOW, help="边容量随机扰动下界")
    parser.add_argument("--capacity-high", type=float, default=DEFAULT_CAPACITY_HIGH, help="边容量随机扰动上界")
    parser.add_argument("--failure-facility", default=None, help="可选：固定中断的设施节点名，例如 Escalator_L2_up1")
    args = parser.parse_args()
    if args.capacity_low <= 0 or args.capacity_high <= 0 or args.capacity_low > args.capacity_high:
        raise ValueError("Capacity perturbation range must satisfy 0 < low <= high.")

    graph = network.build_graph()
    pop_dict = build_scenario1_pop_dict()
    raw_rows = collect_raw_rows(
        graph,
        pop_dict,
        args.runs,
        args.capacity_low,
        args.capacity_high,
        failure_facility=args.failure_facility,
    )
    summary_rows = build_summary_rows(raw_rows)
    significance_rows = build_significance_rows(raw_rows, args.runs)

    write_csv(
        OUTPUT_RAW,
        raw_rows,
        [
            "run_id",
            "noise_seed",
            "capacity_low",
            "capacity_high",
            "failure_facility",
            "method_label",
            "evacuation_time_s",
            "queueing_time_person_s",
            "moderate_congestion_exposure_time_person_s",
            "severe_congestion_exposure_time_person_s",
            "peak_density_p_per_m2",
            "avg_speed_m_per_s",
            "wall_clock_runtime_s",
        ],
    )
    write_csv(
        OUTPUT_SUMMARY,
        summary_rows,
        [
            "method_label",
            "metric_key",
            "metric_label",
            "mean",
            "std",
            "min",
            "q1",
            "median",
            "q3",
            "max",
        ],
    )
    write_csv(
        OUTPUT_SIGNIFICANCE,
        significance_rows,
        [
            "comparison",
            "metric_key",
            "metric_label",
            "mean_delta_our_minus_baseline",
            "median_delta_our_minus_baseline",
            "wins_our",
            "ties",
            "losses_our",
            "win_rate_our",
            "permutation_p_value",
            "bootstrap_ci95_low",
            "bootstrap_ci95_high",
        ],
    )
    draw_boxplots(raw_rows)
    OUTPUT_REPORT.write_text(
        build_report(
            summary_rows,
            significance_rows,
            args.runs,
            args.capacity_low,
            args.capacity_high,
            failure_facility=args.failure_facility,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT_RAW.name}")
    print(f"Wrote {OUTPUT_SUMMARY.name}")
    print(f"Wrote {OUTPUT_SIGNIFICANCE.name}")
    print(f"Wrote {OUTPUT_BOXPLOT.name}")
    print(f"Wrote {OUTPUT_REPORT.name}")


if __name__ == "__main__":
    main()
