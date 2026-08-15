# 地铁疏散网络流代码审查与重构记录

更新时间：2026-07-21

## 1. 实际调用链

正式运行链已统一为：

```text
network.py / algorithm_comparison.py
    -> single_path_routing.py（唯一正式路由实现）
    -> network.get_step_moves()（生成单下一跳移动请求）
    -> network._integerize_moves()（共同整数化与共享资源容量）
    -> network._apply_destination_receiving_limits()（共同接收/回堵）
    -> network._schedule_moves_as_transit()（共同物理旅行）
```

`single_path_routing_test.py` 只包含自动化测试，不再替换 `network.spr`、容量函数、接收函数或路径函数。项目中不再存在运行时切换的 Production/Test 两套 AA。

## 2. 已发现并修复的问题

### P0：共同物理执行层

- 原 `_edge_flow_credit[(u, v)]` 会让多个入口边分别使用一次同一楼梯、扶梯或闸机容量。现以 `edge_resource_id()` 聚合至唯一物理资源，共享 `_resource_flow_credit`。
- 所有请求先按源节点人数约束，再按资源统一整数分配，最后应用下游空间接收限制。
- 容量不足的请求留在原节点并形成 `_resource_queues`；不会再被容量驱动地塞入未被路由选中的其它边。
- 对相同优先级来源采用确定性轮转，消除固定节点遍历顺序的长期优先权。
- 节点存储容量改为 `有效面积 × 4.0 人/平方米`，删除 `出流能力 × 18 秒` 的非物理缓冲。
- Fruin 速度—密度关系同时用于旅行时间与密度相关接收能力，删除未使用且会造成口径混淆的 Weidmann 5.4 人/平方米代码。
- 回堵和密度相关流量在正式算法比较中对 Improved 与 AA 同时开启。

### P0：队列和旅行时间

- 等待队列定义为“尚未获得物理资源容量、仍在上游等待的人”，不再用设施节点内人员代替。
- 设施内/边上人员属于在途人员，不重复计入等待队列。
- `resource_queueing_time = Σ(resource_waiting_people) × DELTA_T`。
- `physical_edge_travel_time()` 是 Improved、AA、运输调度、ETA 预测和速度指标的共同物理函数。
- 平台到垂直设施的水平段、垂直段分别计时；站厅/闸机/出口连接按平面通道处理。
- 零长度边旅行时间和统计速度均为 0，不再注入最少 1 秒或虚假自由流速度。
- 边密度只读取实际在该边运输的人，不把下游节点人群重复投影到每条入口边。

### P1：唯一 AA 与可解释预测

- 唯一正式实现为 `single_path_routing.py` 中的 `AdaptiveQueueAwareAStar`。
- AA 采用缓存的、无环、按关键设施区分的 A* 候选路径，每个出口最多保留 3 条有意义候选；执行仍是每节点每步一个下一跳。
- 当前预测按到达事件逐段扣除服务量，晚到人员不会在到达前被服务。
- 预测只包含当前真实资源队列与已经进入整数运输队列的承诺；没有 EMA、浮点路径预留、校准系数或任意等待缓冲。
- 删除 `source_release_wait`/`_mean_fifo_source_wait` 重复等待逻辑。
- 最终获准的整数移动承诺记录 `resource_id`、`amount`、`eta/arrive_time`、`source_node` 和 `path_version`。
- 删除旧的 `use_test_routing()`、monkeypatch、测试版整数预留以及含糊的 `"Improved"` 分流别名。

### P1：配置校验

- 清理 L2 楼梯方向字符串中的前导空格；构图时统一 `strip().lower()` 并校验合法方向。
- 清理 35 条引用未定义 L2 扶梯节点的陈旧配置边；此类边此前均被静默跳过，因此未删除实际已构建的拓扑连接。
- 构图前发现任何未定义端点会抛出 `ValueError`，错误中列出配置组、起点、终点和缺失节点。
- 20 个闸机仍保留集中定义的 `count × 2.0 m²` 兼容面积，用于旧接口、绘图和配置报告；闸机现标记为 `density_exempt=True`、`spatial_storage_enabled=False`，该面积不再限制储存或参与空间密度。
- `VN_L7_Corner_1 <-> VN_L7_Corner_2` 修正为 `virtual_channel`，不再错误标记为出口边。
- 当前共识别 382 条 `euclidean_fallback` 局部边；其长度由相邻节点坐标按 CAD 比例计算，符合当前网络流模型约定。后续只需核查连接是否表示实际直接可达；存在墙体或转弯时应增加中间虚拟节点，而不是要求逐条填写整段路线距离。

