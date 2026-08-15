# Section Contracts

Each section must satisfy its contract before it enters the submission draft.

## Abstract

Purpose:
State the problem, method, evaluation setting, main final results, and boundary.

Allowed now:
- One-sentence problem framing.
- One-sentence method description.
- Placeholder for final numerical results.

Not allowed yet:
- Final percentage improvements.
- Claims of real-world deployment readiness.
- Uncaveated T100 improvement.

Required placeholders:
- `[RESULT PLACEHOLDER: final T95/T99/stationary-delay metrics]`
- `[RESULT PLACEHOLDER: final completion-status wording]`
- `[RESULT PLACEHOLDER: final trade-off sentence]`

## Introduction

Purpose:
Move from metro-station evacuation risk to the need for queue-aware dynamic guidance.

Required moves:
- Establish why multi-line transfer stations create high-load, bottleneck-sensitive evacuation conditions.
- Explain why path length alone is insufficient.
- Identify a gap in anticipatory queue-aware routing for constrained internal facilities.
- State the paper's method and evaluation boundary.

Citation requirements:
- Latest urban rail statistics from official CAMET or equivalent.
- Empirical subway evacuation or bottleneck evidence.
- Recent path-planning and guidance literature.

Forbidden:
- Unverified national statistics.
- Overstated novelty such as "first ever" unless proven.

## Related Work

Purpose:
Position the work against evacuation simulation, route planning, and validation literature.

Required groups:
- Subway station evacuation behavior and bottlenecks.
- Dynamic path planning and guided evacuation.
- Queueing, congestion, and bottleneck-aware routing.
- Simulation and validation tools.

Boundary:
Contrast prior work carefully. The gap is not "nobody studies evacuation routing"; the narrower gap is anticipatory queue-aware routing for constrained station resources under a shared high-load simulation layer.

## Method

Purpose:
Define the graph model, shared execution layer, baseline, proposed AA* method, and metrics.

Must include:
- Network representation.
- People initialization and batch/routing unit.
- Density-speed relation and capacity handling.
- Resource queue definition.
- Baseline route cost.
- AA* predicted wait term.
- Rerouting threshold and anti-oscillation logic.
- Implementation boundary and computational complexity.

Parameter rule:
Every physical or empirical parameter needs a source or local model-source justification. Every internal algorithmic threshold must be labeled as algorithmic and sensitivity-tested if it affects conclusions.

## Experimental Setup

Purpose:
Make the comparison reproducible.

Must include:
- Scenario definitions.
- Population construction.
- Shared simulator settings.
- Methods compared.
- Metrics.
- Termination criteria.
- Output-directory versioning.

Current fixed items for inspected Mode 4:
- 17,905 passengers.
- 1 s time step.
- Density-dependent flow enabled.
- Spillback enabled.
- Gate queue areas enabled.
- `gain_min = 0.20`.

Included in scope:
- Mode 1 low-load regular emergency.
- Mode 4 high-load bidirectional full-train scenario.
- Sensitivity analysis.
- Pathfinder comparison.

Still pending:
- Final frozen output directories for each included experiment group.

## Results

Purpose:
Report observations, not interpretation.

Required tables:
- Overall evacuation metrics.
- Line clearance metrics.
- Load-balance metrics.
- Runtime.
- Optional sensitivity or validation tables.

Required caveats:
- If a method reaches the time limit with remaining passengers, report remaining passengers and termination status.
- Separate T95/T99 from T100 when T100 is bounded by a time limit.

Forbidden:
- Mechanistic explanations before the Discussion.
- Selectively hiding negative metrics.

## Discussion

Purpose:
Explain why the observed pattern occurs and what it means.

Must address:
- Why predicted resource queues may reduce stationary delay.
- Why moving time may increase.
- Why key-facility balance and exit balance can diverge.
- Runtime cost.
- Parameter sensitivity and external validity.
- Limitations of graph abstraction.

## Conclusion

Purpose:
State the final contribution without exceeding the evidence.

Allowed structure:
- Restate method.
- Summarize final frozen metrics.
- State practical implication.
- State limitations and future work.

Forbidden:
- "Universal", "guaranteed", or "field-proven" claims unless supported by additional evidence.
