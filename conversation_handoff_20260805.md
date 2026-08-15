# AA / ImprovedAStar 项目对话交接记录

更新时间：2026-08-05
项目目录：`C:\Users\28146\Desktop\network\FIRST`

## 1. 当前目标

本项目是多线地铁换乘站疏散仿真，主要比较：

- `ImprovedAStar`：保留文献 Improved A* 的密度和障碍感知路径代价结构。
- `AdaptiveQueueAwareAStar`（AA）：当前项目的预测型、排队感知、动态重规划算法。

主要关注：

- 全站 T95、T99、T100 和人员守恒；
- L2、L7、L16、L18、Maglev 各线路清空时间；
- 各出入口和闸机人数；
- 跨线疏散的来源线路、实际路径和最终出口；
- Gate Queue、Gate Approach、服务容量、排队和路径连续性；
- 结果是否符合真实地铁站的人流分布，而不是出现一个闸机承担全部人流、相邻闸机为 0 人等明显不合理情况。

## 2. 用户的关键建模要求

### 2.1 ImprovedAStar

- Improved A* 的正式基线不使用额外的 `Q/mu` 闸机等待项。当前正式 Mode 4 入口中：

  ```python
  graph.graph["improved_gate_queue_term"] = False
  graph.graph["improved_shared_travel_time"] = False
  graph.graph["density_dependent_flow"] = True
  graph.graph["spillback_enabled"] = True
  ```

- Improved 的核心路径规则是密度阈值和动态高代价/不可通行处理，不是 AA 的预测排队换路机制。
- 普通跨线准入已从最初的 `L7 -> L2` 特例扩展成通用框架，但必须区分：
  - 新人员是否被允许进入另一条线路的跨线分支；
  - 已经进入跨线分支的人员不能因为下游节点状态变化而被卡死。
- 现有通用跨线控制不应擅自改成“所有线路必须全部闸机超过密度 3 才能跨线”，除非明确作为运营政策。正常物理建模更适合判断具体跨线入口和目标闸机的可接受状态。

### 2.2 AA

- AA 的 Gate Approach 横向换闸逻辑已经通过既有验收，不要重新设计拓扑。
- 已验收且不得随意修改的规则：
  - 真实 Queue -> Queue 横向路径；
  - `gate_switch_only`；
  - 不经过 Stair；
  - 不使用 common hall；
  - 不允许循环换闸；
  - 真实有向路径限制；
  - 20% 改善阈值；
  - 单次换闸限制；
  - 路径报告和人数守恒。
- Gate Approach 的正式顺序必须是：

  ```text
  Gate Queue 当前等待人员
  -> 按 queue_enter_time FIFO 排序
  -> 根据当前 Gate 本时间步真实剩余服务容量预留 committed 人员
  -> committed 人员固定进入当前 Gate，不参与换闸
  -> 剩余 waiting 人员再进行 stay vs switch 比较
  -> 改善达到 20% 才允许横向换闸
  -> 最后执行容量接受和整数化
  ```

- 不能把 `_integerize_aa_batch_requests()` 之后的部分接受当成“决策前已经 committed”。
- 已加入 committed 统计和相关回归测试；不要为了消除 L2 的 50/50 而人工把 300 人拆成固定 20 人批次。

## 3. 已经确认的主要问题

### 3.1 路径/拓扑问题

- `L7`、`L2` 等线路的路径分布曾出现整个平台等待区只有单一路径的问题。
- `L18` 的部分换乘流经过 `VN_L18_Hall_Split_A/B`，其中 A、B 对闸机形成硬分组；如果不增加真实连接，路径不能自然覆盖所有相邻闸机。
- Maglev 更严重：部分楼梯/扶梯只连接到一个对应闸机，没有“第一近、第二近、第三近”的备用路径。
- 这些是物理拓扑/候选路径不足问题，不能只靠在出口分配阶段强行制造人数。

### 3.2 出入口覆盖问题