### P2：性能和状态指标

- 每仿真步只完整更新一次动态边权。
- 缓存静态 A* 候选路径、边有效面积和物理资源 ID；不再为每个活动节点复制最短距离字典。
- 修复“缓存密度为 0 时仍遍历整个在途队列”的性能缺陷。
- 详细节点/边时间序列默认按 2 秒采样；`collect_detailed_series=False` 可关闭详细序列，不改变容量、移动或精确累计指标。
- 新增 `completed`、`remaining_people`、`termination_reason`、`resource_queueing_time`、`mean_queueing_time`、`mean_moving_time`、`mean_total_evacuation_time`。达到时间上限不会被报告为正常完成。

### 2026-07-21 第二轮物理语义修正

- 闸机是点式服务资源；楼梯和扶梯节点是拓扑服务点。默认均不使用节点面积储存或节点空间密度，设施内部占用由在途边表示。
- 进入设施的边消费设施共享容量；离开设施的边不再继承源设施容量，避免入口、出口各限流一次。
- `_resource_queues` 明确定义为当前时间步的等待意图。人员实体仍在上游节点，可以下一步换路，它不是永久 FIFO 人员队列。
- 正常在途记录带 `service_capacity_consumed=True`：这些人已经获得入口容量并处于设施内，不能在到达设施节点时再次加入同一资源等待队列。只有明确标注尚待服务的 `confirmed_arrival_resource_id` 才属于未来确认到达。
- 空间接收拥堵密度继续使用既有 Fruin 模型的 4.0 人/m²边界，没有采用无依据的 5.0 人/m²建议。中度阈值保留 3.0，重度报告阈值调整为 3.5，使其严格位于阻塞密度以下；3.5 是内部诊断分带，不宣称为新的实测基本图参数。

## 3. 当前算法公式

共同基础量：

```text
t_phys(u,v) = physical_edge_travel_time(G,u,v)
```

四种正式/消融模式：

```text
PaperImprovedAStar:       alpha × length + beta × t_phys
DensityOnlyAStar:         t_phys
CurrentQueueAwareAStar:   t_phys + Q_now / mu
AdaptiveQueueAwareAStar:  t_phys + Q_pred(cumulative_resource_ETA) / mu
```

预测队列按整数到达事件演化：

```text
每个事件到达前：Q = max(Q - mu × Δt, 0)
事件到达时：    Q = Q + integer_arrival
预测时刻前：    Q = max(Q - mu × remaining_time, 0)
```

候选路径从当前仿真时刻沿路径逐边递推，后续资源 ETA 包含此前全部物理旅行时间和预计等待时间。新候选路径、保留路径、惯性换路与恶化判断共用 `evaluate_candidate_path_with_cumulative_eta()`。

## 4. 公平性与守恒

- Improved 与 AA 共用网络、人口、时间步、旅行时间、资源容量、整数化、节点接收、在途空间预留、回堵和指标口径，但各自保留算法定义中的搜索、缓存和换路机制。
- 严格内部消融仅比较 DensityOnly、CurrentQueueAware 与 AdaptiveQueueAware；三者共用 K 候选路径、缓存、惯性、累计 ETA 和物理执行层，区别只在等待代价。
- 算法只决定移动请求的下一跳；物理执行器决定本步最终获准的整数人数。
- 自动化守恒测试验证：节点人数 + 在途人数 + 已疏散人数保持不变。
- 同一设施容量只在其共享资源桶中消费一次，不再按入口边重复计算。

## 5. 自动化验证

执行：

```powershell
python -m py_compile lines_config.py network.py single_path_routing.py single_path_routing_test.py algorithm_comparison.py test_routing_regressions.py
python -m unittest -v test_routing_regressions.py single_path_routing_test.py
```

结果：语法检查通过；25 项测试全部通过。测试覆盖共享设施容量、小数信用、确定性公平轮转、预测队列消退、晚到事件、旅行时间一致性、配置错误、方向清洗、超时状态、整数人员守恒和既有回堵/引导回归。

`pytest` 未安装在当前 Python 环境，因此使用标准库 `unittest` 完成等价自动化验证，未擅自安装依赖。

## 6. 小规模烟雾测试

重构后曾以 Mode 1 状态分别对 Improved 与 AA 运行到 10 秒：两者均未误报完成，剩余人数均为 2187，人员总量均守恒。该测试只验证短时执行链，不代表完整疏散结果。

