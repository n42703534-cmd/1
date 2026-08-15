from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
DXF = HERE / "longyang_station.dxf"


def repair_mojibake(value: str) -> str:
    return value
    # Legacy repair logic retained below for reference but bypassed because
    # the AutoCAD 2025 export is UTF-8.
    """Recover legacy layer names and doubly encoded CJK text when possible."""
    candidates = [value]
    for byte_codec in ("latin1", "cp1252"):
        for text_codec in ("utf-8", "gb18030"):
            try:
                candidates.append(value.encode(byte_codec).decode(text_codec))
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

    def score(text: str) -> tuple[int, int, int]:
        cjk = sum("\u3400" <= char <= "\u9fff" for char in text)
        replacement = text.count("\ufffd") + text.count("?")
        mojibake = sum(char in "æçéåèä½¾¿ð" for char in text)
        return cjk, -replacement, -mojibake

    best = max(candidates, key=score)
    # Some readers expose UTF-8 bytes as Latin-1 and a later serialization
    # preserves that mojibake.  A final visible-marker pass repairs those rows.
    if any(marker in best for marker in ("æ", "ç", "é", "å", "è", "ä")):
        for byte_codec in ("cp1252", "latin1"):
            try:
                repaired = best.encode(byte_codec).decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            if score(repaired) > score(best):
                best = repaired
    return best


def read_pairs(path: Path):
    # AutoCAD 2025 exported this ASCII DXF with UTF-8 text payloads even though
    # the header retains the source drawing's ANSI_936 code-page marker.
    with path.open("r", encoding="utf-8-sig", errors="strict") as handle:
        while True:
            code = handle.readline()
            if not code:
                return
            value = handle.readline()
            if not value:
                return
            try:
                group = int(code.strip())
            except ValueError:
                continue
            yield group, value.rstrip("\r\n")


def parse_entities(path: Path):
    in_entities = False
    current_type = None
    fields: list[tuple[int, str]] = []

    def emit():
        if current_type is None:
            return None
        return current_type, fields.copy()

    for code, value in read_pairs(path):
        if code == 0 and value == "SECTION":
            current_type = None
            fields = []
            continue
        if code == 2 and value == "ENTITIES":
            in_entities = True
            continue
        if in_entities and code == 0 and value == "ENDSEC":
            item = emit()
            if item:
                yield item
            return
        if not in_entities:
            continue
        if code == 0:
            item = emit()
            if item:
                yield item
            current_type = value
            fields = []
        else:
            fields.append((code, value))


def first(fields, code, default=""):
    for c, value in fields:
        if c == code:
            return value
    return default


def floats(fields, code):
    values = []
    for c, value in fields:
        if c == code:
            try:
                values.append(float(value))
            except ValueError:
                pass
    return values


def entity_points(kind, fields):
    xs = floats(fields, 10)
    ys = floats(fields, 20)
    zs = floats(fields, 30)
    if kind == "LINE":
        xs += floats(fields, 11)
        ys += floats(fields, 21)
        zs += floats(fields, 31)
    if kind in {"CIRCLE", "ARC"} and xs and ys:
        try:
            radius = float(first(fields, 40, "0"))
            xs = [xs[0] - radius, xs[0] + radius]
            ys = [ys[0] - radius, ys[0] + radius]
        except ValueError:
            pass
    return list(zip(xs, ys, zs + [0.0] * max(0, len(xs) - len(zs))))


def main():
    counts = Counter()
    layer_counts = Counter()
    layer_types = defaultdict(Counter)
    layer_bounds = {}
    text_rows = []
    insert_rows = []

    for kind, fields in parse_entities(DXF):
        layer = repair_mojibake(first(fields, 8, "<no-layer>"))
        counts[kind] += 1
        layer_counts[layer] += 1
        layer_types[layer][kind] += 1

        points = entity_points(kind, fields)
        if points:
            xs = [p[0] for p in points if math.isfinite(p[0])]
            ys = [p[1] for p in points if math.isfinite(p[1])]
            if xs and ys:
                bounds = layer_bounds.setdefault(layer, [xs[0], ys[0], xs[0], ys[0]])
                bounds[0] = min(bounds[0], min(xs))
                bounds[1] = min(bounds[1], min(ys))
                bounds[2] = max(bounds[2], max(xs))
                bounds[3] = max(bounds[3], max(ys))

        if kind in {"TEXT", "MTEXT", "ATTRIB", "ATTDEF"}:
            text = repair_mojibake(first(fields, 1, ""))
            extra = repair_mojibake(first(fields, 3, ""))
            x = first(fields, 10, "")
            y = first(fields, 20, "")
            text_rows.append([kind, layer, x, y, text + extra])
        elif kind == "INSERT":
            insert_rows.append(
                [kind, layer, repair_mojibake(first(fields, 2, "")), first(fields, 10, ""), first(fields, 20, "")]
            )

    inventory = {
        "source": str(DXF),
        "entity_counts": dict(counts.most_common()),
        "layers": [
            {
                "layer": layer,
                "count": count,
                "types": dict(layer_types[layer].most_common()),
                "bounds": layer_bounds.get(layer),
            }
            for layer, count in layer_counts.most_common()
        ],
    }
    (HERE / "dxf_inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (HERE / "dxf_text_entities.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["type", "layer", "x", "y", "text"])
        writer.writerows(text_rows)
    with (HERE / "dxf_insert_entities.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["type", "layer", "block", "x", "y"])
        writer.writerows(insert_rows)

    print(f"entities={sum(counts.values())}, layers={len(layer_counts)}, text={len(text_rows)}, inserts={len(insert_rows)}")
    print("top entity types:", counts.most_common(12))
    print("top layers:", repr(layer_counts.most_common(20)))


if __name__ == "__main__":
    main()
