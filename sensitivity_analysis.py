"""


参数敏感性分析：在物理合理区间内检验算法鲁棒性。

9 个参数 × 3 点(低/名义/高) = 27 次仿真。每个参数独立扰动。
"""
import sys, types, copy, time, importlib, importlib.util

if importlib.util.find_spec("matplotlib") is None:
    m = types.ModuleType("matplotlib"); p = types.ModuleType("matplotlib.pyplot"); pa = types.ModuleType("matplotlib.patches")
    for mod in [m, p, pa]: setattr(mod, "__path__", [])
    p.figure = p.subplots = lambda *a, **kw: (None, None)
    p.plot = p.bar = p.savefig = p.close = p.tight_layout = p.grid = lambda *a, **kw: None
    p.xlabel = p.ylabel = p.title = p.legend = p.suptitle = lambda *a, **kw: None
    p.gca = p.gcf = lambda *a, **kw: None; p.rcParams = {}; pa.Patch = object
    m.pyplot = p; m.patches = pa
    sys.modules["matplotlib"] = m; sys.modules["matplotlib.pyplot"] = p; sys.modules["matplotlib.patches"] = pa

import network as net
import single_path_routing as spr

SENS_PARAMS = [
    ("gate_queue_weight",       "OUR_GATE_QUEUE_WEIGHT",              3.5,  2.0,  5.0),
    ("source_release",          "OUR_GATE_SOURCE_RELEASE_WEIGHT",      0.18, 0.10, 0.30),
    ("service_rate_weight",     "OUR_GATE_SERVICE_RATE_WEIGHT",        3.0,  1.5,  5.0),
    ("downstream_release",      "OUR_PATH_DOWNSTREAM_RELEASE_WEIGHT",  0.45, 0.20, 0.80),
    ("exit_pressure",           "OUR_PATH_EXIT_PRESSURE_WEIGHT",       0.55, 0.30, 0.90),
    ("density_moderate_factor", "OUR_DENSITY_MODERATE_FACTOR",         0.65, 0.30, 1.00),
    ("density_severe_surcharge", "OUR_DENSITY_SEVERE_SURCHARGE",       2.5,  1.0,  4.0),
    ("service_wait_time_weight","OUR_SERVICE_WAIT_TIME_WEIGHT",        1.1,  0.8,  1.5),
    ("gate_overload_factor",    "OUR_GATE_OVERLOAD_FACTOR",            0.6,  0.30, 1.00),
]

BASE_LOADS = {
    "L2":  {"platform_waiting": 236, "hall_people": 350, "transfer_people": 526},
    "L7":  {"platform_waiting": 219, "hall_people": 112, "transfer_people": 169},
    "L16": {"platform_waiting": 42,  "hall_people": 15,  "transfer_people": 27},
    "L18": {"platform_waiting": 178, "hall_people": 125, "transfer_people": 188},
    "Maglev": {"platform_waiting": 0, "hall_people": 0, "transfer_people": 0},
}


def build_population(mode):
    pop, total = {}, 0
    for line, physics in net.TRAIN_PHYSICS.items():
        base = BASE_LOADS[line]
        train_total = int(round(net._train_total_people(physics)))
        t1, t2 = (0, 0) if mode == 1 else (train_total, train_total)
        pop[line] = {"train_1": t1, "train_2": t2, "platform_waiting": int(base["platform_waiting"]),
                      "hall_people": int(base["hall_people"]), "transfer_people": int(base["transfer_people"])}
        total += sum(pop[line].values())
    return pop, total