未运行 17905 人完整 Mode 4。此次改动修正了容量重复、18 秒存储缓冲和队列口径，完整结果与旧模型必然可能显著不同，不能把旧的 1300/1400 秒当作回归断言。

## 7. 尚未完成或需要数据支持的事项

- 382 条局部边采用坐标欧氏距离生成，不视为默认错误；仍需核查每条拓扑连接是否在现实中直接可达。
- 闸机兼容面积不是排队区实测面积，且已从储存和密度计算中豁免，因此不要求补充20个闸机面积。
- `_transit_queue` 仍是列表，没有改成最小堆。大量模块需要按边、线路和来源遍历全部在途项，直接替换为单一到达堆会破坏这些查询；应在性能剖析后增加“到达堆 + 边索引”双索引结构。
- 一些诊断、固定路径和鲁棒性辅助流程仍使用全对最短路；正式仿真核心已改为出口反向距离，辅助流程需单独验证后再迁移。
- `calc_platform_dists.py` 只负责从 Pathfinder 坐标生成站台至垂直设施距离，本轮审计未发现需要改变其输入含义的错误，因此未修改。
- 未生成修改前后完整运行时间及完整小工况 T100 对比：旧模型与新模型物理定义不同，且本轮未运行耗时完整仿真。后续应在固定提交、同一机器和同一输入上分别记录 wall-clock 与结果，不应引用历史混合版本数据。

## 8. 推荐运行方式

```powershell
# 保留 network.py 的交互式绘图和完整工作流
python network.py

# Mode 4：Improved 与正式 AA 公平比较
python algorithm_comparison.py --mode 4

# Mode 4：四种等待代价消融
python algorithm_comparison.py --mode 4 --ablation
```

## 9. 2026-07-21 完整 Mode 4 诊断结果（17,905 人）

本节结果来自同一代码版本、同一人口、同一时间步和同一物理执行层下的六次完整运行，原始数据见 `storage_spillback_diagnostic.csv`。没有按目标疏散时间加入校准系数。

| 场景 | 算法 | 是否完成 | T100 / 停止时间 (s) | 剩余人数 | 运行时间 (s) |
|---|---|---:|---:|---:|---:|
| A：旧式服务节点空间存储 + 回溢 | ImprovedAStar | 否（超时） | 6000.0 | 355 | 207.8 |
| A：旧式服务节点空间存储 + 回溢 | AdaptiveQueueAwareAStar | 是 | 3035.5 | 0 | 115.1 |
| B：点服务/拓扑服务节点免空间存储 + 回溢 | ImprovedAStar | 是 | 1461.0 | 0 | 45.1 |
| B：点服务/拓扑服务节点免空间存储 + 回溢 | AdaptiveQueueAwareAStar | 是 | 1777.5 | 0 | 70.1 |
| C：B 的语义 + 关闭空间回溢（仅诊断） | ImprovedAStar | 是 | 1474.0 | 0 | 50.8 |
| C：B 的语义 + 关闭空间回溢（仅诊断） | AdaptiveQueueAwareAStar | 是 | 1777.5 | 0 | 70.3 |

结论：旧输出中 Improved 的 6000 秒确实是时间上限而非正常清空；本次可复现实验在 6000 秒仍有 355 人。旧 AA 的 3897 秒不能再作为当前实现的验证结果；当前 A 为 3035.5 秒，正式 B 为 1777.5 秒。服务节点面积豁免对结果影响很大，但当前 AA 仍慢于 Improved（316.5 秒），因此不能声称本轮修改已经证明 AA 优于 Improved，也不能把 1200--1300 秒当作物理正确性的回归断言。

正式 B 场景的前五资源排队瓶颈：

- Improved：`Gate_L18_E1 -> VN_L18_Exit12_Entrance`、`Gate_L2_N_West`、`Escalator_L2_down1`、`Stair_L7_1`、`Stair_Maglev_6`。
- AA：`Gate_L7_West_Vert`、`Gate_L7_N_West`、`Stair_L7_1`、`Stair_L2_5`、`Escalator_L2_up1`。

正式 B 场景的前五空间回溢节点：

- Improved：`VN_L7toL2_Hall_Arrival`、`VN_L2_to_L16_Passageway_Start`、`VN_7to2_Entrance`、`Train_L2_1_Car1`、`Train_L2_1_Car2`。
- AA：`VN_L18_Exit12_Entrance`、`VN_L18_Exit17_Entrance`、`VN_L2_to_L16_Passageway_Start`、`VN_2to7_Exit`、`Train_L2_1_Car1`。

