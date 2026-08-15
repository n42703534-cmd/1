import time

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd

import network
import single_path_routing as spr


ALGORITHM_METHODS = [
    network.PAPER_SINGLE_PATH_METHOD,
    network.OUR_SINGLE_PATH_METHOD,
]
EVACUEES = 100.0
LINE_START_ZONES = {
    "L2": ["Platform_L2_Z1_Wait", "Platform_L2_Z2_Wait", "Platform_L2_Z3_Wait", "Platform_L2_Z4_Wait"],
    "L7": ["Platform_L7_C1_Wait", "Platform_L7_C3_Wait", "Platform_L7_C5_Wait", "Platform_L7_C6_Wait"],
    "L18": ["Platform_L18_C1_Wait", "Platform_L18_C3_Wait", "Platform_L18_C5_Wait", "Platform_L18_C6_Wait"],
}
METHOD_ORDER = ["ImprovedAStar", "AdaptiveQueueAwareAStar"]


def build_algorithm_cases():
    cases = []
    for line_id, origins in LINE_START_ZONES.items():
        for origin in origins:
            zone_name = origin.replace(f"Platform_{line_id}_", "").replace("_Wait", "")
            cases.append(
                {
                    "case_id": f"{line_id}_{zone_name}",
                    "line": line_id,
                    "origin": origin,
                    "start_role": "platform_zone",
                }
            )
    return cases


ALGORITHM_CASES = build_algorithm_cases()


def method_label(method):
    return network._method_display_name(method)


def path_to_text(path):
    if not path:
        return "N/A"
    return " -> ".join(path)


def dominant_exit_for_line(metrics, line_id):
    exit_usage = metrics.get("exit_usage_by_line", {})
    best_exit = None
    best_flow = -1.0
    for exit_name, by_line in exit_usage.items():
        flow = float(by_line.get(line_id, 0.0))
        if flow > best_flow:
            best_flow = flow
            best_exit = exit_name
    return best_exit


def evaluate_case(G_base, case_spec, method):
    case_state = network.build_single_path_case_state(G_base, case_spec, evacuees=EVACUEES)
    shortest_dists = dict(nx.all_pairs_dijkstra_path_length(case_state, weight="length"))

    t0 = time.perf_counter()
    candidates = spr.enumerate_exit_paths(case_state, case_spec["origin"], method, shortest_dists, network.fruin_speed)
    planning_time_ms = (time.perf_counter() - t0) * 1000.0
    if not candidates:
        raise RuntimeError(f"No feasible path for {case_spec['case_id']} / {method}")

    chosen = candidates[0]
    chosen_path = chosen["path"]
    predicted_exit = chosen["target"]
    predicted_cost = float(chosen["cost"])
    predicted_path_length = network._path_total_length(case_state, chosen_path)

    metrics = network.run_simulation_for_fixed_path_state(
        case_state,
        chosen_path,
        method=method,
        target_by_line={case_spec["line"]: float(EVACUEES)},
    )

    return {
        "case_id": case_spec["case_id"],
        "line": case_spec["line"],
        "origin": case_spec["origin"],
        "start_role": case_spec["start_role"],
        "evacuees": float(EVACUEES),
        "method": spr.normalize_method(method),
        "method_label": method_label(method),
        "planning_time_ms": planning_time_ms,
        "predicted_exit": predicted_exit,
        "predicted_cost": predicted_cost,
        "predicted_path_length": predicted_path_length,
        "predicted_path": path_to_text(chosen_path),
        "actual_exit": dominant_exit_for_line(metrics, case_spec["line"]),
        "actual_evacuation_time": float(metrics["time"]),
        "actual_queueing_time": float(metrics["queueing_time"]),
        "actual_congestion_exposure": float(metrics["congestion_exposure_time"]),
        "avg_speed": float(metrics["avg_speed"]),
    }