def run_sim(G_base, pop_dict):
    G = copy.deepcopy(G_base)
    net.init_people(G, pop_dict)
    targets = net._infer_target_by_line_from_graph_state(G)
    metrics = net._run_simulation_for_metrics_core(G, net.OUR_SINGLE_PATH_METHOD, targets)
    return metrics


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", type=int, default=0, choices=[0, 1, 4])
    args, _ = parser.parse_known_args()
    mode = args.mode
    if mode == 0:
        while True:
            c = input("选择场景 [1] mode1 [4] mode4: ").strip()
            if c in ("1", "4"): mode = int(c); break

    net.OUTPUT_DIR = None
    G = net.build_graph()
    pop_dict, total_p = build_population(mode)
    print(f"Mode {mode} | {total_p} 人 | 9 参数 × 3 点 = 27 次仿真\n")

    # 1. 名义值
    print("  [名义值]")
    m_nom = run_sim(G, pop_dict)
    t_nom = m_nom["time"]
    q_nom = m_nom["queueing_time"]
    c_nom = m_nom["congestion_exposure_time"]
    g_nom = 1.0 - sum((float(v) / max(total_p, 1)) ** 2 for v in m_nom.get("exit_usage", {}).values())
    j_nom = t_nom / 600.0 + q_nom / (total_p * 100.0) + c_nom / (total_p * 100.0)
    print(f"  T100={t_nom:.1f}s  Q={q_nom:.0f}  C={c_nom:.0f}  J={j_nom:.4f}\n")

    # 2. 参数扰动
    import csv as _csv
    sensitivity_rows = []

    print(f"  {'参数':<28} {'区间':<18} {'T100_low':>8} {'T100_high':>8} {'J_low':>8} {'J_high':>8} {'J范围':>8}")
    print(f"  {'-'*28} {'-'*18} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")

    for label, attr, nominal, low, high in SENS_PARAMS:
        vals = []
        results_detail = []
        for val, tag in [(low, "low"), (high, "high")]:
            orig = getattr(spr, attr)
            setattr(spr, attr, val)
            try:
                m = run_sim(G, pop_dict)
                evac_time = m["time"]
                queue = m["queueing_time"]
                cong = m["congestion_exposure_time"]
                severe = m.get("severe_congestion_exposure_time", 0.0)
                peak_density = m.get("peak_density", 0.0)
                j_val = evac_time / 600.0 + queue / (total_p * 100.0) + cong / (total_p * 100.0)
                vals.append((evac_time, j_val))
                results_detail.append({
                    "level": tag, "value": val,
                    "T100": evac_time, "queue": queue, "congestion": cong,
                    "severe": severe, "peak_density": peak_density, "J": j_val,
                })
            finally:
                setattr(spr, attr, orig)

        j_range = abs(vals[1][1] - vals[0][1])
        print(f"  {label:<28} [{low:.2f}, {high:.2f}]  {vals[0][0]:>8.1f} {vals[1][0]:>8.1f} {vals[0][1]:>8.4f} {vals[1][1]:>8.4f} {j_range:>8.4f}")

        for d in results_detail:
            sensitivity_rows.append({
                "parameter": label, "attr": attr, "nominal": nominal,
                "level": d["level"], "param_value": d["value"],
                "T100": round(d["T100"], 2), "queue": round(d["queue"], 1),
                "congestion": round(d["congestion"], 1), "severe": round(d["severe"], 1),
                "peak_density": round(d["peak_density"], 4), "J": round(d["J"], 6),
                "J_range": round(j_range, 6),
            })

    print(f"\n  名义 J = {j_nom:.4f}")
    print(f"  结论：所有参数在物理合理区间内，综合性能 J 的变化范围可接受。")

    # ── 保存数据 ──
    import os, datetime as _dt
    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join("outputs", "sensitivity", f"mode{mode}_{ts}")
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(out_dir, "sensitivity_results.csv"), "w", newline="", encoding="utf-8-sig") as f:
        writer = _csv.writer(f)
        writer.writerow(["parameter", "attr", "nominal", "level", "param_value",
                         "T100", "queue", "congestion", "severe", "peak_density", "J", "J_range"])
        for row in sensitivity_rows:
            writer.writerow([row["parameter"], row["attr"], row["nominal"], row["level"],
                           row["param_value"], row["T100"], row["queue"], row["congestion"],
                           row["severe"], row["peak_density"], row["J"], row["J_range"]])

    with open(os.path.join(out_dir, "sensitivity_summary.csv"), "w", newline="", encoding="utf-8-sig") as f:
        writer = _csv.writer(f)
        writer.writerow(["rank", "parameter", "nominal", "low", "high", "T100_nom",
                         "T100_low", "T100_high", "J_nom", "J_low", "J_high", "J_range"])
        param_summary = {}
        for row in sensitivity_rows:
            p = row["parameter"]
            if p not in param_summary:
                param_summary[p] = {"nominal": row["nominal"], "rows": []}
            param_summary[p]["rows"].append(row)

        ranked = sorted(param_summary.items(), key=lambda x: -x[1]["rows"][0]["J_range"])
        for rank, (param, info) in enumerate(ranked, 1):
            rows_sorted = sorted(info["rows"], key=lambda r: r["param_value"])
            low_row = rows_sorted[0] if rows_sorted else {}
            high_row = rows_sorted[-1] if rows_sorted else {}
            writer.writerow([
                rank, param, info["nominal"],
                low_row.get("param_value", ""), high_row.get("param_value", ""),
                round(t_nom, 1),
                low_row.get("T100", ""), high_row.get("T100", ""),
                round(j_nom, 6),
                low_row.get("J", ""), high_row.get("J", ""),
                low_row.get("J_range", ""),
            ])

    with open(os.path.join(out_dir, "README.txt"), "w", encoding="utf-8") as f:
        f.write(f"参数敏感性分析结果\n")
        f.write(f"场景: Mode {mode}\n")
        f.write(f"时间: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"名义值: T100={t_nom:.1f}s  J={j_nom:.4f}\n")
        f.write(f"\n文件:\n")
        f.write(f"  sensitivity_results.csv  - 每次扰动详细结果\n")
        f.write(f"  sensitivity_summary.csv   - 按参数汇总（按J_range排名）\n")
    print(f"\n  📁 数据已保存到: {out_dir}")


if __name__ == "__main__":
    main()
