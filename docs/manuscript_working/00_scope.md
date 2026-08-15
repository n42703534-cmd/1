# Manuscript Scope

## Working Status

This folder is a controlled writing workspace for manuscript sections that can be drafted before all simulation results are finalized. It separates confirmed local evidence from provisional interpretation so that later numerical updates can be inserted without rewriting the argument from scratch.

## Working Title Options

1. Emergency evacuation simulation and path optimization for multi-line metro transfer stations considering facility service queues
2. Bottleneck queuing and route organization in high-load evacuation of multi-line metro transfer stations
3. Emergency evacuation simulation and guidance optimization for metro transfer stations under high passenger loads
4. Queue-predictive path optimization for emergency evacuation in multi-line metro transfer stations

## Target Manuscript Type

Algorithmic and simulation-based evacuation study.

Likely target venue type: transportation safety, underground space, evacuation modeling, or simulation-based built-environment safety journal. The specific journal is not fixed yet, so style, reference format, abstract length, and section labels remain generic.

## Current Writing Boundary

Sections that can be drafted now:

- Introduction
- Related Work
- Method
- Experimental Design
- Results table shells
- Discussion scaffold
- Conclusion scaffold

Sections that must remain provisional until final runs are fixed:

- Abstract result sentences
- Final Results
- Quantitative Discussion
- Conclusion claims about superiority or generality
- Any robustness, sensitivity, or cross-tool validation claim not backed by final output files

## Confirmed Project Anchor

The current formal algorithm is `AdaptiveQueueAwareAStar`, not `AdaptiveSingleNextHop`. The current baseline label is `PaperImprovedAStar` / `ImprovedAStar`. Older drafts that use `AdaptiveSingleNextHop`, old ACO-related comparisons, or older Mode 1 result tables must not be merged into the manuscript unless those results are rerun and revalidated under the current formal model.

## Non-negotiable Evidence Rules

- Do not invent final performance results.
- Do not treat a time-limit value as a true completion time.
- Do not describe `gain_min = 0.20` as a literature-calibrated behavioral parameter. Local documentation defines it as an internal anti-oscillation threshold for Mode 4 rerouting sensitivity.
- Do not claim exit-load balance improved in the latest Mode 4 run. The latest run shows improved key-facility Jain index but lower exit-level Jain index for AA* than the baseline.
- Every numeric background statistic, pedestrian-flow parameter, and literature result must be linked to a verified source before submission.

## Finalization Gate

Before converting this workspace into a submission draft, complete the following:

- Freeze the final experiment directory or list all accepted run directories.
- Recompute summary metrics from the frozen outputs.
- Freeze the accepted Mode 1, Mode 4, sensitivity-analysis, and Pathfinder comparison output directories.
- Verify all references and DOI metadata.
- Replace all `[RESULT PLACEHOLDER]`, `[CITATION NEEDED]`, and `[CHECK]` markers.
