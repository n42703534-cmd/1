# Draft Sections, English Working Version

This is a working draft for sections that can be written before the final results are frozen. Bracketed markers must be resolved before submission.

## Title Candidates

1. Time-dependent queue-aware A* guidance for emergency evacuation in a multi-line metro transfer station
2. Adaptive queue-aware route guidance for high-load evacuation in a metro transfer station
3. Queue-predictive evacuation routing under constrained facility service in a metro transfer station

## Abstract Skeleton

Emergency evacuation in multi-line metro transfer stations is strongly affected by constrained facilities such as stairs, gates, passages, and exits. Static shortest-path guidance and congestion-reactive route costs can underrepresent the waiting time created by already committed downstream arrivals. This paper proposes `AdaptiveQueueAwareAStar` (AA*), a time-dependent queue-aware A* method that augments physical travel time with predicted service waiting time at constrained resources. The method is evaluated in a graph-based model of Longyang Road Station against a shared `PaperImprovedAStar` baseline under identical density-dependent flow, spillback, and gate-queue settings. `[RESULT PLACEHOLDER: insert final completion status, T95/T99, stationary-delay, and load-balance results.]` The results will be interpreted together with computational cost and balance trade-offs, including cases where key-facility and final-exit load balance move in different directions.

## 1. Introduction

Urban rail systems concentrate large passenger volumes in enclosed, multi-level spaces. In transfer stations, passengers from different lines share a limited set of stairs, ticket gates, passages, and final exits. During emergency evacuation, these shared resources can become controlling bottlenecks, so evacuation performance depends not only on route distance but also on how demand is distributed over time across constrained facilities. Current background statistics should be updated from the latest official urban rail report before submission. `[CITATION NEEDED: latest CAMET annual statistical and analysis report, preferably 2025 if using current wording.]`

Recent empirical work on real subway stations confirms that evacuation behavior is shaped by bounded route choice, facility preference, bottleneck speed attenuation, and fatigue during long upward movement. Li et al. reported full-size subway-station evacuation experiments and observed that passengers do not always choose the nearest or globally best route, while facility-level effects such as ticket-gate and stair movement can substantially shape evacuation dynamics. Broader pedestrian-flow studies also show that congestion and bottleneck risk are not captured by geometric distance alone. These findings motivate route guidance methods that account for both travel distance and time-varying crowd interaction at critical facilities.

A large body of subway evacuation research has developed simulation models, guide-assignment strategies, and path-planning methods. Multi-objective guidance models can improve total evacuation efficiency and distribute passengers more evenly across evacuation nodes, but many methods still evaluate candidate routes through static or current-state costs. In high-load transfer-station evacuation, a route that looks acceptable at the current time may become poor by the time a passenger group reaches a downstream gate or stair, because other passengers have already committed to that same resource. The resulting delay is anticipatory: it is created by future service demand, not only by current local density.

This study addresses that gap by evaluating `AdaptiveQueueAwareAStar` (AA*), a time-dependent queue-aware A* guidance method for a multi-line metro transfer station. AA* estimates the arrival time of each routed passenger batch and adds a predicted service waiting term at constrained resources to the route cost. The method is compared with `PaperImprovedAStar` in a shared graph-based simulation layer that includes density-dependent movement, spillback, service queues, and gate queue areas. The paper is intentionally framed as an algorithmic simulation study, not as a field deployment claim. Its main evidence will come from controlled comparisons on the same station model and scenario definitions.

The contributions are:

1. A time-dependent queue-aware A* formulation that incorporates predicted resource waiting time into evacuation route search.
2. A shared high-load simulation comparison in a multi-line metro transfer-station model with density-dependent flow, spillback, and service queues.
3. A metric set that reports evacuation efficiency, stationary delay, line clearance, facility-load balance, exit-load balance, and computational cost.
4. An explicit analysis boundary that distinguishes final completion, percentile clearance, internal facility balance, final exit balance, and runtime trade-offs.

## 2. Related Work

### 2.1 Subway station evacuation behavior and bottlenecks

