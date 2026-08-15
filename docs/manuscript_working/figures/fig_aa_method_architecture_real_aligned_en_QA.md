# QA — `fig_aa_method_architecture_real_aligned_en`

## Figure contract

- Publication-oriented architecture figure, 183 × 120 mm, white background.
- English labels only in the newly drawn figure.
- Reference-aligned structure: `INPUT → MODEL / OPTIMIZATION → OUTPUT`.
- Real source assets are embedded for the station geometry and Pathfinder model; the network graph thumbnail is intentionally omitted because it is not legible at this figure scale.

## Source integrity

- DWG/DXF geometry is rendered from the latest exported project file; no station geometry was hallucinated.
- The implemented network-flow mechanism remains represented in the central execution block, but the dense directed-network thumbnail is not shown.
- The Pathfinder execution image is the user-supplied overview image copied into the project asset folder.
- The Pathfinder validation panel uses the existing project result figure `fig2_pathfinder_high_load_validation.png`.
- Hashes and source paths are recorded in `fig_aa_method_architecture_real_aligned_en.source_manifest.json`.

## Semantic QA

- Input block: station geometry, demand events, service rate, receiving capacity and speed–density relation.
- Model block: controlled comparison, ETA propagation, committed arrival events, queue at ETA, multi-label A* search, time-dependent path cost, rolling assignment and dynamic network-flow execution.
- Execution feedback: occupancy, queues and future arrivals return to the planning block; in-transit routes are explicitly locked.
- Output block: route/exit transfer to Pathfinder, network-layer metrics, continuous-space metrics and cross-model assessment.

## Visual QA

- White background; no shadows, photo textures or saturated decorative colors.
- Stage boundaries and internal modules follow the rectangular/dashed, arrow-driven style of the supplied reference figures.
- All visible labels were checked at the rendered PNG scale for clipping and overlap.
- Real source thumbnails are kept subordinate to the workflow so the figure remains a methods architecture rather than a result collage.
- The dense network thumbnail was removed during QA because it was not legible at the reference-aligned scale. The Pathfinder validation figure was retained and enlarged as a dedicated output module.
- Timeline markers are rendered as labelled event dots; decorative vertical stems in the execution cards were removed.

## Export QA

- PNG, TIFF, PDF and SVG were regenerated from the same script.
- The PDF/SVG are the preferred submission masters; PNG/TIFF are preview and raster-submission alternatives.

## Boundary of evidence

- The Pathfinder source supplied by the user is a model-overview snapshot, not a time-stamped evacuation-state field. It is therefore labelled as `Pathfinder execution` and used as a verification-model asset, not as evidence of a particular transient flow state. The separate validation panel is the project result figure and is labelled accordingly.