- 仅依靠单批次确定性最短路，不能保证相邻闸机都会获得流量。
- 但不能把“每个出口必须有人”当成物理模型硬约束，否则会人为改路。
- 出口覆盖可以作为运营策略或单独消融实验，但不应隐藏在正式 AA 路径规划函数中。
- 结果中出现相邻闸机 0 人时，应先审计：
  - 是否存在真实候选边；
  - 楼梯/扶梯到闸机的连接是否完整；
  - 闸机到出口是否存在路径；
  - 是否被错误的跨线控制或密度边删除；
  - 是否因单批次确定性选路造成集中。

### 3.3 AA 运行效率问题

AA 当前不是逻辑上必然错误，但运行效率仍然很差。最近一次 AA 运行日志显示：

```text
sim_time=300.0s
wall_clock=239.44s
evacuated=8285
remaining=9620
astar_calls=6924
old_path_evaluations=1341345
same_path_reuse=0
committed_replan_skips=11775
committed_path_refreshes=1341345
```

说明当前主要性能瓶颈是：

- 大量 `old_path_evaluation`；
- `same_path_reuse=0`，路径复用没有生效；
- committed batch 仍发生大量路径刷新；
- Gate 候选搜索和路径预测调用次数过多。

后续性能优化应遵循：

1. 对尚未到达决策节点、且队列/容量/空间状态未有效变化的 batch 复用已有预测。
2. 只有队列、容量、空间状态发生有效变化时刷新路径。
3. 单独统计 Gate 候选 A* 调用次数和耗时。
4. Gate Approach 候选搜索只对真正满足触发条件的 waiting batch 执行。

性能优化不能改变 AA 的路径选择规则和物理容量规则。

## 4. 本轮真正修复的问题

此前 Improved Mode 4 出现：

```text
target=17905
evacuated=17884
remaining=21
completed=False
termination_reason=time_limit
T100=6000s
```

唯一失败的路径验证组是：

```text
source_group = L16_Maglev_transfer
initial_people = 21
raw_route_count = 0
summed_route_people = 0
people_error = -21
```

根因不是物理拓扑没有出口路径。经检查，`Transfer_L16_Maglev_Passageway` 到出口实际上有 10 条拓扑可达路径。真正原因是：

1. 通用 Improved 跨线控制把部分内部 `Arrival -> Entrance` 继续边误当成了新的跨线入口。
2. 因此已经在跨线分支中的人员仍被再次执行跨线准入限制。
3. 该分支被高代价阻断，导致 21 人停留到时间上限。

本轮修改采用最小侵入方式：

- 方向命名节点先按名称解析源线路，例如 `VN_L16_to_Maglev_Entrance` 的源线路是 `L16`。
- 普通跨线准入只在真实入口节点或平台入口执行，不把内部 `Arrival -> Entrance` 继续边当成新准入点。
- 对已经位于 `Transfer_*` 节点的人员，只允许其继续通过当前已进入的跨线分支；临时恢复该分支入口边的正常代价，不新增拓扑边，也不允许新的人员绕过跨线准入。
- 临时恢复只用于当前已进入分支的路径搜索，原有动态权重在本时间步结束后仍恢复。

主要实现位置：

- `network.py:3972`：`_crossline_source_line_id()`。
- `network.py:4053`：`_improved_ordinary_crossline_controls()`。
- `network.py:4128`：`_paper_refresh_temporary_high_cost_weights()`。
- `network.py:4403`：`_paper_committed_transfer_edges()`。
- `network.py:4419`：`_paper_plan_path()`，支持只对已经进入分支的边临时恢复正常代价。
- `network.py:4747` 及之后：Improved 单步移动中使用该逻辑。

## 5. 最新验证结果

### 5.1 回归测试

```text
147 tests in 2.238s
OK
```

新增/重点测试包括：

- `test_improved_crossline_controls_cover_all_transfer_line_pairs`
- `test_improved_l16_maglev_transfer_continues_after_entry`
- Gate Queue committed/FIFO/batch split 测试；
- 多标签时间依赖 A* 测试；
- L2/L7 residual reroute 测试；
- 路径连续性、人数守恒、raw/merged facility audit 测试。