def attach_oracle_metrics(case_df):
    oracle_df = (
        case_df.sort_values(
            [
                "case_id",
                "actual_evacuation_time",
                "actual_queueing_time",
                "actual_congestion_exposure",
                "planning_time_ms",
            ]
        )
        .groupby("case_id", as_index=False)
        .first()
    )
    oracle_df = oracle_df.rename(
        columns={
            "method_label": "oracle_method",
            "predicted_exit": "oracle_exit",
            "predicted_path": "oracle_path",
            "actual_evacuation_time": "oracle_actual_evacuation_time",
            "actual_queueing_time": "oracle_actual_queueing_time",
            "actual_congestion_exposure": "oracle_actual_congestion_exposure",
        }
    )

    merged = case_df.merge(
        oracle_df[
            [
                "case_id",
                "oracle_method",
                "oracle_exit",
                "oracle_path",
                "oracle_actual_evacuation_time",
                "oracle_actual_queueing_time",
                "oracle_actual_congestion_exposure",
            ]
        ],
        on="case_id",
        how="left",
    )
    merged["exit_hit"] = (merged["predicted_exit"] == merged["oracle_exit"]).astype(int)
    merged["path_hit"] = (merged["predicted_path"] == merged["oracle_path"]).astype(int)
    merged["regret_time"] = merged["actual_evacuation_time"] - merged["oracle_actual_evacuation_time"]
    merged["regret_queue"] = merged["actual_queueing_time"] - merged["oracle_actual_queueing_time"]
    merged["regret_exposure"] = merged["actual_congestion_exposure"] - merged["oracle_actual_congestion_exposure"]
    return merged


def build_summary(case_df):
    return (
        case_df.groupby(["method", "method_label"])
        .agg(
            case_count=("case_id", "count"),
            mean_planning_time_ms=("planning_time_ms", "mean"),
            mean_predicted_cost=("predicted_cost", "mean"),
            mean_actual_evacuation_time=("actual_evacuation_time", "mean"),
            mean_actual_queueing_time=("actual_queueing_time", "mean"),
            mean_actual_congestion_exposure=("actual_congestion_exposure", "mean"),
            mean_regret_time=("regret_time", "mean"),
            mean_regret_queue=("regret_queue", "mean"),
            mean_regret_exposure=("regret_exposure", "mean"),
            exit_hit_rate=("exit_hit", "mean"),
            path_hit_rate=("path_hit", "mean"),
        )
        .reset_index()
        .sort_values("mean_actual_evacuation_time")
    )


def build_line_summary(case_df):
    return (
        case_df.groupby(["line", "method", "method_label"])
        .agg(
            case_count=("case_id", "count"),
            mean_planning_time_ms=("planning_time_ms", "mean"),
            mean_predicted_cost=("predicted_cost", "mean"),
            mean_actual_evacuation_time=("actual_evacuation_time", "mean"),
            mean_actual_queueing_time=("actual_queueing_time", "mean"),
            mean_actual_congestion_exposure=("actual_congestion_exposure", "mean"),
            mean_regret_time=("regret_time", "mean"),
            mean_regret_queue=("regret_queue", "mean"),
            mean_regret_exposure=("regret_exposure", "mean"),
            exit_hit_rate=("exit_hit", "mean"),
            path_hit_rate=("path_hit", "mean"),
        )
        .reset_index()
        .sort_values(["line", "mean_actual_evacuation_time"])
    )


def build_pairwise_delta(case_df):
    wide = case_df.pivot_table(
        index=["case_id", "line", "origin", "start_role"],
        columns="method_label",
        values=[
            "actual_evacuation_time",
            "actual_queueing_time",
            "actual_congestion_exposure",
            "planning_time_ms",
            "exit_hit",
            "regret_time",
        ],
        aggfunc="first",
    )
    wide.columns = [f"{metric}_{label}" for metric, label in wide.columns]
    wide = wide.reset_index()

    for rival in ["ImprovedAStar"]:
        wide[f"time_gap_{rival}_minus_our"] = wide[f"actual_evacuation_time_{rival}"] - wide["actual_evacuation_time_AdaptiveQueueAwareAStar"]
        wide[f"queue_gap_{rival}_minus_our"] = wide[f"actual_queueing_time_{rival}"] - wide["actual_queueing_time_AdaptiveQueueAwareAStar"]
        wide[f"exposure_gap_{rival}_minus_our"] = wide[f"actual_congestion_exposure_{rival}"] - wide["actual_congestion_exposure_AdaptiveQueueAwareAStar"]
    return wide


