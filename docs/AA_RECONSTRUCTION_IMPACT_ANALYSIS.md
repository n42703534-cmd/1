# Adaptive Queue-Aware A* 重建影响分析

更新时间：2026-07-21

本文件在本轮代码修改前生成。结论来自当前 `network.py`、`single_path_routing.py`、`algorithm_comparison.py`、测试和人口/在途数据结构，不把目标结果当作实现前提。

## 1. 当前正式调用方法

- `network.py` 交互式工作流当前调用 `MesoscopicCurrentQueueAwareAStar`。
- `algorithm_comparison.py` 默认比较同样调用 `MesoscopicCurrentQueueAwareAStar`。
- `AdaptiveQueueAwareAStar` 当前被显示为 `LegacyInertiaAblation`，只在专用介观比较脚本中作为历史对照运行。

因此，当前默认正式AA不是原始预测AA，而是介观当前队列算法。

## 2. 当前方法的预测与搜索事实

### 默认介观当前队列版

- 使用完整图 `networkx.astar_path`。
- 边代价为共同物理旅行时间加当前资源队列 `Q_now / mu`。
- 不使用未来确定到达，也不使用累计ETA预测队列。
- 使用自动识别的129个决策节点、节点离开申请预算、路径段承诺和后代资源可达统计。
- `_mesoscopic_step_path_cache` 的键实质为 `(method, node)`，并按仿真时步清空；同一节点同一时步的所有批次直接复用第一次得到的完整路径。

### 历史预测AA

- `AdaptiveQueueAwareAStar` 能沿给定路径累计ETA并按事件预测资源队列。
- 但搜索先生成静态结构候选，每个出口最多保留 `K_CANDIDATE_PATHS=3`，然后只在候选中评分。
- 路径状态按节点保存在 `_our_guidance_state`，同节点来源组共享路径。
- 使用2秒保持、3%切换、20%强制切换、50%恶化和2%改善等多重惯性规则。

因此历史版本也不满足本轮“批次独立、无固定K、时间依赖A*”要求。

## 3. 当前人口和批次字段

### 节点实体

- `people`：节点实体总人数。
- `people_dict`：按线路汇总。
- `source_group_dict`：按列车、车厢/分区、站厅或换乘来源组汇总。
- 介观实验代码另有 `_mesoscopic_cohorts`，保存来源组、到达时间、人数和复杂路径段承诺。

### 在途实体

`_transit_queue` 保存：

```text
u, v, amount, depart_time, arrive_time,
resource_id, service_capacity_consumed,
line_shares, source_group_shares, travel_time
```

介观实验记录还可能携带 `cohort_state`。人员到达节点后恢复到 `people`、`people_dict` 和 `source_group_dict`。

### 当前逻辑队列

- `_resource_queues` 是上一轮物理分配后按资源记录的被拒申请量。
- `_resource_queue_sources` 保存这些拒绝量所在的上游节点。
- 它没有严格保存 `source_group/arrival_time/current_path/queue_enter_time`，因此还不是本轮定义的真实批次资源队列。

### 当前预测到达

- `_transit_queue` 中显式 `confirmed_arrival_resource_id` 可作为尚未消费资源的确定未来到达。
- 普通在途记录带 `service_capacity_consumed=True`，不能在同一设施处重复计入。
- 当前不存在“同一决策轮前面批次刚完成路径分配”的临时预测事件表。

## 4. 不属于原AA最小实现的介观内容

下列内容保留代码以便历史复现，但将退出默认正式AA调用链：

1. 自动识别129个决策节点；
2. `node_integer_departure_budget()`；
3. 到下一决策节点的复杂路径段承诺；
4. `_mesoscopic_descendants_cache` 和全图后代资源可达需求；
5. 介观资源闲置诊断作为正式AA路由输入；
6. `(method, node)`完整路径时步缓存；
7. `MesoscopicCurrentQueueAwareAStar`默认入口。

## 5. 本轮保留、停用和修改范围

### 保留且冻结

- `physical_edge_travel_time()`；
- `edge_resource_id()`和共享容量桶；
- `resource_integer_capacity_for_step()`；
- `_integerize_moves()`的申请上限修正；
- `_apply_destination_receiving_limits()`；
- `_schedule_moves_as_transit()`的整数在途调度；
- 服务节点空间豁免、普通空间回堵、4.0人/m²既有接收边界；
- 382条欧氏距离边；
- ImprovedAStar路由规则和物理执行层。

