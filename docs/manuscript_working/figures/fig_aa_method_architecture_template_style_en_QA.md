# Visual QA — template-style arrival-time-aware framework

## Scope

- Layout source: the user-provided three-column template (blue input, orange planning, green output).
- The figure deliberately contains no performance values, result tables, or comparative claims.
- Text is English only.

## Evidence retained

- Actual station geometry is rendered from `../cad_geometry/longyang_station_20260815.dwg/.dxf`.
- Actual Pathfinder execution view is loaded from `../cad_geometry/pathfinder_longyang_overview_20260815.png`.
- The central mechanism uses the implemented logic in `network.py` and `single_path_routing.py`: dynamic state, confirmed-arrival event advancement, ETA queue forecast, cumulative route cost, and route-lock/rolling reassignment.

## Visual checks

- All three macro panels use the same header height and baseline.
- The four central planning cards have equal widths, aligned tops and bottoms, and non-crossing stage arrows.
- Result tables were replaced with an evidence-flow evaluation panel.
- Checked the 360 dpi PNG at native resolution for clipping, overlap, and title-badge collisions.

## Exports

- PDF and SVG: vector masters.
- PNG: 360 dpi preview/export.
- TIFF: 600 dpi, LZW-compressed submission raster.
