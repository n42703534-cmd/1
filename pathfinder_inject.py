"""
pathfinder_inject.py — 解析 Pathfinder .txt，注入 AdaptiveQueueAwareAStar 出口分配。

策略 (v3):
  1. 用 ImprovedAStar 数据作为"当前分配"参照系
  2. 在 (profile, behavior) 组内做空间排序，匹配 source_group
  3. 只对 Adaptive ≠ baseline 的 source_group 对应的 occupant 改出口
  4. 保持其他 occupant 不变

用法:
    python pathfinder_inject.py              # 默认参数
    python pathfinder_inject.py --dry-run    # 只看差异
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# exit → behavior
EXIT_TO_BEHAVIOR = {
    "Exit_L16_10": 0, "Exit_L16_11": 1,
    "Exit_L7_7": 2, "Exit_L7_8/9": 3,
    "Exit_L2_4": 4, "Exit_L2_3": 5,
    "Exit_L2_2": 6, "Exit_L2_6": 7,
    "Exit_L18_12": 8, "Exit_L18_17": 9,
}
BEHAVIOR_TO_EXIT = {v: k for k, v in EXIT_TO_BEHAVIOR.items()}

PROFILE_TO_LINE = {0: "L16", 1: "L7", 2: "L2", 3: "L18"}

EXIT_LINE = {
    "Exit_L16_10": "L16", "Exit_L16_11": "L16",
    "Exit_L7_7": "L7", "Exit_L7_8/9": "L7",
    "Exit_L2_2": "L2", "Exit_L2_3": "L2", "Exit_L2_4": "L2", "Exit_L2_6": "L2",
    "Exit_L18_12": "L18", "Exit_L18_17": "L18",
}

DEFAULT_CSV = ROOT / "203b_scenario1_pathfinder_exit_by_source_group.csv"
DEFAULT_TXT = ROOT / "pathfinder" / "龙阳路my .txt"
DEFAULT_OUT = ROOT / "pathfinder" / "龙阳路my _injected.txt"


# ── TXT 解析 ──────────────────────────────────────────────

def parse_txt_sections(txt_path: Path) -> dict[str, list[str]]:
    text = txt_path.read_text(encoding="utf-8")
    sections: dict[str, list[str]] = {}
    current = "__head__"
    sections[current] = []
    for line in text.splitlines(keepends=True):
        m = re.match(r'^\[(\w+)\]', line)
        if m:
            current = m.group(1)
            sections[current] = [line]
        else:
            sections[current].append(line)
    return sections


def parse_occupants(sections: dict) -> list[dict]:
    occs = []
    for line in sections.get("occupants", []):
        m = re.match(r'^\d+:\s*(\{.*\})', line)
        if not m:
            continue
        occ = json.loads(m.group(1))
        occ["_raw"] = m.group(1)
        occs.append(occ)
    return occs


# ── CSV 读取 ──────────────────────────────────────────────

def read_csv_rows(csv_path: Path) -> list[dict]:
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def build_sg_exit_map(rows: list[dict], method: str) -> dict[str, list[dict]]:
    mp: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("method_label", "") != method:
            continue
        mp[r["source_group"]].append({
            "exit_name": r["exit_name"],
            "people": float(r.get("people", 0)),
            "share": float(r.get("share_within_group", r.get("pct_of_group", 0))),
        })
    for k in mp:
        mp[k].sort(key=lambda x: x["people"], reverse=True)
    return dict(mp)


def build_sg_meta(rows: list[dict]) -> dict[str, dict]:
    seen = {}
    for r in rows:
        sg = r["source_group"]
        if sg not in seen:
            seen[sg] = {
                "line": r["line"],
                "source_type": r["source_type"],
                "source_zone": r.get("source_zone", ""),
                "configured_people": int(float(r.get("configured_people", 0))),
            }
    return seen


# ── 辅助函数 ──────────────────────────────────────────────

def _occ_pos(occ: dict) -> tuple[float, float, float]:
    parts = occ.get("loc", "0 0 0").split()
    return (float(parts[0]), float(parts[1]), float(parts[2]))


def _is_transfer_sg(sg: str, sg_meta: dict) -> bool:
    return sg_meta.get(sg, {}).get("source_type") == "transfer_people"


# ── 核心分配逻辑 (v3) ─────────────────────────────────────

def assign_exits(
    occupants: list[dict],
    baseline_map: dict[str, list[dict]],
    adaptive_map: dict[str, list[dict]],
    sg_meta: dict[str, dict],
) -> dict[int, str]:
    """
    策略:
      1. 按 (profile, behavior) 分组 occupant
      2. 每组内，找到 baseline exit = 当前 behavior exit 的 source_groups
      3. 组内 occupant 按空间排序，匹配 source_group（按 configured_people 计数）
      4. 应用 AdaptiveQueueAwareAStar 出口（可能有变化）
    """
    assignments: dict[int, str] = {}

    # 按 (profile, behavior) 分组
    groups: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for occ in occupants:
        key = (occ.get("profile", -1), occ.get("behavior", -1))
        groups[key].append(occ)

    for (profile, behavior), group_occs in groups.items():
        line = PROFILE_TO_LINE.get(profile, "?")
        baseline_exit = BEHAVIOR_TO_EXIT.get(behavior)
        if not baseline_exit:
            # 未知 behavior → 保持原样
            for occ in group_occs:
                assignments[occ["id"]] = BEHAVIOR_TO_EXIT.get(behavior, "Exit_L2_2")
            continue

        # 找出所有 baseline exit = 当前出口的 source_group（属于该 line）
        matching_sgs = []
        for sg, meta in sg_meta.items():
            if meta["line"] != line:
                continue
            baseline_entries = baseline_map.get(sg, [])
            if not baseline_entries:
                continue
            if baseline_entries[0]["exit_name"] == baseline_exit:
                matching_sgs.append(sg)

        if not matching_sgs:
            # 没有匹配的 source_group → 保持原出口
            for occ in group_occs:
                assignments[occ["id"]] = baseline_exit
            continue

        # 排序 source_groups: transfer 放在最后, platform 在前按 zone 排序
        def _sg_sort_key(sg):
            meta = sg_meta.get(sg, {})
            st = meta.get("source_type", "")
            sz = meta.get("source_zone", "")
            if st == "platform_waiting":
                return (0, sz)
            elif st == "hall_people":
                return (1, sz)
            else:
                return (2, sz)
        matching_sgs.sort(key=_sg_sort_key)

        # 组内 occupant 排序: 先按距离"站台层Z"的距离, 再按 X, Y
        # 站台层Z ≈ 组内最频繁的 Z (四舍五入到0.5)
        all_z = [_occ_pos(o)[2] for o in group_occs]
        if all_z:
            from collections import Counter
            z_bins = Counter(round(z * 2) / 2 for z in all_z)  # 分箱到 0.5
            ref_z = z_bins.most_common(1)[0][0]  # 众数 Z
        else:
            ref_z = 0.0

        sorted_occs = sorted(
            group_occs,
            key=lambda o: (abs(_occ_pos(o)[2] - ref_z), _occ_pos(o)[0], _occ_pos(o)[1])
        )

        occ_idx = 0
        for sg in matching_sgs:
            meta = sg_meta.get(sg, {})
            total = meta.get("configured_people", 0)

            adaptive_exits = adaptive_map.get(sg, [])
            sg_occs = sorted_occs[occ_idx:occ_idx + total]

            if not adaptive_exits:
                # 无 Adaptive 数据 → 保持 baseline
                for occ in sg_occs:
                    assignments[occ["id"]] = baseline_exit
            elif len(adaptive_exits) == 1:
                for occ in sg_occs:
                    assignments[occ["id"]] = adaptive_exits[0]["exit_name"]
            else:
                # 多出口 — 保持组内空间顺序，按比例分配
                _proportional_assign(sg_occs, adaptive_exits, assignments)

            occ_idx += total

        # 剩余 occupant（计数不匹配的情况）→ 保持原出口
        for i in range(occ_idx, len(sorted_occs)):
            assignments[sorted_occs[i]["id"]] = baseline_exit

    return assignments


def _proportional_assign(
    occs: list[dict],
    exit_list: list[dict],
    assignments: dict[int, str],
):
    """保持 occupant 空间顺序，按出口人数比例分配"""
    if not occs or not exit_list:
        return
    idx = 0
    for entry in exit_list:
        count = int(entry["people"])
        for _ in range(count):
            if idx >= len(occs):
                return
            assignments[occs[idx]["id"]] = entry["exit_name"]
            idx += 1
    for i in range(idx, len(occs)):
        assignments[occs[i]["id"]] = exit_list[0]["exit_name"]


# ── TXT 生成 ──────────────────────────────────────────────

def build_modified_txt(
    sections: dict[str, list[str]],
    assignments: dict[int, str],
) -> str:
    section_order = [
        "version", "param", "nodedisp", "behaviors", "tags",
        "profiles", "functions", "distributions", "component-restrictions",
        "attractor-filters", "events", "occupants",
    ]
    result: list[str] = []
    for sn in section_order:
        if sn not in sections:
            continue
        if sn == "occupants":
            result.extend(_rewrite_occupants(sections[sn], assignments))
        else:
            result.extend(sections[sn])
    for key in sections:
        if key not in section_order and key != "__head__":
            result.extend(sections[key])
    return "".join(result)


def _rewrite_occupants(lines: list[str], assignments: dict[int, str]) -> list[str]:
    new_lines = []
    for line in lines:
        m = re.match(r'^(\d+):\s*(\{.*\})', line)
        if not m:
            new_lines.append(line)
            continue
        idx_str, json_str = m.group(1), m.group(2)
        occ = json.loads(json_str)
        occ_id = occ.get("id")
        if occ_id in assignments:
            new_exit = assignments[occ_id]
            new_behavior = EXIT_TO_BEHAVIOR.get(new_exit)
            if new_behavior is not None and new_behavior != occ.get("behavior"):
                occ["behavior"] = new_behavior
                json_str = json.dumps(occ, ensure_ascii=False, separators=(",", ":"))
                new_lines.append(f'{idx_str}: {json_str}\n')
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    return new_lines


# ── 差异统计 ──────────────────────────────────────────────

def show_diff(occupants: list[dict], assignments: dict[int, str]):
    changes: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    changed = 0
    unchanged = 0
    missing = 0

    for occ in occupants:
        occ_id = occ.get("id")
        profile = occ.get("profile", -1)
        line = PROFILE_TO_LINE.get(profile, "?")
        old_exit = BEHAVIOR_TO_EXIT.get(occ.get("behavior"), f"bhv_{occ.get('behavior')}")

        if occ_id not in assignments:
            missing += 1
            continue

        new_exit = assignments[occ_id]
        if old_exit == new_exit:
            unchanged += 1
        else:
            changed += 1
            changes[line][f"{old_exit} → {new_exit}"] += 1

    print(f"\n=== 注入差异汇总 ===")
    print(f"  总人数: {len(occupants)}")
    print(f"  出口变更: {changed} ({changed / max(len(occupants), 1) * 100:.1f}%)")
    print(f"  保持不变: {unchanged} ({unchanged / max(len(occupants), 1) * 100:.1f}%)")
    if missing:
        print(f"  未分配: {missing}")

    if changed > 0:
        print()
        for line in sorted(changes):
            print(f"  [{line}]:")
            for desc, cnt in sorted(changes[line].items(), key=lambda x: -x[1]):
                print(f"    {desc}: {cnt} 人")

    # 出口分布
    print(f"\n  出口分布:")
    dist = defaultdict(int)
    for occ in occupants:
        occ_id = occ.get("id")
        ex = assignments.get(occ_id, BEHAVIOR_TO_EXIT.get(occ.get("behavior"), "?"))
        dist[ex] += 1
    for ex, cnt in sorted(dist.items(), key=lambda x: -x[1]):
        print(f"    {ex}: {cnt} 人 ({cnt / max(len(occupants), 1) * 100:.1f}%)")


def _show_changed_sgs(
    baseline_map: dict[str, list[dict]],
    adaptive_map: dict[str, list[dict]],
    sg_meta: dict[str, dict],
):
    """打印 Adaptive 与 baseline 不同的 source_group 详情。"""
    changed = []
    for sg in baseline_map:
        baseline_entries = baseline_map.get(sg, [])
        adaptive_entries = adaptive_map.get(sg, [])
        if not adaptive_entries:
            continue
        baseline_dist = {e["exit_name"]: e["people"] for e in baseline_entries}
        adaptive_dist = {e["exit_name"]: e["people"] for e in adaptive_entries}
        if baseline_dist != adaptive_dist:
            changed.append((sg, baseline_dist, adaptive_dist))

    if changed:
        print(f"\n  Adaptive ≠ baseline 的 source_group ({len(changed)} 个):")
        for sg, baseline_d, adp_d in sorted(changed):
            meta = sg_meta.get(sg, {})
            print(f"    [{meta.get('line','?')}] {sg} ({meta.get('source_type','?')})")
            print(f"      Baseline: {dict(baseline_d)}")
            print(f"      Adaptive: {dict(adp_d)}")


# ── main ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="注入算法出口分配到 Pathfinder txt")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--txt", type=Path, default=DEFAULT_TXT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--baseline-method", default="ImprovedAStar")
    parser.add_argument("--method", default="AdaptiveQueueAwareAStar")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # 1. CSV
    print(f"[1] 读取 CSV: {args.csv}")
    all_rows = read_csv_rows(args.csv)
    baseline_map = build_sg_exit_map(all_rows, args.baseline_method)
    adaptive_map = build_sg_exit_map(all_rows, args.method)
    sg_meta = build_sg_meta(all_rows)
    print(f"  {args.baseline_method}: {len(baseline_map)} sgs, {args.method}: {len(adaptive_map)} sgs")
    _show_changed_sgs(baseline_map, adaptive_map, sg_meta)

    # 2. txt
    print(f"\n[2] 解析 txt: {args.txt}")
    sections = parse_txt_sections(args.txt)
    occupants = parse_occupants(sections)

    # 按 profile, behavior 统计
    pb_counts = defaultdict(int)
    for occ in occupants:
        pb_counts[(occ.get("profile", -1), occ.get("behavior", -1))] += 1
    print(f"  {len(occupants)} occupants, {len(pb_counts)} (profile,behavior) 组")

    # 3. 分配
    print(f"\n[3] 分配出口 (method={args.method})...")
    assignments = assign_exits(occupants, baseline_map, adaptive_map, sg_meta)
    print(f"  已分配: {len(assignments)} 人")

    # 4. 差异
    show_diff(occupants, assignments)

    # 5. 写入
    if not args.dry_run:
        print(f"\n[4] 写入: {args.out}")
        new_content = build_modified_txt(sections, assignments)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(new_content, encoding="utf-8")
        print(f"  完成! ({len(new_content)} bytes)")
    else:
        print("\n[4] Dry-run，不写入")


if __name__ == "__main__":
    main()