def plot_summary(case_df, summary_df, line_summary_df, plot_file):
    colors = {
        "ImprovedAStar": "#F28E2B",
        "AdaptiveQueueAwareAStar": "#E15759",
    }

    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    axes = axes.flatten()
    metric_specs = [
        ("mean_planning_time_ms", "Planning time (ms)"),
        ("mean_actual_evacuation_time", "Actual evacuation time (s)"),
        ("mean_actual_queueing_time", "Actual queueing time (person*s)"),
        ("mean_actual_congestion_exposure", "Actual congestion exposure (person*s)"),
        ("path_hit_rate", "Path hit rate"),
        ("mean_regret_time", "Time regret (s)"),
    ]

    for ax, (metric, title) in zip(axes, metric_specs):
        xs = range(len(METHOD_ORDER))
        ys = [float(summary_df.loc[summary_df["method_label"] == label, metric].iloc[0]) for label in METHOD_ORDER]
        ax.bar(xs, ys, color=[colors[label] for label in METHOD_ORDER], edgecolor="black")
        ax.set_xticks(list(xs))
        ax.set_xticklabels(METHOD_ORDER, rotation=20, ha="right")
        ax.set_title(title)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        if metric == "path_hit_rate":
            ax.set_ylim(0, 1.05)
    plt.tight_layout()
    plt.savefig(plot_file, dpi=300, bbox_inches="tight")
    plt.close()

    case_plot_file = plot_file.replace(".png", "_by_case.png")
    pivot = case_df.pivot(index="case_id", columns="method_label", values="actual_evacuation_time").reindex(
        [c["case_id"] for c in ALGORITHM_CASES]
    )
    fig, ax = plt.subplots(figsize=(16, 5.5))
    x = range(len(pivot.index))
    width = 0.18
    for idx, label in enumerate(METHOD_ORDER):
        vals = pivot[label].to_list()
        offset = (idx - (len(METHOD_ORDER) - 1) / 2.0) * width
        ax.bar([v + offset for v in x], vals, width=width, color=colors[label], edgecolor="black", label=label)
    ax.set_xticks(list(x))
    ax.set_xticklabels(list(pivot.index), rotation=20, ha="right")
    ax.set_ylabel("Actual evacuation time (s)")
    ax.set_title("Algorithm-layer case comparison")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.legend()
    plt.tight_layout()
    plt.savefig(case_plot_file, dpi=300, bbox_inches="tight")
    plt.close()

    line_plot_file = plot_file.replace(".png", "_by_line.png")
    lines = list(LINE_START_ZONES.keys())
    fig, axes = plt.subplots(1, len(lines), figsize=(5.2 * len(lines), 4.8), sharey=True)
    axes = [axes] if len(lines) == 1 else list(axes)
    for ax, line_id in zip(axes, lines):
        sub = line_summary_df[line_summary_df["line"] == line_id]
        xs = range(len(METHOD_ORDER))
        ys = [float(sub.loc[sub["method_label"] == label, "mean_actual_evacuation_time"].iloc[0]) for label in METHOD_ORDER]
        ax.bar(xs, ys, color=[colors[label] for label in METHOD_ORDER], edgecolor="black")
        ax.set_xticks(list(xs))
        ax.set_xticklabels(METHOD_ORDER, rotation=20, ha="right")
        ax.set_title(f"{line_id} mean evacuation time")
        ax.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.savefig(line_plot_file, dpi=300, bbox_inches="tight")
    plt.close()
    return case_plot_file, line_plot_file


def format_float(value, digits=2):
    if pd.isna(value):
        return "N/A"
    return f"{float(value):.{digits}f}"


def markdown_table(headers, rows):
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return lines


