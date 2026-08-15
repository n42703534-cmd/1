# Step 6B 待验收报告

生成时间：2026-07-26  
状态：代码修改完成；按要求未运行单元测试、回归测试或仿真。

> **⚠️ 2026-07-27 修正：本报告第 2 节的 Q 口径已被撤销。**
> 本报告把闸机路由 Q 定义为「Gate 节点未服务 + 上游接收空间被拒」。经复核，该口径统计的
> 是「已通过闸机、卡在闸后」的人（gate 节点存量），而非「被闸机通行能力 μ 挡在上游排队
> 等待通过」的人；且默认 exempt 模式下上游项恒 0，Q 退化为闸机节点存量，实测严重低估真实
> 排队（例：Gate_L7_West_Vert 路由口径 node people ≈ 60，而 `_resource_queues` 峰值 1789）。
> 现已改为：路由 Q = `_resource_queues[("facility", gate)]`（详见
> `aa_queue_state_definition.md` 的 2026-07-27 更新）。第 4 节新增的 Improved Gate Q/μ
> 分量随之改用同一口径。第 2 节的 backlog 定义此后仅作为诊断量
> `gate_service_backlog_people` 保留，不再用于路由成本。

## 1. 修改范围

- `network.py`
  - 新增 `gate_service_backlog_state`，每次调用都从当前 Gate 节点状态和当前直接上游 Gate 空间拒绝记录重建 Q，不保存 Q 的跨步缓存。
  - Gate 节点批次与直接上游阻挡批次按 `batch_id`、`cohort_id` 或 `person_id` 去重。
  - AA 没有批次标识时、Improved 聚合客流没有持久批次标识时，使用物理位置、直接上游和 source group 组成的唯一聚合键；不把在途人员加入 Q。
  - 新增逐 Gate 诊断和 L18/L2 指定 Gate 的逐秒跟踪。
  - Gate 密度继续仅使用 Gate 节点实际人数；上游阻挡人数只进入服务积压 Q。
  - 进入 Gate、离开 Gate 服务扣减、Gate 空间、服务率和回溢分配代码未改。
- `single_path_routing.py`
  - 新增共享 Gate 积压回调。
  - AA 的当前 Gate 队列基值改为统一 Q；AA 自身批次服务时间、预测事件和主动换路规则未改。
- `algorithm_comparison.py`
  - `diagnostics.json` 增加 `gate_backlog_diagnostics`。
  - 新增 `gate_backlog_step_trace.csv`。
- `test_routing_regressions.py`
  - 增加场景 A、B、C 三个待运行回归测试。

## 2. 统一 Q 定义

当前实现：

`Q = Gate 节点尚未服务人数 + 直接上游因 Gate 接收空间不足被拒绝且下一跳仍为该 Gate 的人数`

排除：

- 仅计划以后使用 Gate 的人员；
- `_transit_queue` 中正在前往 Gate 的人员；
- 已离开 Gate 的人员；
- Gate 节点与上游阻挡记录中权威批次标识相同的重复表示。

## 3. 诊断字段

- `gate_node_waiting_people`
- `gate_upstream_blocked_people`
- `gate_service_backlog_people`
- `improved_queue_q_used`
- `aa_queue_q_used`
- `gate_backlog_overlap_people`
- `gate_backlog_mismatch_count`

逐秒文件还记录：

- 服务率；
- `Q/μ`；
- 当步选择进入 Gate 的人数；
- 当步离开 Gate、实际消耗服务能力的人数。

## 4. 必须明确的现有代码差异

修改前代码中的 AA 已使用 `Q/μ` 等待成本，但修改前 Improved 的 `paper_edge_cost` 明确不包含服务率等待项。为实现 Step 6B“Improved 实际读取统一 Q”的目标，本阶段在 Improved 的 Gate 入边当前步 `sim_weight` 中增加了 `Q/μ`。

因此，对当前代码基线而言，这不是单纯替换 Improved 原有 Q 的来源，而是增加了一个此前不存在的 Gate 等待成本分量。该变化可能改变 Improved 路径和结果，验收时必须单独判断是否符合你的算法定义；不能把结果变化解释为纯诊断变化。

## 5. 待运行验收

本次没有执行以下项目：

- Python 编译/import；
- 场景 A/B/C；
- Mode 4；
- 人数守恒、路径循环/反向/断裂检查。

建议先只运行三个新增回归测试，再运行默认参数 Mode 4 双算法。重点检查：

1. A 场景 Q=5；
2. B 场景位置迁移前后均为 5；
3. C 场景通过 Gate 后 Q 立即为 0；
4. `gate_backlog_overlap_people=0`；
5. `gate_backlog_mismatch_count=0`；
6. AA 与 Improved 同一时刻、同一 Gate 的 Q 一致；
7. Gate 服务能力没有重复扣减或超额服务。

## 6. 备份与 SHA-256

备份目录：

`C:\Users\28146\Desktop\network\network\backups\step6b_gate_backlog_20260726_100644`

修改前：

- `network.py`: `847C4CFC1A132EBA732707F1EBF6D1165235BEF3530737B89B476BE848C1B734`
- `single_path_routing.py`: `78AEEB96931DB988CBC757549F4C9566F49BCDFFB0F310308F1090E8A2DD5C0A`
- `algorithm_comparison.py`: `6081588FBBBB24598A871B4E62E48DA35363B84227442C5C7DF34FA6920D4B94`

修改后：

- `network.py`: `D0AD5DBE35DA74576A0D3362BF119C4E3F7EEFDE4370E59F2DBF7F4D40220A77`
- `single_path_routing.py`: `838353085E5C5A7CB1B0FCD8CF559D51FE24441E261040BEC733BE502D1FE4FA`
- `algorithm_comparison.py`: `F63C6E771903CEF52B42444114A605A84C7BC9C6FAAB047E759281C9E2DA9AA5`
- `test_routing_regressions.py`: `946E51F351E7F21FB9A45FD098E0D0B5755397F94BE81073680A5F91342391C3`

静态 `git diff --check` 未报告空白错误。未开始任何后续阶段。
