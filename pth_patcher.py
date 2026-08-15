"""
pth_patcher.py — Binary-patch Pathfinder .pth: replace occupant behavior handles.

Strategy:
  1. javaobj parses the full object graph → builds handle→behavior_index map
  2. pathfinder_inject logic determines: agent → new_exit → new_behavior_index
  3. Binary scanner finds every EgressAgent, reads d_behavior handle
  4. Match by traversal order → patch behavior handles for changed agents

Usage:
  python pth_patcher.py --pth pathfinder/龙阳路my.pth --csv 203b_...csv [--dry-run]
"""

import io
import struct
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent

# ── Constants ─────────────────────────────────────────────

EGRESS_AGENT_CD_HANDLE = 0x7E003F  # primary classdesc handle
ALT_EGRESS_AGENT_CD_HANDLE = 0x80D658  # alternative classdesc handle

# From pathfinder_inject.py
EXIT_TO_BEHAVIOR = {
    "Exit_L16_10": 0, "Exit_L16_11": 1,
    "Exit_L7_7": 2, "Exit_L7_8/9": 3,
    "Exit_L2_4": 4, "Exit_L2_3": 5,
    "Exit_L2_2": 6, "Exit_L2_6": 7,
    "Exit_L18_12": 8, "Exit_L18_17": 9,
}
BEHAVIOR_TO_EXIT = {v: k for k, v in EXIT_TO_BEHAVIOR.items()}
PROFILE_TO_LINE = {0: "L16", 1: "L7", 2: "L2", 3: "L18"}


# ── javaobj-based analysis ────────────────────────────────

def parse_with_javaobj(pth_path: Path):
    """Parse .pth and return (md, refs, behavior_handles, agents_ordered)."""
    import javaobj
    from javaobj.v1 import JavaObjectUnmarshaller

    with open(pth_path, 'rb') as f:
        data = f.read()

    stream = io.BytesIO(data)
    um = JavaObjectUnmarshaller(stream)
    um.readObject()  # block data
    um.readObject()  # version
    md = um.readObject()

    refs = um.references

    # Build behavior handle → index mapping from BehaviorRoot hashset
    bhv_hset = md.behaviors.annotations[0]
    handle_to_bhv = {}
    bhv_idx = -2  # skip IdentityHasher + string in hashset
    for item in bhv_hset.annotations:
        if hasattr(item, 'get_class') and 'Behavior' in item.get_class().name:
            bhv_idx += 1
            if bhv_idx >= 0:
                try:
                    ridx = refs.index(item)
                except ValueError:
                    for i, r in enumerate(refs):
                        if r is item:
                            ridx = i
                            break
                    else:
                        continue
                handle_to_bhv[0x7E0000 + ridx] = bhv_idx

    # Traverse all agents in order (same order as serialization)
    agents_ordered = []
    top_hset = md.agents.annotations[0]
    for item in top_hset.annotations:
        if not hasattr(item, 'get_class') or 'EgressAgentComp' not in item.get_class().name:
            continue
        if not item.annotations:
            continue
        sub_hset = item.annotations[0]
        if not hasattr(sub_hset, 'annotations'):
            continue
        for si in sub_hset.annotations:
            if hasattr(si, 'get_class') and 'EgressAgent' in si.get_class().name and 'Comp' not in si.get_class().name:
                agents_ordered.append(si)

    return md, refs, handle_to_bhv, agents_ordered


