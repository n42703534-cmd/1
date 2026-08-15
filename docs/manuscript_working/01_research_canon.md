# Research Canon

This file records the facts that the manuscript may use, the reasonable inferences that remain tentative, and the items that still need verification.

## Confirmed Local Facts

- Repository working directory: `C:\Users\28146\Desktop\network\FIRST`.
- Compared methods:
  - Baseline: `PaperImprovedAStar` / `ImprovedAStar`.
  - Proposed method: `AdaptiveQueueAwareAStar` / AA*.
- The formal AA* design uses time-dependent A* search with predicted resource queues. Local design notes explicitly state that the formal version does not rely on fixed-K dynamic full-path caching.
- `gain_min = 0.20` is an internal rerouting anti-oscillation threshold, not an externally calibrated pedestrian parameter.
- Main experiment scope is fixed as two scenarios:
  - Mode 1: low-load regular emergency, 2,187 passengers.
  - Mode 4: high-load bidirectional full-train scenario, 17,905 passengers.
- Sensitivity analysis and Pathfinder comparison are included in the manuscript scope.
- Older `AdaptiveSingleNextHop`, ACO, and old result tables are excluded unless rerun under the current formal implementation.

## Confirmed External Facts

- The current official urban rail network scale should cite CAMET's 2026-H1 line overview.
- CAMET reports that as of 2026-06-30, mainland China had 58 cities with operating urban rail service, 386 operating lines, 13,268.30 km of operating line length, 6,920 stations, and 1,052 transfer stations.
- The 2025 CAMET annual report should be used only for annual 2025 wording such as annual passenger volume, not for "current as of now" network scale.

## Source Status For Speed-density Parameters

- `single_path_routing.py` identifies the baseline as Meng et al. (2022), "基于改进A*算法的多层邮轮疏散系统仿真".
- Current code constants:
  - `PAPER_FREE_SPEED = 1.427` m/s.
  - `PAPER_DENSITY_FREE = 0.2` persons/m2.
  - `PAPER_DENSITY_JAM = 4.0` persons/m2.
  - `PAPER_DENSITY_SLOPE = 0.3549`.
  - `PAPER_HIGH_DENSITY_THRESHOLD = 3.0` persons/m2.
  - `PAPER_LENGTH_ALPHA = 0.15`.
  - `PAPER_SPEED_BETA = 0.85`.
  - `PAPER_HEURISTIC_GAMMA = 0.10`.
- Manuscript wording should say these parameters reproduce the Meng et al. Improved A* baseline and the associated Fruin speed-density model. Do not describe them as Longyang Road field-calibrated parameters.

## Latest Mode 4 Output Status

The older `outputs\algorithm_compare\mode4_20260805_105507` comparison is superseded for ImprovedAStar because the 6000 s timeout was later fixed. It must not be used as the current final Mode 4 comparison.

| Metric | ImprovedAStar latest completed run | AdaptiveQueueAwareAStar latest inspected run | Manuscript status |
|---|---:|---:|---|
| Output directory | `mode4_20260805_111839\ImprovedAStar` | `mode4_20260805_111940\AdaptiveQueueAwareAStar` | Confirmed |
| Target population | 17,905 | 17,905 | Confirmed |
| Evacuated population | 17,905 | incomplete run | Improved confirmed; AA pending |
| Remaining population | 0 | latest log at 400 s: 7,477 | AA pending |
| Termination | completed | no `summary_metrics.csv` | AA pending |
| T95 (s) | 1102 | not available | AA pending |
| T99 (s) | 1275 | not available | AA pending |
| T100 (s) | 1443 | not available | AA pending |
| Mean total evacuation time (s/person) | 448.735 | not available | AA pending |
| Cumulative stationary person-s | 6,553,851 | not available | AA pending |
| Exit-load Jain index | 0.714752 | not available | AA pending |
| Key-facility Jain index | 0.196035 | not available | AA pending |
| Wall-clock runtime (s) | 40.824 | not available | AA pending |

## Confirmed Interpretation Constraints

- The previous claim that ImprovedAStar timed out at 6000 s is obsolete.
- The latest AA Mode 4 run is incomplete and cannot be used for final comparison against the completed ImprovedAStar run.
- Any AA performance conclusion must wait for a completed AA run under the same configuration.
- If older AA diagnostic patterns are mentioned internally, they must be labeled as older-run diagnostics, not final results.
- Key-facility Jain and exit-load Jain must be interpreted separately. Higher Jain means more even distribution.

## Facility-capacity Source Boundary

- `lines_config.py` contains station topology, platform areas, stair/escalator widths, gate counts, coordinates, virtual node widths/areas, and exit widths.
- `network.py` converts facility width or gate count into service capacity using `calculate_gb_capacity_per_second`.
- Gate queue areas are engineering approximations: queue area = physical gate-bank width times configured line-specific queue depth.
- Gate-bank physical width uses configured gate-bank width where available; otherwise it falls back to standard/wide gate clear-width and cabinet-width assumptions in `lines_config.py`.
- Therefore, do not write "all Longyang Road capacities are official data" unless the original official/CAD source for each class is cited. Safer manuscript wording: station geometry and facility counts are encoded from the station model/configuration; service capacities are calculated from facility type and effective width/count; queue-area depths and gate-bank fallback widths are model assumptions.

## Temporarily Unverified Items

- Exact original source file or document proving each Longyang Road station geometry and capacity value.
- Exact Pathfinder version and behavior settings for the validation section.
- Final complete AA results for Mode 1 and Mode 4.
- Sensitivity-analysis output directories and accepted parameter grid.
