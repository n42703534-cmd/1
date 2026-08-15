# Evidence Table

Use this table as the gatekeeper for manuscript claims. A claim can move into final prose only when its status is `ready` or when the prose explicitly labels it as preliminary.

| Claim | Evidence or source | Strength | Usable section | Risk | Status |
|---|---|---|---|---|---|
| Current national urban rail network scale can be stated from CAMET. | CAMET 2026-H1 line overview: 58 cities, 386 operating lines, 13,268.30 km, 6,920 stations, 1,052 transfer stations as of 2026-06-30. | Official source | Introduction | Use 2025 annual report only for annual passenger-volume wording. | ready |
| The current formal proposed algorithm is `AdaptiveQueueAwareAStar`. | `single_path_routing.py`; `docs/aa_time_dependent_astar_design.md`; `docs/aa_rerouting_definition.md`. | Strong local evidence | Method | Older drafts use stale names. | ready |
| AA* uses time-dependent search with predicted resource queues rather than fixed-K dynamic full-path cache. | Local design note and validation CSV. | Strong local evidence | Method | Must not mix with old `AdaptiveSingleNextHop` wording. | ready |
| Mode 1 and Mode 4 are the two main scenarios. | `algorithm_comparison.py`: Mode 1 low-load regular emergency with 2,187 people; Mode 4 high-load bidirectional full-train scenario with 17,905 people. | Strong local evidence | Experimental setup | Final AA outputs still pending. | ready |
| Sensitivity analysis and Pathfinder comparison are included in scope. | User decision in current thread. | User-confirmed scope | Experimental setup, validation, discussion | Need final output directories and Pathfinder version/settings. | ready as scope |
| `gain_min = 0.20` is an internal anti-oscillation threshold for Mode 4. | `docs/aa_rerouting_definition.md`; `network.py` / `algorithm_comparison.py` configuration. | Strong local evidence | Method, parameter table | Not literature-calibrated. | ready with caveat |
| Speed-density constants and the 3.0 persons/m2 high-density cutoff follow the Meng et al. Improved A* baseline reproduction. | `single_path_routing.py`; Meng D., Hu Z., Zhang H., 2022, Journal of System Simulation, DOI 10.16182/j.issn1004731x.joss.21-0075. | Local implementation plus literature metadata | Method parameters | Treat as baseline-reproduction parameters, not station field calibration. | ready with caveat |
| Longyang Road facility capacities exist in code but are not all the same source type. | `lines_config.py` encodes widths/counts/areas/coordinates; `network.py` computes capacity; gate queue area uses configured depth and fallback gate-bank width assumptions. | Strong local evidence | Method, parameter table | Need original official/CAD source if claiming "official data". | ready with caveat |
| The previous "ImprovedAStar timed out at 6000 s" claim is obsolete. | `conversation_handoff_20260805.md`; `outputs\algorithm_compare\mode4_20260805_111839\ImprovedAStar\summary_metrics.csv`. | Strong local evidence | Results cleanup | Must remove older timeout-based claim from final comparison. | ready |
| Latest completed ImprovedAStar Mode 4 result has T100 = 1443 s. | `mode4_20260805_111839\ImprovedAStar\summary_metrics.csv`. | Strong local evidence | Results | Not a final comparison until AA completes under same config. | partial |
| Latest AA Mode 4 output is incomplete. | `outputs\algorithm_compare\mode4_20260805_111940\AdaptiveQueueAwareAStar\run.log`; no `summary_metrics.csv`. | Strong local evidence | Results boundary | Do not compare intermediate AA log with completed baseline metrics. | ready |
| Modern metro evacuation research emphasizes real station complexity and bottleneck behavior. | Li et al. 2025, TUST, DOI 10.1016/j.tust.2025.106962; Feliciani and Nishinari 2018, TR-C, DOI 10.1016/j.trc.2018.03.027. | External literature verified by web search | Introduction, Related Work | Full text access may be limited. | ready for general framing |
| Guided passenger path planning can improve evacuation efficiency and balance facility use. | Yang et al. 2022, Applied Mathematical Modelling, DOI 10.1016/j.apm.2022.07.024. | External literature verified by web search | Related Work | Their setting uses guides and optimization, not the same method. | ready with scope |
| Pathfinder supports goal-based occupant behavior, path planning, and door-choice costs involving current room travel/queue time. | Thunderhead Pathfinder user and technical manuals. | Official software documentation | Validation / comparator description | Need match exact Pathfinder version used locally. | ready with version check |
| Jain fairness index increases toward 1 when allocations are more equal. | Jain, Chiu, and Hawe 1984 technical report; author page lead. | Established metric; primary report link still preferred | Metrics | Do not state lower Jain is better. | ready with primary-citation check |

## Claim Wording Rules

- Use "final frozen run" only after a final output directory is explicitly selected.
- Do not use the older 6000 s baseline timeout as a current result.
- Do not compare an incomplete AA log with completed ImprovedAStar metrics.
- Use "is associated with" or "suggests" for mechanism interpretation.
- Say "higher Jain index indicates a more even distribution" when introducing Jain-based metrics.
- For Longyang Road facility data, say "encoded from station model/configuration" unless the original official/CAD document is cited.