Subway stations differ from simple multi-exit rooms because evacuation routes traverse several constrained facility types before passengers reach the outside. Empirical and simulation studies have therefore emphasized stairs, gates, passages, escalators, exit familiarity, and crowding effects. Full-size station experiments provide particularly valuable evidence because they capture route-choice behavior and facility interactions that may be simplified in laboratory or virtual settings. Li et al. showed that subway evacuation trajectories and facility choices are not always globally rational, and that local facilities such as ticket gates and stairs can change pedestrian speeds and route-use patterns.

### 2.2 Dynamic route guidance and passenger assignment

Route guidance studies usually seek to reduce total evacuation time, avoid bottlenecks, or balance facility use. Yang et al. formulated guided passenger path planning as a multi-objective optimization problem and reported improvements in evacuation efficiency and node pressure distribution under guide-based evacuation. Other recent metro-fire and hazard-aware studies embed smoke, risk, or robust optimization into path cost functions. These studies show the value of adaptive guidance, but their objectives, guidance units, and simulator assumptions differ from the queue-predictive decision layer considered here.

### 2.3 Queue-aware evacuation routing

The central routing issue in this manuscript is not only whether a facility is crowded now, but whether it will be crowded when a routed batch arrives. This distinction matters when many passengers are simultaneously assigned to downstream constrained resources. A current-density penalty reacts to visible congestion, while a queue-predictive term estimates waiting time from committed arrivals and service capacity. The proposed AA* method therefore treats constrained resources as time-dependent service points and adds predicted waiting time to physical travel time during search.

### 2.4 Simulation and validation context

Microscopic evacuation tools such as Pathfinder include goal-based occupant behavior, path planning, door choice, and queue-related door-choice terms. Such tools are useful for independent model checks and for communicating assumptions, but official software documentation also cautions that egress models supplement expert judgment rather than automatically predict real outcomes. This manuscript should therefore present any Pathfinder comparison as validation support or sensitivity context, not as proof that the graph model is field validated.

## 3. Method

### 3.1 Station graph and passenger representation

The station is represented as a directed graph `G = (V, E)`. Nodes represent platforms, stairs, gates, passages, exits, and other decision or service locations. Edges represent traversable movement links with length, capacity, and dynamic state. Passengers are initialized by line-specific origin groups and are routed in natural batches rather than as isolated continuous flow. The physical execution layer is shared by all compared routing methods, so differences in outcomes should be attributed to route-choice logic rather than different movement physics.

### 3.2 Shared execution layer

The simulator updates movement at a fixed time step. In the inspected Mode 4 run, the time step is 1.0 s. Movement is density dependent, downstream receiving capacity can limit upstream flow, and spillback can occur when downstream spaces or queue areas are saturated. Constrained resources such as gates or stairs are modeled with service capacity, queue state, and, where enabled, storage depth or queue area. `[CHECK: insert final parameter table with source for each physical constant and model-source justification for each station-specific capacity.]`

### 3.3 Baseline route guidance

The baseline method is `PaperImprovedAStar`. It evaluates routes using the shared network state and the baseline dynamic cost terms implemented in the current code. The manuscript should describe the baseline exactly as implemented, including its density, high-density, length, speed, and heuristic terms after the code is frozen. `[CHECK: verify final equations directly against `single_path_routing.py` before submission.]`

### 3.4 AdaptiveQueueAwareAStar

`AdaptiveQueueAwareAStar` extends route search by making downstream resource delay time-dependent. For a candidate movement from node `u` to node `v`, the method estimates physical travel time and the expected arrival time at `v`. If `v` is a constrained resource, the algorithm estimates the resource queue expected at that arrival time. The predicted waiting component is approximated as:

```text
predicted_wait(v, t_arrival) = Q_pred(v, t_arrival) / mu(v)
```

where `Q_pred` is the predicted queued demand at the resource and `mu` is the resource service rate. The route cost is then the sum of physical travel time and predicted waiting time accumulated through the path. Because the wait term depends on arrival time and committed downstream demand, AA* can avoid assigning many batches to a resource that is not yet visibly congested but is expected to become delayed by the time they arrive.

### 3.5 Rerouting and anti-oscillation threshold

