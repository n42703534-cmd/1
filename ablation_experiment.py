"""Module ablation study for the current AdaptiveQueueAwareAStar implementation.

Each variant changes one planning-layer mechanism only. The network geometry,
population, walking model, facility capacities, finite receiving storage and
spillback executor remain common to every run.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path

import algorithm_comparison as comparison
import network as net
import single_path_routing as spr


VARIANTS = (
    ("Full AA*", {}),
    ("No arrival-time queue prediction", {"aa_resource_queue_prediction_enabled": False}),
    ("No resource-queue waiting cost", {"aa_resource_wait_enabled": False}),
    ("No spatial receiving wait", {"aa_spatial_wait_enabled": False}),
    ("Single-label search", {"aa_search_mode": "single_label"}),
    ("No density-risk penalty", {"aa_safety_weight": 0.0}),
)


def build_base_graph(mode: int):
    graph = net.build_graph()
    graph.graph["improved_gate_queue_term"] = False
    graph.graph["improved_shared_travel_time"] = False
    graph.graph["density_dependent_flow"] = True
    graph.graph["spillback_enabled"] = True
    graph.graph[net.EDGE_RECEIVING_DENSITY_PARAMETER_NAME] = (
        net.EDGE_RECEIVING_DENSITY_LIMIT_P_PER_M2
    )
    graph.graph["aa_reroute_gain_min"] = 0.20
    graph.graph["aa_spatial_batch_arrival_spread_enabled"] = True
    graph.graph["aa_spatial_arrival_spread_seconds"] = 1.0
    if mode == 4:
        graph.graph["split_l2_train_source_groups_by_zone"] = True
    return graph


def result_row(result: dict, variant: str, switches: dict) -> dict:
    return {
        "variant": variant,
        "switches_json": json.dumps(switches, ensure_ascii=False, sort_keys=True),
        "completed": result["completed"],
        "target_people": result["target_people"],
        "evacuated_people": result["evacuated_people"],
        "T50_s": result["eval"]["t50"],
        "T80_s": result["eval"]["t80"],
        "T95_s": result["eval"]["t95"],
        "T99_s": result["eval"]["t99"],
        "T100_s": result["eval"]["t100"],
        "mean_total_evacuation_time_s": result["mean_total_evacuation_time"],
        "stationary_person_s": result["stationary_time"],
        "mean_stationary_time_s": result["mean_stationary_time"],
        "total_movement_distance_m": result["total_movement_distance"],
        "effective_evacuation_speed_m_s": result["effective_evacuation_speed"],
        "exit_load_jain": result["exit_load_jain_index"],
        "key_facility_load_jain": result["key_facility_load_jain_index"],
        "wall_clock_s": result["wall_clock_s"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", type=int, default=4, choices=[1, 4])
    parser.add_argument("--only", nargs="*", help="Optional exact variant names")
    args = parser.parse_args()

    comparison.MODE = args.mode
    net.OUTPUT_DIR = None
    population, total_people = comparison.build_population()
    if args.mode == 4 and total_people != 17905:
        raise RuntimeError(f"Mode 4 population must be 17905, got {total_people}")

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("outputs") / "ablation" / f"mode{args.mode}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    variants = [v for v in VARIANTS if not args.only or v[0] in set(args.only)]

    rows = []
    for index, (name, switches) in enumerate(variants, start=1):
        print(f"[{index}/{len(variants)}] {name}", flush=True)
        graph = build_base_graph(args.mode)
        graph.graph.update(switches)
        result = comparison.run_one(
            graph,
            population,
            net.OUR_SINGLE_PATH_METHOD,
            name,
            collect_detailed_series=False,
        )
        row = result_row(result, name, switches)
        rows.append(row)
        with (output_dir / "ablation_results.csv").open(
            "w", newline="", encoding="utf-8-sig"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(
            f"completed {name}: T95={row['T95_s']:.1f}s "
            f"T100={row['T100_s']:.1f}s stationary={row['stationary_person_s']:.1f} "
            f"runtime={row['wall_clock_s']:.2f}s",
            flush=True,
        )

    manifest = {
        "scenario_mode": args.mode,
        "population": total_people,
        "model_revision": comparison.MODEL_REVISION,
        "physical_executor_invariant": True,
        "variants": [{"name": name, "switches": switches} for name, switches in variants],
    }
    (output_dir / "ablation_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Results saved to {output_dir}", flush=True)


if __name__ == "__main__":
    main()
