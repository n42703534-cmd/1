# 诊断：Improved(纯Meng) mode4 跑动中，记录 Gate_L7_N_West 的换路探测量随时间：
#   闸机节点密度、节点人数、真实排队(_resource_queues)、上游楼扶梯密度、N_West入边是否被判高成本。
# 用来验证"密度>3换路"为何不把人从慢闸机导开。
import os
os.environ.setdefault("IMPROVED_GATE_QUEUE_TERM", "0")
os.environ.setdefault("IMPROVED_SHARED_TRAVEL_TIME", "0")
import network as net
import single_path_routing as spr

records = []


def recorder(G, t, moves, evac):
    if int(round(t)) % 25 != 0:
        return
    st = net._paper_gate_effective_state(G, "Gate_L7_N_West")
    nw_people = float(G.nodes["Gate_L7_N_West"].get("people", 0.0))
    rq = float(G.graph.get("_resource_queues", {}).get(("facility", "Gate_L7_N_West"), 0.0))
    up1 = spr.spatial_effective_density(G, "Escalator_L7_up1")
    s1 = spr.spatial_effective_density(G, "Stair_L7_1")
    hc = G.graph.get("_paper_high_cost_active_edges", set())
    nw_hc = sum(1 for e in hc if len(e) >= 2 and e[1] == "Gate_L7_N_West")
    records.append((t, st["effective_density"], nw_people, rq, up1, s1, nw_hc, len(hc)))


STATION_BASE_LOADS = {
    "L2": {"platform_waiting": 236, "hall_people": 350, "transfer_people": 526},
    "L7": {"platform_waiting": 219, "hall_people": 112, "transfer_people": 169},
    "L16": {"platform_waiting": 42, "hall_people": 15, "transfer_people": 27},
    "L18": {"platform_waiting": 178, "hall_people": 125, "transfer_people": 188},
    "Maglev": {"platform_waiting": 0, "hall_people": 0, "transfer_people": 0},
}
pop = {}
for line, physics in net.TRAIN_PHYSICS.items():
    b = STATION_BASE_LOADS[line]
    tt = int(round(net._train_total_people(physics)))
    pop[line] = {"train_1": tt, "train_2": tt, "platform_waiting": b["platform_waiting"],
                 "hall_people": b["hall_people"], "transfer_people": b["transfer_people"]}

G = net.build_graph()
G.graph["density_dependent_flow"] = True
G.graph["spillback_enabled"] = True
G.graph["improved_shared_travel_time"] = False
G.graph["improved_gate_queue_term"] = False
net.init_people(G, pop, apply_noise=False)
G.graph["_aa_equivalence_observer"] = recorder
targets = {line: sum(d.values()) for line, d in pop.items() if sum(d.values()) > 0}

net._run_simulation_for_metrics_core(G, net.PAPER_SINGLE_PATH_METHOD, targets, stop_at_time=1200.0)

print("\n时间  N_West节点密度  节点人数  真实排队Q  Esc_up1密度  Stair1密度  N_West入边高成本数  全站高成本边")
for r in records:
    print(f"{r[0]:6.0f}  {r[1]:12.2f}  {r[2]:8.0f}  {r[3]:9.0f}  {r[4]:10.2f}  {r[5]:9.2f}  {r[6]:16d}  {r[7]:10d}")
peak_gate_density = max((r[1] for r in records), default=0)
ever_hc = any(r[6] > 0 for r in records)
print(f"\nN_West 闸机节点密度峰值 = {peak_gate_density:.2f}  (阈值 3.0)")
print(f"N_West 入边在整个过程中是否被判过高成本 = {ever_hc}")
with open("_diag_nwest_reroute_result.txt", "w", encoding="utf-8") as f:
    f.write(f"peak_gate_density={peak_gate_density:.2f} ever_high_cost_on_NWest={ever_hc}\n")
    for r in records:
        f.write(f"t={r[0]:.0f} gate_dens={r[1]:.2f} node_ppl={r[2]:.0f} Q={r[3]:.0f} up1_dens={r[4]:.2f} s1_dens={r[5]:.2f} nw_hc={r[6]} total_hc={r[7]}\n")
