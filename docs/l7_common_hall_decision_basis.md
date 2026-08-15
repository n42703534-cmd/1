# L7 common-hall decision: model basis and data provenance

## Scope

The isolated L7 mechanism trial uses one physical decision sequence:

`vertical facility -> VN_L7_Hall_Arrival -> one Gate Queue -> its Gate`

Only people still at `VN_L7_Hall_Arrival` may compare Gate Queues. Entering a
Queue is a physical commitment; Queue nodes cannot replan to another Gate.

The default full-station graph does not yet route the five existing L7
vertical facilities through the new Hall. It preserves their original
vertical-to-gate approaches so a Mode 4 comparison is not confounded by an
unvalidated topology change. The upstream integration is available only when
building an explicit mechanism trial with
`build_graph(enable_l7_common_hall_vertical_integration=True)`.

## Local data provenance

- Vertical-facility and Gate CAD coordinates come from `lines_config.py`.
- The optional five vertical-to-hall lengths use the existing L7 CAD
  conversion factor, `0.01`.
- `VN_L7_Hall_Arrival` retains its existing 90 square metre area.
- Gate Queue areas retain the existing formula: Gate width multiplied by the
  configured 8 metre Queue depth.
- Existing edge and Gate capacities, the 3.0 persons per square metre
  Improved threshold, the speed-density relation, and AA's 20 percent minimum
  gain are unchanged.

The cited literature supports the modelling structure. It is not asserted as
the source of the station-specific geometry or the existing numerical
thresholds above.

## Literature basis

1. Hart, Nilsson and Raphael (1968), "A Formal Basis for the Heuristic
   Determination of Minimum Cost Paths", IEEE Transactions on Systems Science
   and Cybernetics, 4(2), 100-107.
   DOI: https://doi.org/10.1109/TSSC.1968.300136

   This is the foundational A* formulation. It supports separating path-search
   logic from the physical movement executor.

2. Dreyfus (1969), "An Appraisal of Some Shortest-Path Algorithms",
   Operations Research, 17(3), 395-412.
   DOI: https://doi.org/10.1287/opre.17.3.395

   The paper explicitly treats fastest paths with departure-time-dependent
   travel times.

3. Orda and Rom (1990), "Shortest-Path and Minimum-Delay Algorithms in
   Networks with Time-Dependent Edge-Length", Journal of the ACM, 37(3),
   607-625.
   DOI: https://doi.org/10.1145/79147.214078

   This provides the theoretical basis for time-dependent edge delays and for
   stating waiting assumptions explicitly.

4. Srikukenthiran, Fisher, Shalaby and King (2013), "Pedestrian Route Choice
   of Vertical Facilities in Subway Stations", Transportation Research Record,
   2351(1).
   DOI: https://doi.org/10.3141/2351-13

   This supports treating vertical-facility choice as an explicit pedestrian
   route-choice problem rather than an implicit shortest-distance shortcut.

5. Sun et al. (2019), "Simulation Research on Pedestrian Evacuation Path
   Selection in the Metro Station", Journal of System Simulation, 31(9),
   1819-1826.
   DOI: https://doi.org/10.16182/j.issn1004731x.joss.18-0715

   The model uses real-time passenger density and facility capacity to
   determine evacuation path allocation.

6. "Stochastic user equilibrium path planning for crowd evacuation at subway
   station based on social force model" (2022), Physica A, 594, 127033.
   DOI: https://doi.org/10.1016/j.physa.2022.127033

   This supports including path distance, congestion and path capacity when
   balancing crowd flow among station Gates.

7. "Modeling boundedly rational route choice in crowd evacuation processes"
   (2022), Safety Science, 147, 105590.
   DOI: https://doi.org/10.1016/j.ssci.2021.105590

   This supports a non-zero improvement threshold: pedestrians need not change
   route for every arbitrarily small calculated advantage. The project's
   existing 20 percent value remains a model assumption and is not claimed to
   be calibrated by this paper.

## Validation requirements

The isolated mechanism is accepted only when tests demonstrate:

- every configured L7 vertical facility reaches every L7 Gate Queue through
  `VN_L7_Hall_Arrival`;
- no vertical facility retains a direct edge to an L7 Gate Queue;
- every Gate Queue has exactly its own Gate as its downstream successor;
- decision people and physically accepted people are reported separately;
- unaccepted people remain at the Hall;
- node occupants, in-transit occupants and evacuated occupants conserve the
  initial population.

These checks apply to the explicit integration trial. They are not a license
to enable that topology in the full Mode 4 comparison before the trial and
the station-level connectivity review pass.