自动验证最终状态：Python 语法检查通过；`python -m unittest -q test_routing_regressions.py single_path_routing_test.py` 共 34 项测试全部通过，包括累计 ETA、事件时序队列、同设施共享容量、独立设施隔离、容量仅消费一次、阈值可达、超时状态和人员守恒。

## 10. 滚动时域介观批次重构（2026-07-21）

### 10.1 结构事实与修正

- 旧节点仅有 `source_group_dict` 汇总量；`_our_guidance_state` 按节点保存路径，确实会让同节点全部来源组使用同一下一跳。
- 新增 `_mesoscopic_cohorts`，以“来源组 × 到达时刻 × 承诺状态”表示自然批次，没有固定批次人数。
- 新增完整图 `MesoscopicPhysicalTimeAStar` 和 `MesoscopicCurrentQueueAwareAStar`。正式介观算法不调用固定 K 候选或旧节点惯性。
- 批次只承诺至下一个决策节点。共享容量和下游空间接收完成后，只有实际获准整数人员获得承诺；被拒绝人员保持未承诺。
- 已承诺批次在中间节点只执行承诺边。完整 Mode 4 两种介观算法的 `nondecision_replans` 都为 0。
- 旧 `AdaptiveQueueAwareAStar` 现标记为 `LegacyInertiaAblation`，仅保留历史对照。正常 `network.py` 和 `algorithm_comparison.py` 比较入口改用 `MesoscopicCurrentQueueAwareAStar`。
- `network.py` 的交互式正式比较不再只对AA拆分L2列车来源组；Improved与介观AA使用相同来源组定义，避免决策单位信息条件不一致。

### 10.2 审计中发现的额外问题

1. `_integerize_moves` 原来会在节点申请量小于节点存量时，把申请放大到全部存量，因为来源分配没有申请上限。旧整节点申请掩盖了该缺陷。现已保证最终分配不超过每条申请。
2. 小数容量信用只在资源收到申请时推进。若介观预算把“当前完整整数信用为0”解释为不申请，低流率资源会永久停滞。当前预算允许正服务率资源保留1人的待审申请；共同整数容量仍可拒绝该申请，拒绝者不会获得承诺，因此没有增加物理通过量。
3. 自动决策节点报告识别129/555个节点，其中22个是虚拟分叉。这些节点满足当前拓扑判据，但是否代表现实可选择通道仍需按CAD/运营语义人工核实。
4. 当前队列瞬时成本导致大量未承诺申请在被拒后下一时步改选。它不是已承诺批次的途中摆荡，但仍是决策层振荡；本轮没有用保持时间或百分比阈值掩盖。

### 10.3 完整场景B结果