def build_agent_changes(md, refs, handle_to_bhv, agents_ordered, csv_path: Path):
    """Apply pathfinder_inject logic, return list of (agent_index, new_behavior_handle)."""
    import pathfinder_inject as pinj

    # Read CSV
    all_rows = pinj.read_csv_rows(csv_path)
    baseline_map = pinj.build_sg_exit_map(all_rows, "ImprovedAStar")
    adaptive_map = pinj.build_sg_exit_map(all_rows, "AdaptiveQueueAwareAStar")
    sg_meta = pinj.build_sg_meta(all_rows)

    # Get profile mapping: need to match OccProfile objects to profile indices
    # Profile DEFAULT ≈ index 0 for now; actual mapping from OccProfileComp
    # For simplicity, use the profile's position and behavior to match source groups
    # (matching the heuristic used in assign_exits)

    # Build occupant list for assign_exits
    occupants = []
    for agent in agents_ordered:
        name = getattr(agent, 'd_name', '?')
        profile_obj = getattr(agent, 'd_profile', None)
        behavior_obj = getattr(agent, 'd_behavior', None)

        # Determine profile index (0=L16, 1=L7, 2=L2, 3=L18)
        profile_idx = -1
        if profile_obj is not None:
            pid = id(profile_obj)
            # Check DEFAULT/others
            if profile_obj is md.profiles.DEFAULT:
                profile_idx = 0  # Default → we'll figure out from spatial
            elif hasattr(md.profiles, 'NO_CHANGE') and profile_obj is md.profiles.NO_CHANGE:
                profile_idx = -1

        # Determine current behavior index from handle
        old_bhv_idx = -1
        if behavior_obj is not None:
            try:
                bidx = refs.index(behavior_obj)
                bh = 0x7E0000 + bidx
                old_bhv_idx = handle_to_bhv.get(bh, -1)
            except ValueError:
                for i, r in enumerate(refs):
                    if r is behavior_obj:
                        bh = 0x7E0000 + i
                        old_bhv_idx = handle_to_bhv.get(bh, -1)
                        break

        # Get position
        loc_str = "0 0 0"
        location = getattr(agent, 'd_location', None)
        if location is not None and hasattr(location, 'point'):
            pt = location.point
            if hasattr(pt, 'x'):
                loc_str = f"{pt.x} {pt.y} {pt.z}"

        occ = {
            "id": hash(name) % 10000000,
            "profile": profile_idx,
            "behavior": old_bhv_idx,
            "loc": loc_str,
        }
        occupants.append(occ)

    # Run assignment
    assignments = pinj.assign_exits(occupants, baseline_map, adaptive_map, sg_meta)

    # Build changes: agent_index → new_behavior_handle
    changes = {}
    for i, occ in enumerate(occupants):
        new_exit = assignments.get(occ["id"])
        if new_exit is None:
            continue
        new_bhv_idx = EXIT_TO_BEHAVIOR.get(new_exit)
        if new_bhv_idx is None:
            continue
        old_bhv_idx = occ["behavior"]
        if new_bhv_idx == old_bhv_idx:
            continue

        # Find handle for new behavior index
        new_handle = None
        for h, bi in handle_to_bhv.items():
            if bi == new_bhv_idx:
                new_handle = h
                break

        if new_handle is not None:
            changes[i] = new_handle

    return changes


# ── Binary scanning & patching ─────────────────────────────

def find_agent_offsets(data: bytes) -> list[int]:
    """Find all EgressAgent TC_OBJECT offsets in the binary."""
    pattern1 = b'\x73\x71' + struct.pack(">I", EGRESS_AGENT_CD_HANDLE)
    pattern2 = b'\x73\x71' + struct.pack(">I", ALT_EGRESS_AGENT_CD_HANDLE)

    offsets = []
    pos = 0
    while True:
        idx1 = data.find(pattern1, pos)
        idx2 = data.find(pattern2, pos)
        if idx1 == -1 and idx2 == -1:
            break
        if idx1 == -1:
            idx = idx2
        elif idx2 == -1:
            idx = idx1
        else:
            idx = min(idx1, idx2)
        offsets.append(idx)
        pos = idx + 1

    return offsets


def read_behavior_handle(data: bytes, agent_offset: int) -> int:
    """Read d_behavior handle from an EgressAgent at agent_offset.

    Binary layout:
      + 0: TC_OBJECT (1 byte)
      + 1: TC_REFERENCE + classdesc handle (5 bytes)
      + 6: d_resultsId (long, 8 bytes) [AMerlinObj superclass]
      +14: TC_ENDBLOCKDATA (1 byte) [AMerlinObj annotations end]
      +15: d_enabled (boolean, 1 byte)
      +16: d_orientSeed (long, 8 bytes)
      +24: d_profileSeed (long, 8 bytes)
      +32: d_visible (boolean, 1 byte)
      +33: d_behavior TC_REFERENCE byte (0x71)
      +34: d_behavior handle (4 bytes)  ← THIS IS WHAT WE NEED
    """
    handle_offset = agent_offset + 34
    if handle_offset + 4 > len(data):
        return None

    tc = data[handle_offset - 1]
    if tc != 0x71:  # TC_REFERENCE
        # Might be TC_NULL (0x70) if no behavior
        return None

    return struct.unpack_from(">I", data, handle_offset)[0]


def patch_behavior_handle(data: bytearray, agent_offset: int, new_handle: int):
    """Replace d_behavior handle at the given agent offset."""
    handle_offset = agent_offset + 34
    struct.pack_into(">I", data, handle_offset, new_handle)


