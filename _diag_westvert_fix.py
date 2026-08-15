# 只读：用修正后的 West_Vert 坐标 (264, 6073.2) 重算各上游到 4 个 L7 闸机的欧氏距离，
# 看修正 x 后 West_Vert 是否被任何上游选为最近（错配是否消失）。
import math
from collections import Counter

gates = {
    "N_East": (3424.7, 7238.6),
    "N_Mid": (3019.3, 7217.1),
    "N_West": (1418.8, 7143.7),
    "WVert_FIX": (264.0, 6073.2),   # 修正 x=264, y 不变
}
gates_old_wv = (128.8, 6073.2)
mu = {"N_East": 1.39, "N_Mid": 1.00, "N_West": 1.00, "WVert_FIX": 2.78}
ups = {
    "Esc_down1": (4462.0, 7096.4),
    "Esc_up1": (971.5, 6651.5),
    "Stair_1": (803.1, 6883.1),
    "Stair_2": (2808.0, 6771.1),
    "Stair_3": (4462.0, 6869.9),
    "VN_2to7": (5471.3, 6394.2),
    "Hall": (1997.9, 6924.1),
}


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


order = ["N_East", "N_Mid", "N_West", "WVert_FIX"]
near = Counter()
print("=== 上游 -> 各闸机 欧氏距离(CAD)，* = 该上游最近的闸机（用修正后的 West_Vert x=264）===")
for u, up in ups.items():
    ds = {g: dist(up, gates[g]) for g in order}
    best = min(ds, key=ds.get)
    near[best] += 1
    cells = "  ".join(f"{g}={ds[g]:6.0f}{'*' if g == best else ' '}" for g in order)
    print(f"{u:10s} {cells}")

print("\n=== 各闸机被选为最近的次数（修正后）===")
for g in order:
    print(f"  {g:10s} mu={mu[g]:.2f}  被选最近 = {near[g]}")

print("\n=== West_Vert 到各上游：旧(x=128.8) vs 修正(x=264)，并列 N_West 参考 ===")
for u, up in ups.items():
    old = dist(up, gates_old_wv)
    fix = dist(up, gates["WVert_FIX"])
    nw = dist(up, gates["N_West"])
    flag = "  <-- 修正后 West_Vert 比 N_West 近!" if fix < nw else ""
    print(f"  {u:10s} old={old:6.0f}  fix={fix:6.0f}  N_West={nw:6.0f}{flag}")
