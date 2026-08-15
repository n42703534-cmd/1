# Visual QA — arrival-time-aware planning framework

## Reference and scope

- Primary composition reference: Yang et al. (2024), Fig. 1 — left input strip, four-column central execution pipeline, and right output strip.
- Secondary cues only: Wei et al. (2026), Fig. 1 for the restrained blue/orange/green hierarchy; Junfeng et al. (2026), Fig. 1 for staged process grouping.
- Figure language: English only.

## Source assets embedded

- Station geometry: `../cad_geometry/longyang_station_20260815.dwg` / `.dxf` (rendered from the supplied station drawing).
- Continuous-space execution: `../cad_geometry/pathfinder_longyang_overview_20260815.png`.
- Completion-profile check: `fig2_pathfinder_high_load_validation.png`.

## Layout checks completed

- Rebuilt on one three-strip grid; all four central stages share equal widths and aligned baselines.
- Removed the prior nested-frame clutter, tiny network graph, curved feedback arrow, and floating chart thumbnail.
- Kept only two real inputs and two real outputs, each in a full-size evidence card.
- Checked the 320 dpi PNG at native resolution for clipping, overlap, connector crossings, and legibility.
- No new numerical result, comparison claim, or unverified parameter value was added.

## Export checks

- PDF: one page, 518.74 × 286.30 pt (183 × 101 mm), vector master.
- SVG: vector master.
- PNG: 320 dpi review/export image.
- TIFF: 600 dpi, LZW-compressed submission raster.
