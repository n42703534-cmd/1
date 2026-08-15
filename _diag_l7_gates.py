# 只读诊断：L7 四个平行闸机的入边成本对比（A2关 = Meng 走时），
# 看为什么 Improved 把人导向 mu=1.0 的 Gate_L7_N_West 而非 mu=2.78 的 West_Vert。
import network as net
import single_path_routing as spr

G = net.build_graph()
G.graph["density_dependent_flow"] = True
G.graph["spillback_enabled"] = True
G.graph["_sim_time"] = 0.0

l7_gates = sorted(
    n for n in G.nodes
    if ("gate" in str(G.nodes[n].get("type", "")).lower()) and ("L7" in str(n))
)
mu = {g: net.resource_capacity_per_second(G, ("facility", g)) for g in l7_gates}


def cost_a2(G, u, v, a2_on):
    G.graph["improved_shared_travel_time"] = a2_on
    return spr.paper_edge_cost(G, u, v)


upstreams = sorted({u for g in l7_gates for u in G.predecessors(g)})
print("L7 闸机:  " + "  ".join(f"{g.split('Gate_L7_')[-1]}(mu={mu[g]:.2f})" for g in l7_gates))
print("=" * 100)
print("对每个上游节点，列出 ->各闸机 的边长 length | A2关成本(Meng) | A2开成本(引擎)；[*]=该行最便宜(被选)")
print("=" * 100)

for u in upstreams:
    cells = []
    a2off = {}
    a2on = {}
    for g in l7_gates:
        if G.has_edge(u, g):
            a2off[g] = cost_a2(G, u, g, False)
            a2on[g] = cost_a2(G, u, g, True)
    if not a2off:
        continue
    best_off = min(a2off, key=a2off.get)
    best_on = min(a2on, key=a2on.get)
    print(f"\n{u}")
    for g in l7_gates:
        if g not in a2off:
            continue
        length = float(G[u][g].get("length", 0.0))
        mark_off = " *A2关选此" if g == best_off else ""
        mark_on = " *A2开选此" if g == best_on else ""
        print(f"   -> {g.split('Gate_L7_')[-1]:10s} mu={mu[g]:.2f}  len={length:6.1f}  "
              f"cost_Meng={a2off[g]:7.2f}{mark_off:10s}  cost_engine={a2on[g]:7.2f}{mark_on}")
