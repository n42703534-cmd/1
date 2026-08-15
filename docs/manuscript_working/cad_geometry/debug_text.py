import extract_dxf_inventory as e

for kind, fields in e.parse_entities(e.DXF):
    value = e.first(fields, 1, "")
    if "磁悬浮站厅层" in value or "ç£" in value:
        print(repr(value), repr(e.repair_mojibake(value)))
        break