| 算法 | T50 | T90 | T95 | T99 | T100 | T100-T99 | 排队人秒 | 距离(m) | 运行时间(s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ImprovedAStar | 426.5 | 1061.0 | 1176.0 | 1387.0 | 1461.0 | 74.0 | 7,539,589.5 | 1,703,664.6 | 62.8 |
| MesoscopicPhysicalTimeAStar | 479.0 | 2493.0 | 3625.5 | 4535.0 | 4762.5 | 227.5 | 390,774.5 | 1,434,283.7 | 305.2 |
| MesoscopicCurrentQueueAwareAStar | 428.0 | 1190.5 | 1661.5 | 2123.0 | 2348.0 | 225.0 | 320,421.0 | 1,469,722.4 | 374.6 |
| LegacyInertiaAblation | 425.0 | 952.0 | 1313.5 | 1690.5 | 1777.5 | 87.0 | 7,677,943.5 | 1,565,003.1 | 101.1 |

四组均完成17,905/17,905，`remaining_people=0`、`termination_reason=completed`。两次完整重跑的四个T100完全一致。

### 10.4 数据支持的原因判断

- 当前队列介观版相对纯物理介观版：T100减少2,414.5秒，排队人秒减少70,353.5，移动距离增加35,438.7m。当前队列信息有明显正作用。
- 当前队列介观版的T50为428.0秒，与Improved的426.5秒接近；主要差距发生在后10%，特别是最后1%：`T100-T99=225秒`，Improved仅74秒。
- 当前队列介观版最后10人来自L7站厅、L7列车和L2→L7换乘，最终经 `VN_L7_Corner_2 -> Exit_L7_7` 为主。L7出口前空间是尾部瓶颈之一。
- 当前队列介观版的空间拒绝主要包括 `VN_L7_Corner_2=5096` 和 `VN_L18_Exit12_Entrance=4136`；连续3.0人/m²暴露为991,590人秒，显著高于Improved的484,033。其较慢不能归因于总移动距离或资源排队人秒，因为这两项反而更低；证据指向空间接收阻塞、长期未使用的可达分支以及尾部滞留。
- 当前队列介观版有630,428次路径决策、94,452次路径段承诺、484,570次拒绝后改选，非决策节点重规划为0。承诺机制消除了途中重规划，但没有消除未承诺申请的时步级振荡。
- 不能从当前四组实验单独量化“删除2秒/百分比惯性”和“删除K=3”各自贡献，因为旧版与介观版同时改变了决策单位、承诺范围和搜索空间。若给出单独秒数将是无依据归因，需要额外正交消融实验。

### 10.5 预测版状态

没有把旧累计ETA路径评分冒充为新的预测搜索。预测成本依赖标签到达时刻；在完整图上需要经过验证的时间依赖A*或标签设置算法。本轮未实现该搜索，因此 `ExperimentalMesoscopicPredictiveQueueAwareAStar` 仅保留名称，不生成结果。

### 10.6 验证

最终执行Python语法检查和45项自动化测试，全部通过。覆盖申请不放大、无固定批次规模、只有获准人员承诺、非决策节点不重规划、到达决策节点清除承诺、一个批次单下一跳、不同自然时刻可选不同下一跳、拒绝者保持未承诺、完整图可选择第四条路线、共享容量、单次容量消费和人员守恒。
# 2026-07-21 predictive-AA reconstruction findings

## Confirmed implementation changes

- Formal AA is again `AdaptiveQueueAwareAStar` and uses a full time-dependent A* search.
- Natural source/arrival batches search independently; no fixed batch size, fixed-K candidate set,
  EMA demand, fractional reservation, waiting multiplier, or new physical calibration coefficient was added.
- The previous mesoscopic methods remain callable only as experimental methods and are not formal defaults.
- Improved routing rules, capacities, speeds, areas, population, time step, shared receiving, integerization
  and spillback code were not intentionally changed in this reconstruction.
- A same-round queue-conservation error was fixed: a rerouted batch is removed from its old logical queue
  before evaluation and appended to the selected queue after evaluation. In the 100 s Mode 2 smoke test,
  reroutes fell from 85,153 to 287 and A-B-A cycles from 81,567 to 23.

## Validation results and blocking defect

- Regression tests: 49/49 pass.
- Mode 1 (2,187 people): all methods complete at 320.5 s. Predictive AA resource-queue person-seconds
  are 54,492.5 versus 55,944.0 for current-queue A* and 78,015.0 for Improved.
- Mode 2 (10,046 people): Improved reaches the 6,000 s limit with 197 people remaining; current-queue
  A* completes at 422.0 s and predictive AA at 419.5 s.
- Mode 4 (17,905 people): Improved reaches the 6,000 s limit with 797 people remaining; current-queue
  A* completes at 685.0 s and predictive AA at 680.5 s. These times are not accepted as a valid comparison
  with the historical ~1,400/~1,300 s baseline.
- All 797 Mode 4 Improved residual people are in infinite-time transit on
  `Platform_L2_Z3_Wait -> Escalator_L2_down1`. The shared scheduler admitted a move whose physical
  travel time was infinite. This makes `in_transit_person_seconds` and mean moving time infinite.
- Because the instruction freezes the common physical layer, this defect is reported rather than silently
  repaired here. Until it is fixed and both algorithms rerun, Mode 2/4 claims that AA outperforms Improved
  are invalid.
- Predictive AA Mode 4 wall-clock runtime is 1,784 s versus 273 s for current-queue A*. Prediction MAE is
  50.44 people with bias -26.39 people, so the predictor systematically underestimates queues.

## Remaining limitations

- The spatial predictor uses an optimistic sum of distinct outgoing service rates; its calibration has not
  been empirically validated.
- `effective_reroute_count` currently means an accepted movement in the same step as a route change; it is
  not a measured counterfactual time saving.
- The requested `g_min` values are sensitivity settings supplied by the task. They are not asserted to be
  measured project parameters or independently literature-validated values.
- Formal full-load validation is computationally expensive because each natural batch runs independent A*;
  dynamic full-path caching is deliberately prohibited.
