# 只读诊断：L7 平台等待区 -> 各竖向设施(楼/扶梯) 的成本，A2关 vs A2开，
# 看 A2(竖向边打-41%折) 是否改变平台选哪个楼扶梯，进而把人汇聚到 N_West 的上游。
import network as net
import single_path_routing as spr

G = net.build_graph()
G.graph["density_dependent_flow"] = True
G.graph["spillback_enabled"] = True
G.graph["_sim_time"] = 0.0

# 每个竖向设施最终喂给哪个 L7 闸机（取其到闸机的最便宜边）
l7_gates = [n for n in G.nodes if "gate" in str(G.nodes[n].get("type","")).lower() and "L7" in str(n)]
mu = {g: net.resource_capacity_per_second(G, ("facility", g)) for g in l7_gates}
G.graph["improved_shared_travel_time"] = False


def feeds_gate(vert):
    best, bestc = None, float("inf")
    for g in l7_gates:
        if G.has_edge(vert, g):
            c = spr.paper_edge_cost(G, vert, g)
            if c < bestc:
                best, bestc = g, c
    return best


# L7 平台等待区节点
plats = sorted(n for n in G.nodes if "Platform_L7" in str(n) and G.out_degree(n) > 0)
verts = sorted(n for n in G.nodes
               if ("Stair_L7" in str(n) or "Escalator_L7" in str(n)))

print("竖向设施 -> 喂给的闸机(mu):")
for v in verts:
    g = feeds_gate(v)
    if g:
        print(f"  {v:22s} -> {g.split('Gate_L7_')[-1]}(mu={mu[g]:.2f})")

print("\n=== 平台等待区 -> 各竖向设施 的成本 (A2关 Meng | A2开 引擎)，标记各自最便宜 ===")
shift = 0
for p in plats:
    rows = {}
    for v in verts:
        if G.has_edge(p, v):
            G.graph["improved_shared_travel_time"] = False
            coff = spr.paper_edge_cost(G, p, v)
            G.graph["improved_shared_travel_time"] = True
            con = spr.paper_edge_cost(G, p, v)
            rows[v] = (coff, con)
    if not rows:
        continue
    best_off = min(rows, key=lambda k: rows[k][0])
    best_on = min(rows, key=lambda k: rows[k][1])
    changed = " <<< A2 改变了平台的选择!" if best_off != best_on else ""
    if best_off != best_on:
        shift += 1
    print(f"\n{p}{changed}")
    print(f"   A2关选: {best_off.split('_L7_')[-1]} -> {str(feeds_gate(best_off)).split('Gate_L7_')[-1]}(mu={mu.get(feeds_gate(best_off),0):.2f})")
    print(f"   A2开选: {best_on.split('_L7_')[-1]} -> {str(feeds_gate(best_on)).split('Gate_L7_')[-1]}(mu={mu.get(feeds_gate(best_on),0):.2f})")
    for v in verts:
        if v in rows:
            coff, con = rows[v]
            print(f"      {v.split('_L7_')[-1]:12s} len={float(G[p][v].get('length',0)):6.1f}  Meng={coff:7.2f}  engine={con:7.2f}")

print(f"\n平台选择被 A2 改变的数量: {shift} / {len(plats)}")
