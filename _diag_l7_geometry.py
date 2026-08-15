# 只读：L7 四个平行闸机的位置、容量，以及各上游到它们的距离（几何-容量错配）
import network as net

G = net.build_graph()
G.graph["_sim_time"] = 0.0

l7_gates = sorted(
    n for n in G.nodes
    if ("gate" in str(G.nodes[n].get("type", "")).lower()) and ("L7" in str(n))
)

print("=== L7 闸机：位置 / 类型 / 容量 ===")
print(f"{'闸机':20s} {'pos(x, y)':20s} {'类型':13s} {'容量(人/秒)':>12s} {'≈人/小时':>10s}")
for g in l7_gates:
    pos = G.nodes[g].get("pos")
    mu = net.resource_capacity_per_second(G, ("facility", g))
    typ = str(G.nodes[g].get("type", ""))
    posx = f"({pos[0]:.1f}, {pos[1]:.1f})" if pos else "None"
    print(f"{g:20s} {posx:20s} {typ:13s} {mu:12.2f} {mu*3600:10.0f}")

upstreams = sorted({u for g in l7_gates for u in G.predecessors(g)})
print("\n=== 上游节点位置 ===")
for u in upstreams:
    pos = G.nodes[u].get("pos")
    posx = f"({pos[0]:.1f}, {pos[1]:.1f})" if pos else "None"
    print(f"{u:24s} {posx}")

print("\n=== 上游 -> 各闸机 距离（边长 m），行尾标注该上游最近的闸机 ===")
hdr = "  ".join(f"{g.split('Gate_L7_')[-1]:>9s}" for g in l7_gates)
print(f"{'上游 \\ 闸机':24s} {hdr}   最近闸机(mu)")
for u in upstreams:
    lens = {}
    cells = []
    for g in l7_gates:
        if G.has_edge(u, g):
            L = float(G[u][g].get("length", 0.0))
            lens[g] = L
            cells.append(f"{L:9.1f}")
        else:
            cells.append(f"{'-':>9s}")
    nearest = min(lens, key=lens.get) if lens else None
    tail = ""
    if nearest:
        mu = net.resource_capacity_per_second(G, ("facility", nearest))
        tail = f"{nearest.split('Gate_L7_')[-1]}(mu={mu:.2f})"
    print(f"{u:24s} " + "  ".join(cells) + f"   {tail}")

# 汇总：每个闸机被多少上游视为"最近"，对比其容量
print("\n=== 汇总：闸机容量 vs 被多少上游视为最近 ===")
from collections import Counter
near = Counter()
for u in upstreams:
    lens = {g: float(G[u][g].get("length", 0.0)) for g in l7_gates if G.has_edge(u, g)}
    if lens:
        near[min(lens, key=lens.get)] += 1
for g in sorted(l7_gates, key=lambda x: -net.resource_capacity_per_second(G, ("facility", x))):
    mu = net.resource_capacity_per_second(G, ("facility", g))
    print(f"{g:20s} mu={mu:.2f}/s  被 {near.get(g,0)} 个上游视为最近")