# ── Main ──────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Binary-patch Pathfinder .pth behavior handles")
    parser.add_argument("--pth", type=Path, default=ROOT / "pathfinder" / "龙阳路my .pth")
    parser.add_argument("--csv", type=Path, default=ROOT / "203b_scenario1_pathfinder_exit_by_source_group.csv")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.out is None:
        stem = args.pth.stem
        args.out = args.pth.parent / f"{stem}_injected.pth"

    print(f"[1] Parsing {args.pth.name} with javaobj...")
    md, refs, handle_to_bhv, agents_ordered = parse_with_javaobj(args.pth)
    print(f"    Agents: {len(agents_ordered)}")
    print(f"    Behavior handles: {len(handle_to_bhv)}")
    for h, bi in sorted(handle_to_bhv.items(), key=lambda x: x[1]):
        exit_name = BEHAVIOR_TO_EXIT.get(bi, f"special_{bi}")
        print(f"      Behavior[{bi}] → handle=0x{h:06X} → {exit_name}")

    print(f"\n[2] Computing exit assignment changes...")
    changes = build_agent_changes(md, refs, handle_to_bhv, agents_ordered, args.csv)
    print(f"    Agents to change: {len(changes)}")

    if args.verbose:
        for ag_idx, new_handle in sorted(changes.items())[:20]:
            agent = agents_ordered[ag_idx]
            name = getattr(agent, 'd_name', '?')
            # Find old handle
            bhv_obj = getattr(agent, 'd_behavior', None)
            old_handle = None
            if bhv_obj is not None:
                try:
                    old_handle = 0x7E0000 + refs.index(bhv_obj)
                except ValueError:
                    for i, r in enumerate(refs):
                        if r is bhv_obj:
                            old_handle = 0x7E0000 + i
                            break
            old_bhv = handle_to_bhv.get(old_handle, -1) if old_handle else -1
            new_bhv = handle_to_bhv.get(new_handle, -1)
            print(f"      Agent[{ag_idx}] {name}: Behavior[{old_bhv}]→Behavior[{new_bhv}] (0x{old_handle:06X}→0x{new_handle:06X})")

    if args.dry_run:
        # Show summary statistics
        from collections import Counter
        change_types = Counter()
        for ag_idx, new_handle in changes.items():
            agent = agents_ordered[ag_idx]
            bhv_obj = getattr(agent, 'd_behavior', None)
            old_handle = None
            if bhv_obj is not None:
                try:
                    old_handle = 0x7E0000 + refs.index(bhv_obj)
                except ValueError:
                    for i, r in enumerate(refs):
                        if r is bhv_obj:
                            old_handle = 0x7E0000 + i
                            break
            old_bhv = handle_to_bhv.get(old_handle, -1) if old_handle else -1
            new_bhv = handle_to_bhv.get(new_handle, -1)
            change_types[f"Behavior[{old_bhv}]→Behavior[{new_bhv}]"] += 1

        print(f"\n    Change summary:")
        for desc, cnt in change_types.most_common():
            print(f"      {desc}: {cnt} agents")
        print(f"\n[Dry-run] Done. No files written.")
        return

    print(f"\n[3] Scanning binary for EgressAgent objects...")
    with open(args.pth, 'rb') as f:
        data = bytearray(f.read())

    agent_offsets = find_agent_offsets(bytes(data))
    print(f"    Found {len(agent_offsets)} EgressAgent offsets in binary")

    if len(agent_offsets) != len(agents_ordered):
        print(f"    ⚠ Mismatch! javaobj={len(agents_ordered)}, binary={len(agent_offsets)}")
        if len(agent_offsets) > len(agents_ordered):
            print(f"    Will truncate binary to match javaobj order")
            agent_offsets = agent_offsets[:len(agents_ordered)]
        else:
            print(f"    ⚠ Fewer agents in binary — some may be missed")

    print(f"\n[4] Patching behavior handles...")
    patched = 0
    skipped = 0

    for ag_idx, new_handle in sorted(changes.items()):
        if ag_idx >= len(agent_offsets):
            print(f"    ⚠ Agent index {ag_idx} out of binary range, skipping")
            skipped += 1
            continue

        offset = agent_offsets[ag_idx]
        old_handle = read_behavior_handle(bytes(data), offset)

        if old_handle is None:
            skipped += 1
            continue

        if old_handle == new_handle:
            skipped += 1
            continue

        patch_behavior_handle(data, offset, new_handle)
        patched += 1

    print(f"    Patched: {patched}")
    print(f"    Skipped: {skipped}")

    print(f"\n[5] Writing {args.out.name}...")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, 'wb') as f:
        f.write(data)
    print(f"    Done! ({len(data)} bytes)")

    # Quick verification
    print(f"\n[6] Verifying...")
    changed_offsets = [agent_offsets[ag_idx] for ag_idx in sorted(changes) if ag_idx < len(agent_offsets)]
    if changed_offsets:
        # Verify re-read the patched file
        with open(args.out, 'rb') as f:
            verify_data = f.read()

        verify_changes = 0
        for ag_idx, new_handle in sorted(changes.items()):
            if ag_idx >= len(changed_offsets):
                continue
            offset = agent_offsets[ag_idx]
            # Re-find in patched file
            read_handle = read_behavior_handle(verify_data, offset)
            if read_handle == new_handle:
                verify_changes += 1

        print(f"    Verified {verify_changes}/{len(changes)} changes applied correctly")
        if verify_changes == len(changes):
            print(f"    ✓ All patches verified!")
        else:
            print(f"    ⚠ Some patches may not have applied correctly")


if __name__ == "__main__":
    main()