The inspected Mode 4 configuration uses `gain_min = 0.20`. This value should be described as an internal rerouting threshold that suppresses low-gain route changes. It should not be described as a pedestrian behavior parameter or as a literature-calibrated value. If the final paper relies on its value, a sensitivity table should be added. `[RESULT PLACEHOLDER: gain_min sensitivity if included.]`

### 3.6 Metrics

The primary evacuation metrics are T95, T99, T100, mean total evacuation time, cumulative stationary person-seconds, effective evacuation speed, line clearance time, and remaining population at termination. T100 must be interpreted carefully when a method reaches the simulation time limit with passengers remaining. Balance is measured at two levels: final exits and key internal facilities. For Jain fairness indices, higher values indicate a more even distribution. Runtime is reported as computational cost and should not be hidden when comparing methods.

## 4. Experimental Setup

### 4.1 Scenario definition

The current inspected formal run evaluates Mode 4, a high-load scenario with 17,905 passengers. The run uses density-dependent flow, spillback, service-node queue handling, and gate queue areas. The final manuscript should specify whether this Mode 4 run is final and whether additional Mode 1 or sensitivity scenarios are included.

### 4.2 Compared methods

The compared methods are:

- `PaperImprovedAStar`, the implemented improved A* baseline.
- `AdaptiveQueueAwareAStar`, the proposed time-dependent queue-aware A* method.

Both methods must use the same population, network graph, service capacities, density-flow model, and termination criteria.

### 4.3 Reporting plan

The Results section should contain:

1. Overall evacuation metrics.
2. Line-level clearance metrics.
3. Facility and exit load-balance metrics.
4. Runtime metrics.
5. Optional sensitivity and cross-tool validation metrics.

If a method does not complete before the stopping limit, the table must report the remaining population and termination status. The text should then use percentile and remaining-population metrics rather than treating the time limit as a real clearance time.

## 5. Results Skeleton

`[RESULT PLACEHOLDER: replace this section after the final output directory is frozen.]`

Recommended table captions:

- Table 1. Overall evacuation performance under Mode 4.
- Table 2. Line-level clearance times under Mode 4.
- Table 3. Exit and key-facility load-balance metrics.
- Table 4. Computational runtime.
- Table 5. Sensitivity analysis for `gain_min` and queue-area assumptions, if included.

Draft result sentence template:

In the final Mode 4 run, AA* `[insert completion-status result]`. Compared with the baseline, AA* changed T95 from `[x]` s to `[y]` s and cumulative stationary person-seconds from `[x]` to `[y]`. The method also changed key-facility Jain index from `[x]` to `[y]` and exit-load Jain index from `[x]` to `[y]`, indicating that internal facility balance and final-exit balance should be interpreted separately.

## 6. Discussion Skeleton

The expected mechanism is that predicted resource queues allow AA* to avoid sending additional passenger batches toward downstream facilities that are likely to be saturated at the time of arrival. This can reduce stationary delay even when the selected route is longer in movement time. Such a pattern would be consistent with a routing trade-off: passengers may walk longer or use less direct internal paths to avoid waiting at severe service bottlenecks.

The balance metrics require separate interpretation. A higher key-facility Jain index suggests more even use of constrained internal resources. A lower exit-load Jain index, if retained in the final results, means final exits are not more evenly used. This is not a contradiction if the method prioritizes bottleneck service delay rather than equal final-exit assignment. The manuscript should report both instead of compressing them into a generic "load balance" claim.

Computational cost is another limitation. AA* performs richer time-dependent evaluation and, in the inspected run, is substantially slower in wall-clock runtime than the baseline. The practical relevance of this cost depends on planning cadence, possible caching, route-update frequency, and whether route guidance is computed offline, near-real-time, or as decision support for operators.

## 7. Conclusion Skeleton

This paper proposes and evaluates a time-dependent queue-aware A* route-guidance method for emergency evacuation in a multi-line metro transfer station. The method augments physical travel time with predicted service waiting time at constrained resources, allowing route search to account for downstream queues before they are physically visible at the candidate passenger location. `[RESULT PLACEHOLDER: insert final frozen performance summary.]` The results should be presented with clear boundaries: the method is promising for high-load bottleneck management, but its final claim depends on frozen simulation outputs, parameter sensitivity, and validation against independent models or empirical evidence.
