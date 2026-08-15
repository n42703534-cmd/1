# Improved 临时高成本状态修正：待验收报告

## 范围

本阶段只修改 Improved 的临时高成本状态、对应诊断与回归用例。未修改：

- AA 路由逻辑；
- 共同物理层；
- 设施容量；
- 闸机服务顺序；
- Improved 的 3.0 人/m²阈值；
- Improved 正常成本公式；
- Improved 固定路径及拥堵状态变化时的重规划规则。

本阶段未运行测试或仿真，所有结果均待用户执行验收。

## 备份

备份目录：

`C:\Users\28146\Desktop\network\network\backups\improved_temporary_high_cost_20260726_093615`

修改前 SHA-256：

| 文件 | SHA-256 |
|---|---|
| network.py | `0417D5CBF246B7347CF62352B04907D579E8CEC35B922425C8CA055496785124` |
| single_path_routing.py | `F3858B1CB30EB2D36A4C2EF677767E7960D493905B6C3552C9581F50029AD730` |
| algorithm_comparison.py | `908B99BF48C762C8E2C02B54E64ECBC13F3C570CAC6ED1EE21F98CF2F8B442C3` |

修改后 SHA-256：

| 文件 | SHA-256 |
|---|---|
| network.py | `847C4CFC1A132EBA732707F1EBF6D1165235BEF3530737B89B476BE848C1B734` |
| single_path_routing.py | `78AEEB96931DB988CBC757549F4C9566F49BCDFFB0F310308F1090E8A2DD5C0A` |
| algorithm_comparison.py | `6081588FBBBB24598A871B4E62E48DA35363B84227442C5C7DF34FA6920D4B94` |

## 实现

1. 每个 Improved 仿真步开始时重新计算所有边的 `sim_weight`。
2. 普通边使用当前边在途密度作为控制密度。
3. 进入 Gate 的边同时读取 Step 7 已验收的真实 Gate 密度，控制密度取“当前边密度”和“目标 Gate 真实密度”中的较大值。这样不会重新引入已排除的上游重复人数。
4. 控制密度严格大于 3.0 人/m²时，仅把当前步 `sim_weight` 设为 `1e6`。
5. 下一步密度回落到不大于 3.0 人/m²时，立即按原 Improved 公式重算正常 `sim_weight`。
6. 不再为 Improved 高密度状态建立删节点路由副本，也不删除基础图边。
7. 不写 `disabled`，不修改静态 `weight`。
8. 当前高成本边集合变化时，继续按原有规则清空 Improved 固定路径缓存并重新规划；集合不变时保留路径锁定。
9. A*使用 `sim_weight`；候选路径总成本也读取同一当前步 `sim_weight`。

## 新增诊断

`diagnostics.json`：

- `temporary_high_cost_events`
- `recovered_next_step_events`
- `high_cost_active_edges`
- `maximum_high_cost_active_edges`
- `stale_high_cost_state_count`
- `last_refresh_time_seconds`

`improved_temporary_high_cost_step_diagnostics.csv` 每步记录：

- 当前步新进入高成本的边数；
- 当前步恢复的边数；
- 当前活跃高成本边数；
- 当前步陈旧状态数。

`improved_temporary_high_cost_trace.csv` 每步记录L18四个Gate和L2四个出口方向：

- 当前真实Gate密度；
- 当前是否处于临时高成本；
- 最近恢复时刻；
- 当前选定路径成本；若当步无人选择，则记录该方向最小入口边成本；
- 当步固定路径选择该方向的人数。

L2对应关系：

| Gate | 出口 |
|---|---|
| Gate_L2_N_West | Exit_L2_2 |
| Gate_L2_N_East | Exit_L2_6 |
| Gate_L2_S_West | Exit_L2_4 |
| Gate_L2_S_East | Exit_L2_3 |

## 待执行回归用例

`ImprovedTemporaryHighCostRegressionTests.test_high_density_edge_recovers_on_the_next_step`

构造状态：

1. 第0步 Gate密度为4.0人/m²，入口边 `sim_weight=1e6`；
2. 第1步 Gate密度降为3.0人/m²；
3. 断言入口边恢复正常成本；
4. 断言基础边仍存在；
5. 断言静态 `weight` 未改变；
6. 断言 `recovered_next_step_events=1`；
7. 断言 `stale_high_cost_state_count=0`。

另有用例检查A*绕开当前步高成本方向，并确认没有删除该边。

## 验收重点

- `stale_high_cost_state_count=0`；
- 至少出现一次恢复事件，或先执行上述构造用例确认恢复链路；
- 高成本方向恢复后，CSV中的 `temporary_high_cost_active` 立即变为 `False`；
- 基础图边数在运行前后不因Improved密度状态变化；
- 静态 `weight` 不被覆盖；
- AA结果与本阶段前一致；
- 闸机服务、容量、人数守恒及路径验证继续通过。