### 停用但不删除

- 两个 `Mesoscopic*` 方法的默认入口；
- 自动决策节点和节点离开预算在正式AA中的调用；
- 介观完整路径缓存；
- 历史K=3候选和多重惯性在正式AA中的调用。

### 最小必要修改

1. 增加轻量AA批次状态：`source_group, arrival_time, amount, current_node, current_path, waiting_resource, queue_enter_time`。
2. 增加按批次的真实资源逻辑队列；人员实体仍只计在节点中。
3. 实现无固定K的时间依赖A*/标签设置搜索。
4. 增加本轮临时预测事件，并在每个批次选路后立即更新。
5. 增加普通空间节点的确定到达、预计出流和接收等待预测。
6. 增加一个独立改路收益指标和单个实验阈值；不得影响物理层。
7. 统一Improved和AA等待分类指标。
8. 恢复 `AdaptiveQueueAwareAStar` 为默认正式AA入口。

预计涉及函数：

```text
single_path_routing.py:
  predicted_resource_queue_at_time
  新增 time_dependent_astar / path ETA detail

network.py:
  get_step_moves
  _integerize_moves（仅批次元数据衔接，不改物理容量）
  _schedule_moves_as_transit
  _process_transit_arrivals
  _run_simulation_for_metrics_core
  新增轻量批次/资源队列/空间预测辅助函数

algorithm_comparison.py:
  默认正式AA方法和统一指标输出

test_routing_regressions.py:
  新增11类小网络测试
```

## 6. 逐项影响边界

| 修改 | 路径选择 | 人员移动 | 设施容量 | 排队统计 | 拥堵统计 | T100 | 守恒 |
|---|---|---|---|---|---|---|---|
| 批次独立时间依赖A* | 会改变 | 不直接改变 | 不变 | 可能改变队列归属 | 间接改变 | 可能显著改变 | 不应改变 |
| 同轮临时预测事件 | 会改变后续批次路径 | 不直接改变 | 不变 | 不作为实体重复计数 | 间接改变 | 可能改变 | 不应改变 |
| 真实资源逻辑队列 | 支持等待/改路 | 未获准者仍留节点 | 不变 | 口径改变且更严格 | 间接改变 | 可能改变 | 队列不重复加实体 |
| 空间接收预测 | 会避开预计满载区域 | 实际接收仍由共同层决定 | 不变 | 可分类为空间阻塞 | 连续密度统计函数不变 | 可能改变 | 不应改变 |
| 单阈值改路 | 只改变排队批次路径 | 已在途人员不变 | 不变 | 队列退出/入尾 | 间接改变 | 需敏感性实验 | 不应改变 |
| 统一等待指标 | 不改变 | 不改变 | 不变 | 改善可比性 | 不改变原始密度 | 不改变 | 不改变 |

## 7. 小网络验证方案

修改后先验证：

1. 两个同节点批次：第一批选择短而低容量A，临时事件更新后第二批可选择B。
2. 当前队列为0但有确定未来到达：当前队列版选A，预测版避开A。
3. 后续资源ETA包含前面全部等待和旅行时间。
4. 下游空间即将满载时产生非零空间等待或不可行标签。
5. 排队批次仅在单一收益阈值满足时改路。
6. 改路退出原队列并进入新队尾，不继承排队位置。
7. 已在途/已进入设施人员不能改路。
8. 每批每时步最多评价一次，不允许同一步A→B→A。
9. Improved与AA调用同一等待分类函数。
10. 任意时步保持 `节点实体 + 在途实体 + 已疏散 = 初始人口`；逻辑资源队列不得重复加入守恒和式。

通过这些测试后，才运行Mode 1、中负荷和17,905人场景B。

## 8. 修改前风险结论

- 重新实现会改变AA路径分配和T100，但不授权改变物理参数。
- 时间依赖搜索加逐批次临时更新可能显著增加运行时间，需要缓存静态下界和资源映射，但不能缓存动态完整路径。
- “排队批次可改路”与“未获准者保留当前路径”要求建立持久批次逻辑队列；若只继续使用汇总 `_resource_queues`，无法正确实现。
- 空间预计出流只能使用当前可确定状态。没有未来真实路由信息时不得伪造出流；预测误差必须记录。
- 0.15和0.20不是本项目实测参数，只能在有文献来源确认后作为敏感性实验。正式基础实现首先使用 `g_min=0`，它是无额外行为阈值的算法边界，不是标定结论。