def write_report(case_df, summary_df, line_summary_df, delta_df, report_file):
    best_time = summary_df.sort_values("mean_actual_evacuation_time").iloc[0]
    best_queue = summary_df.sort_values("mean_actual_queueing_time").iloc[0]
    best_exposure = summary_df.sort_values("mean_actual_congestion_exposure").iloc[0]
    best_path_hit = summary_df.sort_values("path_hit_rate", ascending=False).iloc[0]
    method_rows = summary_df.set_index("method_label").loc[METHOD_ORDER].reset_index()

    lines = [
        "# 三条代表线路的自适应引导算法层对比报告",
        "",
        "本文只比较自适应引导算法层，不讨论全站引导和分流。每个案例固定 100 人，从选定等待区起步，由算法自行决定目标出口和完整路径，再在同一网络模型中执行仿真，统计规划和运行结果。",
        "",
        "## 1. 实验设计",
        "",
        f"- 代表线路：`{', '.join(LINE_START_ZONES.keys())}`。",
        f"- 起点数量：`{len(ALGORITHM_CASES)}`，每条线各 `4` 个等待区起点。",
        f"- 单案例人数：`{int(EVACUEES)}` 人。",
        f"- 对比方法：`{', '.join(METHOD_ORDER)}`。",
        "- 输出字段：起点、目标出口、完整路径、算法耗时、预测代价、实际疏散时间、实际排队、实际拥挤暴露、命中率和 regret。",
        "- `predicted_cost` 只用于各算法内部候选路径排序，不能跨算法直接比较绝对值。",
        "- 命中率口径：同一起点下，以两种算法真实执行结果中“实际疏散时间最优、若并列则依次比较排队、暴露、算法耗时”的方案作为 oracle。",
        "- regret 口径：本算法该指标减去 oracle 方案对应指标，`0` 表示已命中最优方案。",
        "",
        "## 2. 总览图",
        "",
        "![总体指标](139_algorithm_layer_metrics.png)",
        "",
        "![逐案例疏散时间](139_algorithm_layer_metrics_by_case.png)",
        "",
        "![分线路疏散时间](139_algorithm_layer_metrics_by_line.png)",
        "",
        "## 3. 总体汇总",
        "",
    ]

    overall_rows = []
    for _, row in method_rows.iterrows():
        overall_rows.append(
            [
                row["method_label"],
                int(row["case_count"]),
                format_float(row["mean_planning_time_ms"]),
                format_float(row["mean_predicted_cost"]),
                format_float(row["mean_actual_evacuation_time"]),
                format_float(row["mean_actual_queueing_time"]),
                format_float(row["mean_actual_congestion_exposure"]),
                f"{float(row['exit_hit_rate']):.2%}",
                f"{float(row['path_hit_rate']):.2%}",
                format_float(row["mean_regret_time"]),
                format_float(row["mean_regret_queue"]),
                format_float(row["mean_regret_exposure"]),
            ]
        )
    lines.extend(
        markdown_table(
            [
                "方法",
                "案例数",
                "算法耗时 (ms)",
                "预测代价",
                "实际疏散时间 (s)",
                "实际排队 (person*s)",
                "实际拥挤暴露 (person*s)",
                "出口命中率",
                "路径命中率",
                "时间 regret (s)",
                "排队 regret",
                "暴露 regret",
            ],
            overall_rows,
        )
    )

    lines.extend(
        [
            "",
            "### 总体结论",
            f"- 平均实际疏散时间最优的是 `{best_time['method_label']}`，均值为 `{format_float(best_time['mean_actual_evacuation_time'])}s`。",
            f"- 平均实际排队最优的是 `{best_queue['method_label']}`，均值为 `{format_float(best_queue['mean_actual_queueing_time'])}`。",
            f"- 平均实际拥挤暴露最优的是 `{best_exposure['method_label']}`，均值为 `{format_float(best_exposure['mean_actual_congestion_exposure'])}`。",
            f"- 路径命中率最高的是 `{best_path_hit['method_label']}`，命中率为 `{float(best_path_hit['path_hit_rate']):.2%}`。",
            "",
            "## 4. 线路级汇总",
            "",
        ]
    )

    line_rows = []
    for line_id in LINE_START_ZONES.keys():
        line_sub = line_summary_df[line_summary_df["line"] == line_id].set_index("method_label").loc[METHOD_ORDER].reset_index()
        for _, row in line_sub.iterrows():
            line_rows.append(
                [
                    line_id,
                    row["method_label"],
                    int(row["case_count"]),
                    format_float(row["mean_planning_time_ms"]),
                    format_float(row["mean_actual_evacuation_time"]),
                    format_float(row["mean_actual_queueing_time"]),
                    format_float(row["mean_actual_congestion_exposure"]),
                    f"{float(row['path_hit_rate']):.2%}",
                    format_float(row["mean_regret_time"]),
                ]
            )
    lines.extend(
        markdown_table(
            [
                "线路",
                "方法",
                "案例数",
                "算法耗时 (ms)",
                "实际疏散时间 (s)",
                "实际排队 (person*s)",
                "实际拥挤暴露 (person*s)",
                "路径命中率",
                "时间 regret (s)",
            ],
            line_rows,
        )
    )

    for line_index, line_id in enumerate(LINE_START_ZONES.keys(), start=5):
        line_case_df = case_df[case_df["line"] == line_id].copy()
        line_summary_sub = line_summary_df[line_summary_df["line"] == line_id].set_index("method_label").loc[METHOD_ORDER].reset_index()
        best_line = line_summary_sub.sort_values("mean_actual_evacuation_time").iloc[0]
        best_line_exposure = line_summary_sub.sort_values("mean_actual_congestion_exposure").iloc[0]
        best_line_hit = line_summary_sub.sort_values("path_hit_rate", ascending=False).iloc[0]

        lines.extend(
            [
                "",
                f"## {line_index}. {line_id} 线路",
                "",
                "### 场景设计",
                f"- 起点：`{', '.join(LINE_START_ZONES[line_id])}`。",
                f"- 单个起点人数：`{int(EVACUEES)}` 人。",
                "- 每个起点由四种算法分别生成完整路径，并独立执行仿真。",
                "",
                "### 过程与结果",
                f"- 平均实际疏散时间最优：`{best_line['method_label']}` = `{format_float(best_line['mean_actual_evacuation_time'])}s`。",
                f"- 平均实际拥挤暴露最优：`{best_line_exposure['method_label']}` = `{format_float(best_line_exposure['mean_actual_congestion_exposure'])}`。",
                f"- 路径命中率最高：`{best_line_hit['method_label']}` = `{float(best_line_hit['path_hit_rate']):.2%}`。",
                "",
                f"### {line_id} 逐案例完整结果",
                "",
            ]
        )

        case_rows = []
        ordered_case_ids = [spec["case_id"] for spec in ALGORITHM_CASES if spec["line"] == line_id]
        for case_id in ordered_case_ids:
            case_sub = line_case_df[line_case_df["case_id"] == case_id].set_index("method_label").loc[METHOD_ORDER].reset_index()
            for _, row in case_sub.iterrows():
                case_rows.append(
                    [
                        row["case_id"],
                        row["origin"],
                        row["method_label"],
                        row["predicted_exit"],
                        row["predicted_path"],
                        format_float(row["planning_time_ms"]),
                        format_float(row["predicted_cost"], 3),
                        format_float(row["actual_evacuation_time"]),
                        format_float(row["actual_queueing_time"]),
                        format_float(row["actual_congestion_exposure"]),
                        f"{int(row['exit_hit'])}/{int(row['path_hit'])}",
                        format_float(row["regret_time"]),
                        format_float(row["regret_queue"]),
                        format_float(row["regret_exposure"]),
                    ]
                )
        lines.extend(
            markdown_table(
                [
                    "案例",
                    "起点",
                    "方法",
                    "目标出口",
                    "完整路径",
                    "算法耗时 (ms)",
                    "预测代价",
                    "实际疏散时间 (s)",
                    "实际排队 (person*s)",
                    "实际拥挤暴露 (person*s)",
                    "命中率 (出口/路径)",
                    "时间 regret (s)",
                    "排队 regret",
                    "暴露 regret",
                ],
                case_rows,
            )
        )

    lines.extend(
        [
            "",
            f"## {5 + len(LINE_START_ZONES)}. AdaptiveQueueAwareAStar 相对基线",
            "",
            f"- 相对 `ImprovedAStar`：平均时间差 `{format_float(delta_df['time_gap_ImprovedAStar_minus_our'].mean())}s`，平均排队差 `{format_float(delta_df['queue_gap_ImprovedAStar_minus_our'].mean())}`，平均暴露差 `{format_float(delta_df['exposure_gap_ImprovedAStar_minus_our'].mean())}`。",
            "",
            f"## {6 + len(LINE_START_ZONES)}. 总结",
            "",
            "- 这一组实验只验证自适应引导算法层，因此更适合看“路径选择是否稳、是否选中较优出口与完整路径”，不直接外推到全站协同引导。",
            "- 如果后续进入系统层，还需要把这里的单路径结果与全站同时疏散、瓶颈峰值和出口均衡性结合起来看。",
        ]
    )

    with open(report_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    G_base = network.build_graph()
    rows = []
    for case_spec in ALGORITHM_CASES:
        for method in ALGORITHM_METHODS:
            rows.append(evaluate_case(G_base, case_spec, method))

    case_df = pd.DataFrame(rows)
    case_df = attach_oracle_metrics(case_df)
    summary_df = build_summary(case_df)
    line_summary_df = build_line_summary(case_df)
    delta_df = build_pairwise_delta(case_df)

    case_file = "135_algorithm_layer_case_summary.csv"
    summary_file = "136_algorithm_layer_summary_by_method.csv"
    line_summary_file = "137_algorithm_layer_summary_by_line.csv"
    delta_file = "138_algorithm_layer_pairwise_deltas.csv"
    plot_file = "139_algorithm_layer_metrics.png"
    report_file = "140_algorithm_layer_report.md"

    case_df.to_csv(case_file, index=False, encoding="utf-8-sig")
    summary_df.to_csv(summary_file, index=False, encoding="utf-8-sig")
    line_summary_df.to_csv(line_summary_file, index=False, encoding="utf-8-sig")
    delta_df.to_csv(delta_file, index=False, encoding="utf-8-sig")
    case_plot_file, line_plot_file = plot_summary(case_df, summary_df, line_summary_df, plot_file)
    write_report(case_df, summary_df, line_summary_df, delta_df, report_file)

    print(case_file)
    print(summary_file)
    print(line_summary_file)
    print(delta_file)
    print(plot_file)
    print(case_plot_file)
    print(line_plot_file)
    print(report_file)


if __name__ == "__main__":
    main()
