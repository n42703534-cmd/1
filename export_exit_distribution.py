"""Export detailed exit distribution by source group for Mode 1 and Mode 4.

Outputs one CSV per scenario with columns:
    mode, method, source_group, line, source_type, source_zone,
    configured_people, total_evacuated, exit_name, people_to_exit, pct_of_group
"""
from datetime import datetime
from pathlib import Path

import pandas as pd

import network

BASE_LOADS = {
    "L2": {"platform_waiting": 236, "hall_people": 350, "transfer_people": 526},
    "L7": {"platform_waiting": 219, "hall_people": 112, "transfer_people": 169},
    "L16": {"platform_waiting": 42, "hall_people": 15, "transfer_people": 27},
    "L18": {"platform_waiting": 178, "hall_people": 125, "transfer_people": 188},
    "Maglev": {"platform_waiting": 0, "hall_people": 0, "transfer_people": 0},
}

SCENARIOS = {1: "mode1", 4: "mode4"}

METHODS = [
    ("AdaptiveQueueAwareAStar", network.OUR_SINGLE_PATH_METHOD),
]


def build_pop(mode):
    pop = {}
    total = 0
    for line, physics in network.TRAIN_PHYSICS.items():
        base = BASE_LOADS[line]
        train_total = int(round(network._train_total_people(physics)))
        if mode == 1:
            t1, t2 = 0, 0
        elif mode == 4:
            t1, t2 = train_total, train_total
        else:
            raise ValueError(f"unsupported mode: {mode}")
        pop[line] = {
            "train_1": t1,
            "train_2": t2,
            "platform_waiting": int(base["platform_waiting"]),
            "hall_people": int(base["hall_people"]),
            "transfer_people": int(base["transfer_people"]),
        }
        total += sum(pop[line].values())
    return pop, total


def main():
    run_dir = Path("outputs") / (
        "exit_distribution_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"OUTPUT: {run_dir.resolve()}", flush=True)

    for mode, scenario_label in SCENARIOS.items():
        pop, total_people = build_pop(mode)
        print(f"\n=== MODE {mode} ({scenario_label}) total={total_people} ===", flush=True)

        all_rows = []
        for method_label, method in METHODS:
            print(f"  Running {method_label} ...", flush=True)
            graph = network.build_graph()
            metrics = network.run_simulation_for_metrics_timed(graph, pop, method=method)
            rows = network.build_exit_source_group_rows(metrics, method_label=method_label)

            # Add scenario info
            for r in rows:
                r["scenario_mode"] = mode
                r["scenario_label"] = scenario_label
                r["total_people"] = total_people
                r["pct_of_group"] = r["share_within_group"]  # already 0-1 fraction

            all_rows.extend(rows)
            print(f"    {len(rows)} source->exit records", flush=True)

        if all_rows:
            df = pd.DataFrame(all_rows)
            # Reorder columns
            col_order = [
                "scenario_mode", "scenario_label", "total_people",
                "method_label", "source_group", "line", "source_type",
                "source_zone", "configured_people", "evacuated_people",
                "exit_name", "people", "pct_of_group",
            ]
            df = df[[c for c in col_order if c in df.columns]]
            csv_path = run_dir / f"{scenario_label}_exit_by_source_group.csv"
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            print(f"  Saved {len(df)} rows -> {csv_path.name}", flush=True)

            # Print summary
            print(f"\n  --- {scenario_label} exit share summary ---")
            pivot = df.pivot_table(
                values="pct_of_group",
                index=["line", "source_type"],
                columns="method_label",
                aggfunc="sum",
            )
            print(pivot.to_string(), flush=True)

    print(f"\nDONE: {run_dir.resolve()}", flush=True)


if __name__ == "__main__":
    main()
