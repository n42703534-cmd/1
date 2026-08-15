# Argument Map

## One-sentence Argument

This study develops and evaluates a time-dependent queue-aware A* guidance method for evacuation in a multi-line metro transfer station. Final claims about evacuation efficiency, stationary delay, load balance, and computational cost must wait for the frozen Mode 1, Mode 4, sensitivity-analysis, and Pathfinder comparison outputs.

## Core Contribution Claims

1. Method contribution: AA* incorporates predicted service waiting time at constrained resources into the path cost during time-dependent A* search.
2. Modeling contribution: the comparison uses a shared graph-based execution layer with density-dependent flow, spillback, gate queue areas, and line-specific gate queue depth.
3. Evaluation contribution: the paper compares AA* with an ImprovedAStar baseline under the same high-load Mode 4 population and reports both efficiency and balance metrics.
4. Boundary contribution: the paper explicitly reports trade-offs, including higher runtime, worse exit-level Jain balance in the inspected run, and the time-limit caveat for baseline completion.

## Evidence Chain

Problem:
High-load metro station evacuation is constrained not only by path length but also by service queues at gates, stairs, passages, and exits.

Gap:
Route guidance based mainly on current local congestion or static geometric cost can react after queues appear, but may fail to account for committed downstream arrivals that will create future waiting.

Method:
AA* estimates arrival time to each candidate resource and adds a predicted service wait term, approximately `Q_pred / mu`, to the route cost.

Evaluation:
The latest inspected Mode 4 run uses 17,905 passengers and compares AA* against ImprovedAStar in the same graph-based execution environment.

Current evidence:
The latest completed Mode 4 baseline run is available for `ImprovedAStar`, but the latest inspected AA* Mode 4 run is incomplete and has no final `summary_metrics.csv`. No final AA* versus baseline performance conclusion should be written until the accepted output directories are frozen.

Conclusion boundary:
The paper can claim queue-aware prediction is promising under the inspected high-load setting. It cannot yet claim universal superiority, validated real-world deployment readiness, or final quantitative performance until all planned results are frozen.

## Anticipated Reviewer Challenges

| Challenge | Honest response strategy |
|---|---|
| "The baseline timed out, so T100 comparison is unfair." | Agree. Use completion status and bounded clearance wording. Emphasize T95, T99, stationary delay, and remaining population. |
| "The proposed method increases computation time." | Report runtime as a trade-off. Discuss whether the planning cadence or precomputation can be optimized. |
| "Exit balance gets worse." | Report it directly. Explain that key-facility and final-exit balance measure different distribution objectives. |
| "Parameters are not calibrated from field data." | Separate literature-sourced physical parameters from internal algorithmic thresholds. Mark internal sensitivity settings and run sensitivity analysis if included. |
| "Graph abstraction may miss microscopic interactions." | Frame the graph model as a decision-layer abstraction and use Pathfinder or empirical literature only for validation and context, not as proof of real deployment performance. |
| "Older drafts show different algorithm names and results." | Treat older drafts as historical notes. The manuscript should follow the formal current implementation only. |

## Forbidden Shortcuts

- Do not state that AA* is "proven optimal" for evacuation.
- Do not state that AA* "eliminates congestion".
- Do not cite the latest inspected run as final unless the user freezes it.
- Do not use "improved load balance" without specifying the level: key-facility balance improved, exit-level balance worsened in the inspected Mode 4 run.
- Do not call the current comparison "field validated" unless the Pathfinder or empirical validation workflow is included and documented.
