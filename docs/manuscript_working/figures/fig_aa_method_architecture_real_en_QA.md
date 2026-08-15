# QA report — real-data AA* method architecture

## Figure contract

- Scientific message: arrival-time-aware AA* coordinates future competition at shared station resources through a rolling prediction–execution loop, and the resulting route allocation is assessed in the real continuous station geometry.
- Archetype: asymmetric mixed methodology figure with three traceable real-data panels and one mechanism panel.
- Target size: 183 × 112 mm (double-column landscape).
- In-figure language: English only.

## Source integrity

- Panel (a) uses the 2026-08-15 DWG exported through AutoCAD Core Console to DXF. The renderer retained 24,542 visible geometry entities in the robust station envelope; Chinese CAD annotations and remote drawing artifacts were excluded.
- Panel (b) calls `network.build_graph()` and renders all 572 positioned nodes and all 1,414 directed edges. No representative-node sampling was used.
- Panel (c) is derived from the supplied method text and the implemented queue-prediction, multi-label search, rolling assignment, common-executor and route-commitment logic.
- Panel (d) embeds the supplied 505 × 789 Pathfinder top-view image without redrawing its station geometry.
- Full file hashes and type counts are recorded in `fig_aa_method_architecture_real_en.source_manifest.json`.

## Semantic QA

- PASS: Improved A* and AA* differ only by current-queue versus queue-at-ETA evaluation in the controlled-difference strip.
- PASS: committed arrivals are advanced to the candidate ETA before path evaluation.
- PASS: the five cost components are movement, predicted queue, batch service, spatial receiving and density exposure.
- PASS: the network-flow executor returns occupancy, queues and future-arrival state to the next planning cycle.
- PASS: accepted in-transit movements remain route locked.
- PASS: Pathfinder is downstream cross-model assessment and has no feedback arrow to AA*.

## Visual QA

- PASS: restrained four-color semantic palette plus neutral grays.
- PASS: no gradients, shadows, decorative texture, perspective effects or generated station geometry.
- PASS: no clipped titles or metric labels at final print dimensions.
- PASS: CAD, network and Pathfinder evidence remain visually distinct from the abstract AA* mechanism.
- PASS: the 505-pixel Pathfinder source is placed at approximately 32 mm width, preserving adequate effective print resolution.

## Export QA

- PNG: 2305 × 1411 pixels, 320 dpi.
- TIFF: 4322 × 2645 pixels, 600 dpi, LZW compression.
- PDF: vector master for CAD, network, text, arrows and shapes; Pathfinder remains a traceable raster insert.
- SVG: editable vector master with live text.

## Statistics and reproducibility

This is a methodology architecture figure and contains no quantitative comparison panel, replicate summary, inferential test or uncertainty interval. A statistical-reporting block is therefore not applicable. The displayed network counts are direct structural counts from the implemented graph, not experimental estimates.

## Remaining limitation

The supplied Pathfinder image is a model-overview snapshot rather than a time-stamped evacuation-state image. It is valid for documenting the continuous-space model geometry. If a later running-state snapshot is supplied, panel (d) can be replaced without changing the remaining figure.
