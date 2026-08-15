# FIRST — 现行有效代码工作区

> 建立于 2026-07-26。本目录是从 `../network/` 提取的**干净工作区**：只包含当前有效的代码、
> 必要输入和设计文档。`../network/` 从此**冻结为历史档案**，不再修改；所有后续开发、
> 实验都在本目录进行，结果输出也会生成在本目录下（`outputs/`）。

## 一、核心仿真链（5 个文件，互相依赖，缺一不可）

| 文件 | 作用 |
|---|---|
| `network.py` | 共享物理引擎 + 主仿真流程 + 指标统计 |
| `single_path_routing.py` | 路由算法（PaperImprovedAStar / AdaptiveQueueAwareAStar / 各消融） |
| `lines_config.py` | 车站节点/边/线路配置数据（network.py 中部 import） |
| `calc_platform_dists.py` | Pathfinder 几何配置（PATHFINDER_CONFIG） |
| `split_guidance.py` | 分流引导模块（network.py 顶部 import，必须在场） |

## 二、主实验入口

| 命令 | 产出 |
|---|---|
| `python algorithm_comparison.py --mode 4` | 高负荷 AA vs Improved 对比（论文主结果；`--mode 1` 常规场景；`--algorithm improved/aa/both`） |
| `python network.py` | 交互式选 mode 的系统流程（mode1–4） |
| `python l2_complete_study.py` / `l2_case_study.py` / `l7_obstacle_study.py` | 单线案例与障碍研究 |
| `python sensitivity_analysis.py` / `demand_sensitivity_analysis.py` | 敏感性分析 |
| `python robustness_significance_analysis.py` | 鲁棒性与显著性 |
| `python ablation_experiment.py` / `mesoscopic_comparison.py` | 消融 / 介观基线对比 |

## 三、Pathfinder 验证工具链

| 文件 | 作用 |
|---|---|
| `scenario1_pathfinder_validation.py` | 场景1 Pathfinder 验证主脚本（产出 201–212 系列表） |
| `pathfinder_inject.py` | 把出口分配注入 Pathfinder .txt（`--dry-run` 先看差异） |
| `pth_patcher.py` | .pth 文件补丁工具 |
| `plot_pathfinder_figures.py` | Pathfinder 结果图 |
| `export_exit_distribution.py` / `export_improved_zone_paths.py` / `summarize_route_stages.py` | 导出工具 |
| `203b_scenario1_pathfinder_exit_by_source_group.csv` | pathfinder_inject 的默认输入（按 source group 的出口份额） |

⚠️ 注意：原 `network/pathfinder/` 里的 Pathfinder 模型文件（龙阳路 .txt）所在文件夹存在
文件名编码损坏，自动化工具读不到，**未能复制**。请在资源管理器里手动把它拷进
`FIRST/pathfinder/`，并把中文子文件夹改成英文名（如 `high_load_analysis`）。

## 四、测试与守护（每次改核心代码前后都要跑）

| 命令 | 作用 |
|---|---|
| `python test_routing_regressions.py` | 路由回归测试套件 |
| `python aa_formal_validation.py` | AA 形式化验证 |
| `python -c "import network; network.verify_fast_exact_aa()"` | fast/exact 双实现 120s 逐步等价校验 |

## 五、出图与成文（按需运行，不影响仿真）

`make_nature_figures.py`、`make_publication_figures_v2.py`、`build_high_load_results_doc.py`、
`build_algorithm_method_chapter.py`、`build_algorithm_method_chapter_tust_v2.py`、
`generate_doc.py`、`methodology.py`、`flow_distribution.py`、`algorithm_benchmark.py`、
`compare_planning_methods_like_bjut.py`、`l7_waiting_zone_algorithm_compare.py`、
`select_single_path_cases.py`、`select_failure_cases.py`、`algorithm_layer_snapshot_eval.py`、
`storage_spillback_diagnostic.py`、`make_nature_figures_R*.R`、`reconstruct_complete_routes.ps1`

## 六、docs/ — 设计决策文档与论文草稿

`aa_*_definition.md`（AA 队列/改道/时变A*定义）、`mesoscopic_cohort_design.md`、
`improved_temporary_high_cost_pending_acceptance.md`、`step6b_acceptance_pending_report.md`、
`step5c/6/7_report.md`、`version_snapshot.md`、`CODE_REVIEW_FINDINGS.md`、
`AA_RECONSTRUCTION_*.md`、`undefined_edge_audit.md`、`paper_draft_cn.md`、`chapter1_*.md`

## 七、明确排除在外的东西（都留在 ../network/ 原处）

- 历史快照目录：`backups/`、`staged_modifications/`、`legacy_obsolete/`、`.codex_backups/`
- 依赖残留：`__tmp_py38_deps/`、`__vendor_site_packages/`、`__pycache__/`、`tmp/`
- 旧调参诊断：`compare/`
- 死文件：`single_path_routing_orig.py`、`single_path_routing_test.py`（无任何现行引用）
- 历史结果文件（PNG/SVG/CSV/docx/PDF）：全部可由上述脚本重新生成，或属存档

## 八、工作约定

1. **只在 FIRST 里改代码**；`../network/` 是只读档案。
2. 改核心链任何文件之前先跑第四节的三个校验，改完再跑一遍。
3. 不再手工拷贝目录做备份——需要版本控制时在本目录 `git init`（待定）。