### 5.2 修复后 Improved Mode 4

结果目录：

```text
C:\Users\28146\Desktop\network\FIRST\outputs\algorithm_compare\mode4_20260805_111839\ImprovedAStar
```

正式结果：

```text
target_people       = 17905
evacuated_people     = 17905
remaining_people     = 0
completed            = True
termination_reason   = completed
T95_seconds          = 1102
T99_seconds          = 1275
T100_seconds         = 1443
mean_total_evac_time = 448.735 s/person
```

线路清空结果：

```text
L2       T95=790 s,  clearance=1440 s
L7       T95=1247 s, clearance=1443 s, last line=True
L16      T95=358 s,  clearance=1280 s
L18      T95=1134 s, clearance=1279 s
Maglev   T95=517 s,  clearance=590 s
```

路径审计：

- `raw_route_validation.csv` 中 `validation_passed=False` 的记录数为 `0`。
- `L16_Maglev_transfer` 现在有 `1` 条完整 raw route，21 人守恒。
- Pathfinder route allocation 输出显示：151 条完整路线，17905 人，人数守恒误差 0，断裂路线 0，循环路线 0。

### 5.3 最新 AA 运行状态

本次为同配置 AA 运行，目录：

```text
C:\Users\28146\Desktop\network\FIRST\outputs\algorithm_compare\mode4_20260805_111940\AdaptiveQueueAwareAStar
```

该运行在 240 秒工具执行窗口内被终止，不能作为完整 AA 结果，也不能拿中间值和 Improved 的最终值正式比较。终止前：

```text
sim_time=300 s
wall_clock=239.44 s
evacuated=8285
remaining=9620
astar_calls=6924
old_path_evaluations=1341345
same_path_reuse=0
```

因此当前可以确认：

- Improved 的 6000 秒卡死已经修复。
- AA 的运行效率问题仍然存在。
- 还不能据此确认 AA 的最终 T100 或两算法最终性能差异。

## 6. 代码备份

本轮已验证版本备份：

```text
C:\Users\28146\Desktop\network\FIRST\backups\mode4_l16_maglev_continuation_fix_20260805
```

备份文件：

- `network.py`
- `test_routing_regressions.py`
- `algorithm_comparison.py`

## 7. 下一步建议

优先级必须是：

1. 不再修改已通过的 Improved 跨线拓扑和 AA Gate Approach 拓扑。
2. 先对 AA 做性能审计，重点处理 `same_path_reuse=0` 和 `old_path_evaluations`。
3. 加入有效状态签名：只有队列、容量、空间状态实质变化才刷新预测路径。
4. 让 committed/intermediate batch 复用已有路径，除非到达真正决策节点或状态签名改变。
5. 限制 Gate Approach 候选 A* 只对触发条件成立且未 committed 的 waiting batch 执行。
6. 优化后再用完整 Mode 4 同配置运行 Improved 和 AA。
7. 最终比较必须来自同一配置、同一人口、同一设施容量、同一边接收密度限制和同一停止条件。

不要做以下事情：

- 不要为了消除 50/50 人工拆分 300 人批次。
- 不要为了让每个出口有流量而在路径输出阶段强行分流。
- 不要用出口覆盖策略掩盖楼梯/扶梯到闸机的真实拓扑缺失。
- 不要把 AA 未完成的中间运行当成最终性能结果。
- 不要把本轮 Improved 的跨线继续通行修复误认为 AA 的性能优化。

## 8. 新对话开始时建议直接说明

可以在新对话中直接发送：

> 请读取 `C:\Users\28146\Desktop\network\FIRST\conversation_handoff_20260805.md`，从交接记录继续。当前 Improved Mode 4 已从 6000 秒超时修复为 T100=1443 秒并通过 147/147 回归测试；AA 尚未完成，下一步只审计 AA 的路径复用和预测刷新效率，不改变已通过的拓扑、跨线准入和 Gate Approach 规则。

