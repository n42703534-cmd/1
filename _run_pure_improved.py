# 对照实验：纯 Improved(Meng 原版，improved_gate_queue_term=False)，mode4。
# 复现 run_system_mode_workflow 的 mode4 人口与配置；只跑 Improved，不跑 AA。
# 跑完把关键三项写入 _pure_improved_result.txt。跑完即删。
import os
import sys

os.environ.setdefault("IMPROVED_GATE_QUEUE_TERM", "0")
import network as net

# run_system_mode_workflow 的 mode4 基础人口
STATION_BASE_LOADS = {
    "L2": {"platform_waiting": 236, "hall_people": 350, "transfer_people": 526},
    "L7": {"platform_waiting": 219, "hall_people": 112, "transfer_people": 169},
    "L16": {"platform_waiting": 42, "hall_people": 15, "transfer_people": 27},
    "L18": {"platform_waiting": 178, "hall_people": 125, "transfer_people": 188},
    "Maglev": {"platform_waiting": 0, "hall_people": 0, "transfer_people": 0},
}
pop_dict = {}
for line, physics in net.TRAIN_PHYSICS.items():
    base = STATION_BASE_LOADS[line]
    train_total = int(round(net._train_total_people(physics)))  # mode4: 双向满载
    pop_dict[line] = {
        "train_1": train_total,
        "train_2": train_total,
        "platform_waiting": base["platform_waiting"],
        "hall_people": base["hall_people"],
        "transfer_people": base["transfer_people"],
    }
total = sum(sum(v.values()) for v in pop_dict.values())
print(f"POP_TOTAL={total}", flush=True)
assert total == 17905, f"pop total {total} != 17905 (人口构造与 run_system_mode_workflow 不一致)"

G = net.build_graph()
G.graph["density_dependent_flow"] = True
G.graph["spillback_enabled"] = True
G.graph["improved_gate_queue_term"] = (
    os.environ.get("IMPROVED_GATE_QUEUE_TERM", "1").strip().lower()
    not in {"0", "false", "no", "off"}
)
G.graph["improved_shared_travel_time"] = (
    os.environ.get("IMPROVED_SHARED_TRAVEL_TIME", "1").strip().lower()
    not in {"0", "false", "no", "off"}
)
_tag = ("A2on" if G.graph["improved_shared_travel_time"] else "A2off") + "_" + (
    "Qon" if G.graph["improved_gate_queue_term"] else "Qoff"
)
_cfg = (
    f"shared_travel_time={G.graph['improved_shared_travel_time']} "
    f"gate_queue_term={G.graph['improved_gate_queue_term']}"
)
print("GRAPH_READY " + _cfg + " tag=" + _tag, flush=True)

if os.environ.get("DRY") == "1":
    print("DRY_OK", flush=True)
    sys.exit(0)

m = net.run_simulation_for_metrics(G, pop_dict, method=net.PAPER_SINGLE_PATH_METHOD)

T100 = float(m["time"])
gate_tp = None
for _rid, stat in m["resource_stats"].items():
    if str(stat.get("resource_id")) == "Gate_L7_N_West":
        gate_tp = float(stat.get("total_throughput", 0.0))
        break
curve = m["evacuation_curve"]
t95 = None
for t, rem in zip(curve["times"], curve["remaining"]):
    if float(rem) <= total * 0.05:
        t95 = float(t)
        break
result = (
    f"T100={T100:.0f}  T95={t95}  tail={T100 - (t95 or 0):.0f}  "
    f"Gate_L7_N_West_throughput={gate_tp}  "
    f"completed={m['completed']}  remaining={m['remaining_people']:.0f}"
)
print("RESULT_PURE_IMPROVED " + result, flush=True)
with open(f"_improved_{_tag}_result.txt", "w", encoding="utf-8") as f:
    f.write(f"Improved mode4 [{_cfg}]\n" + result + "\n")
