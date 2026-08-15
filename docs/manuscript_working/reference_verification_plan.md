# Reference Verification Plan

This file tracks external sources that should be verified before manuscript submission. Do not move a source into the final reference list until its bibliographic fields are checked.

## Verified Enough For Draft Framing

| Topic | Source | Draft use | Verification notes |
|---|---|---|---|
| Full-size subway-station evacuation experiment | Chao Li, Zexuan Tian, Ruihang Yang, Tiejun Zhou, Dachuan Wang, Haibin Zhang, Zheng Liang, Bofu Liu. "Experimental study for investigating the pedestrian evacuation dynamics pattern in an actual full-size subway station." Tunnelling and Underground Space Technology 166, 106962, 2025. DOI: https://doi.org/10.1016/j.tust.2025.106962 | Empirical support for station-specific behavior, route choice, facility effects, and fatigue. | Metadata and DOI found via ScienceDirect and OUCI. |
| Congestion and crowd risk measurement | Claudio Feliciani and Katsuhiro Nishinari. "Measurement of congestion and intrinsic risk in pedestrian crowds." Transportation Research Part C 91, 124-155, 2018. DOI: https://doi.org/10.1016/j.trc.2018.03.027 | Background support that congestion and risk require more than path length. | DOI and fields found via TRID/ScienceDirect. |
| Guided passenger path planning in subway station | Xiaoxia Yang, Yi Yang, Yongxing Li, Xiaoli Yang. "Path planning for guided passengers during evacuation in subway station based on multi-objective optimization." Applied Mathematical Modelling 111, 777-801, 2022. DOI: https://doi.org/10.1016/j.apm.2022.07.024 | Related-work comparison for guide assignment and multi-objective path planning. | DOI and fields found via ScienceDirect. |
| Pathfinder software behavior and route planning | Thunderhead Engineering Pathfinder User Manual and Technical Reference Manual. Example docs: https://support.thunderheadeng.com/docs/pathfinder/2024-1/user-manual/ and https://support.thunderheadeng.com/docs/pathfinder/2021-3/technical-reference-manual/ | Software-method context and validation discussion. | Need match the exact Pathfinder version used in local experiments. |
| Current urban rail network scale | China Association of Metros. "2026年上半年中国内地城轨交通线路概况." https://www.camet.org.cn/xytj/xxfb/822295470702661.shtml | Introduction background. | Official source. As of 2026-06-30: 58 cities, 386 operating lines, 13,268.30 km, 6,920 stations, 1,052 transfer stations. |
| 2025 annual urban rail statistics | China Association of Metros. "城市轨道交通2025年度统计和分析报告." https://www.camet.org.cn/xytj/tjxx/789653532090437.shtml | Annual passenger volume or annual trend background. | Official source. Use only when wording is "2025 annual" rather than "current". |
| Improved A* cruise-ship baseline source | Meng D., Hu Z., Zhang H. "基于改进A*算法的多层邮轮疏散系统仿真." Journal of System Simulation 34(6), 1375-1382, 2022. DOI: https://doi.org/10.16182/j.issn1004731x.joss.21-0075 | Baseline `PaperImprovedAStar` formulas, speed-density model, high-density threshold, and weights as reproduced in code. | Metadata found from Journal of System Simulation / Digital Commons. Check final PDF for exact equation numbering before typesetting. |
| Jain fairness index | Raj Jain, D.-M. Chiu, W. Hawe. "A Quantitative Measure of Fairness and Discrimination for Resource Allocation in Shared Computer Systems." DEC Research Report TR-301, 1984. Author page lead: https://www.cse.wustl.edu/~jain/papers/fairness.htm | Metrics definition. | Need retrieve or cite primary technical-report URL if final style permits. Higher index means more even allocation. |

## Needs Verification Before Use

| Topic | Candidate source or local lead | What to verify |
|---|---|---|
| Exact equation numbering for Meng et al. 2022 | Code comments say Eq. 5-9 for Fruin speed-density and Eq. 4 / Eq. 10 for A* weights. | Verify equation numbering against the final PDF before typesetting the reference sentence. |
| Longyang Road station topology and capacity data | Local station config and model files. | Official or model-source evidence for five-line configuration, facility capacities, and geometry extraction. |
| Gate capacity and queue-area depth values | `run_config.json` and line-specific queue-depth settings. | Whether values are measured, inferred from design, or scenario assumptions. |
| Older ACO, old Mode 1, and robustness results | `docs/paper_draft_cn.md` and older output files. | Exclude from current manuscript unless rerun under the current formal AA* implementation. Current Mode 1 is included, but old Mode 1 result tables are not. |
| Pathfinder cross-validation | Local Pathfinder outputs under `pathfinder\...` and comparison scripts. | Exact scenario match, Pathfinder version, behavior settings, and result consistency. |

## Bibliographic Hygiene Rules

- Prefer DOI links or publisher pages for journal articles.
- For software manuals, cite the exact version used in the experiment.
- For Chinese industry statistics, cite the original CAMET report page or PDF, not a media repost.
- Do not copy abstracts or long passages into the manuscript.
- If a field cannot be verified, mark it `[CHECK]` rather than inventing it.
