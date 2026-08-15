# Evidence manifest for the TUST working draft

## Direct project evidence

- Case geometry: `龙阳路磁浮加强措施20250320_t3(1).dwg`, supplied by the author.
- Reference-demand construction: `人数设计逻辑.docx`, supplied by the author.
- Implemented demand: `algorithm_comparison.py` (`BASE_LOADS` plus line-specific train loads).
- Proposed and reference methods: `single_path_routing.py`, `network.py`, `algorithm_comparison.py`.
- High-load network results: `outputs/algorithm_compare/mode4_20260808_173528/mode4_formal_report.md`.
- Pathfinder high-load outputs: `龙阳路/高负荷/*_occupants.csv`, `*_occupant_params.csv`, and three `.geom` files.
- Pathfinder analysis outputs: `figures/table_pathfinder_high_load_summary.csv`, `figures/table_pathfinder_high_load_paired.csv`, `figures/pathfinder_high_load_equivalence_audit.txt`.

## Full-text literature basis

- Meng, Hu and Zhang (2022), full local PDF, DOI `10.16182/j.issn1004731x.joss.21-0075`.
- Yang et al. (2024), full local PDF, DOI `10.1016/j.tust.2023.105473`.
- Yang et al. (2022), full local PDF, DOI `10.1016/j.apm.2022.07.024`.
- Guo and Zhang (2022), full local PDF, DOI `10.1016/j.autcon.2021.104010`.
- Shen et al. (2024), full local PDF, DOI `10.1016/j.ress.2023.109711`.
- Wen et al. (2024), full-text source bundle, DOI `10.1016/j.trc.2024.104640`.
- Hua et al. (2024), full local PDF, DOI `10.1016/j.jnlssr.2024.04.001`.
- Yu et al. (2023), publisher full text, DOI `10.1016/j.physa.2023.129175`.
- Pathfinder Technical Reference and User Manual full HTML sections cited for Locally Quickest and Goto Any Exit.

## Interpretation rules applied

- `Pathfinder` is described as cross-model microscopic testing, not field validation.
- `Pathfinder Goto Any Exit` is the software-native contextual reference. “Locally Quickest” describes the internal path-planning mechanism in the technical manual; it is not combined into a new `PF-LQ` label.
- `P-AA` versus `P-Improved` is reported as a matched-name descriptive comparison; the audit discloses observed initial-orientation and minor coordinate differences.
- `Pathfinder Goto Any Exit` is evaluated at the scenario-distribution level because its native scenario differs in many individual attributes and initial positions; it is not used in the same-name paired test.
- Low-load Pathfinder values are not inferred; the manuscript reserves an explicit insertion block.
