# QA — `fig_aa_method_architecture_peerfig1_en`

## Reference-informed visual contract

The figure is a `schematic-led` architecture figure at 183 × 112 mm.
It uses the peer Fig. 1 compositional patterns without reproducing their artwork:

- Junfeng et al. (2026): a small number of sequential, pastel-coded method stages.
- Wei et al. (2026): nested method blocks, compact supporting evidence panels and an explicit evaluation output.
- Yang et al. (2024): `Input → central pipeline → Output` zones, blue chevron transfers, orange module headers, and real input/output thumbnails.

## Source integrity

- Station overview: rendered from the project DWG/DXF export, not redrawn from a generated image.
- Route-allocation panel: the user-provided Pathfinder overview image.
- Completion-profile panel: a crop of the existing project Pathfinder validation result; it remains a native source raster.
- The dense directed-network thumbnail is intentionally absent. At this panel size it added visual noise without readable scientific information.
- Full source hashes are in `fig_aa_method_architecture_peerfig1_en.source_manifest.json`.

## Layout and readability QA

- One outer container with three dashed operational zones; no oversized parallel-panel layout.
- The central zone uses the fixed hierarchy `parameter cards → method modules → local mechanism diagrams → equation strip → shared executor → evacuation plan`.
- Blue is reserved for input/transfer, orange for route optimization, gold for integrated execution, and green for Pathfinder outputs.
- All new labels are English. No non-ASCII icon glyphs remain.
- Each central module has one title and one local visual cue; formula, labels and arrows were checked for overlap in the rendered PNG.

## Evidence boundary

- The Pathfinder overview is a model snapshot rather than a time-indexed crowd-state image.
- The completion profile is an existing cross-model result and is included only as an output-validation example; this architecture figure adds no new numerical claim.

## Deliverables checked

- PDF/SVG: vector master for manuscript production.
- PNG: 320 dpi preview.
- TIFF: 600 dpi raster submission alternative.
