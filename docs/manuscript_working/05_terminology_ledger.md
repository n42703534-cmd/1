# Terminology Ledger

Use these terms consistently across the manuscript.

| Canonical term | Allowed abbreviation | Avoid | Definition / note |
|---|---|---|---|
| Longyang Road Station | Longyang Road | Longyang station if ambiguous | Case-study multi-line metro transfer station. Confirm official English name before submission. |
| AdaptiveQueueAwareAStar | AA* | AdaptiveSingleNextHop | Current formal proposed algorithm. |
| PaperImprovedAStar | ImprovedAStar | improved algorithm without label | Baseline method label in the latest output. |
| time-dependent A* search | time-dependent AA* search | fixed-K dynamic path cache | Search formulation that updates cost according to predicted arrival and resource queue state. |
| predicted resource queue | `Q_pred` | queue if physical location is unclear | Expected queued demand at a constrained resource when a batch arrives. |
| resource service rate | `mu` | capacity if service-rate units are unclear | Service throughput used for predicted wait, typically people per second. |
| predicted waiting time | `Q_pred / mu` | congestion penalty if formula differs | AA* wait component added to physical travel time. |
| rerouting gain threshold | `gain_min` | behavioral compliance parameter | Internal anti-oscillation threshold. In inspected Mode 4, `gain_min = 0.20`. |
| cumulative stationary person-seconds | stationary person-s | congestion time if undefined | Aggregate time spent stationary or queued across passengers. |
| total evacuation time | evacuation time | travel time | Passenger-level time from simulation start to exit. |
| moving time | moving time | total time | Passenger-level time spent moving; distinct from stationary delay. |
| T95, T99, T100 | percentile clearance time | average evacuation time | Time by which the stated percentile has exited. T100 must be caveated if a method hits the time limit. |
| line clearance time | line clearance | platform clearance if line-specific | Final exit time for passengers associated with a line. |
| exit-load Jain index | exit Jain | HHI | Jain fairness index over final exits. Higher means more even distribution. |
| key-facility Jain index | facility Jain | overall balance | Jain fairness index over constrained internal facilities. Higher means more even distribution. |
| density-dependent flow | density flow | crowd speed if formula omitted | Execution-layer flow model in which density affects speed or receiving capacity. |
| spillback | spillback | blockage if not modeled | Downstream occupancy limits upstream receiving flow. |
| gate queue area | queue area | gate buffer if inconsistent | Local model storage area used for gate queue handling. |
| Mode 4 | high-load Mode 4 | final scenario unless frozen | Bidirectional full-train-load scenario with 17,905 passengers in the inspected run. |

## Style Decisions

- Use "passengers" for people in the metro station context.
- Use "occupants" only when discussing Pathfinder output files or software terminology.
- Use "resource" for a constrained service element such as a gate, stair, or passage when the exact facility type varies.
- Use "baseline" only after defining it as `PaperImprovedAStar`.
- Use "inspected run" for current numbers until the final result directory is frozen.

## Claims That Need Precise Wording

- Correct: "AA* improved key-facility Jain index in the inspected Mode 4 run."
- Incorrect: "AA* improved load balance" without specifying the level.
- Correct: "The older baseline timeout result has been superseded by the latest completed ImprovedAStar run."
- Incorrect: "Use the older 6000 s timeout as the current baseline result."
- Correct: "`gain_min` is an algorithmic threshold used to suppress low-gain rerouting."
- Incorrect: "`gain_min` is a literature-calibrated pedestrian behavior parameter."
