# AA 队列状态定义

真实资源队列是已经选择资源、尚未获得该资源入口容量、物理上仍留在上游节点的整数人数。
逻辑批次保存 `resource_id/source_group/arrival_time/amount/queue_enter_time/current_path`；
同一批不得同时属于两个资源队列。

未来时刻的预测队列由三类确定需求组成：当前真实队列、尚未消费目标资源容量的确定在途到达、
以及本轮此前已完成路径分配的整数批次。事件按时间推进：事件间先按物理服务率扣除服务量，
事件发生时再加入整数到达量。未选路的上游需求、EMA、软比例、浮点预留和任意时间窗口均不计入。

本轮重新评估某个已排队批次前，先从旧逻辑队列移除该批；选路后立即加入新资源队尾。
这保证后续批次看到守恒的队列状态，避免使用旧队列同时把同一批计入新路线。

共同统计口径把静止人秒互斥划分为资源排队、未分配等待和空间阻塞；另报告在途人秒和
总系统人秒。Improved 与 AA 共用该统计代码。

## 2026-07-27 更新：闸机回归此统一定义

早期 Step 6B 曾让闸机的路由 Q 改用「闸机节点存量 + 上游接收空间被拒」的 backlog
（`gate_service_backlog_state`）。经核查，该口径统计的是「已通过闸机、卡在闸后」的人，
而非本文件定义的「被闸机通行能力 μ 挡在上游、正在排队等待通过」的人；且默认 exempt
模式下上游项恒 0，Q 退化为闸机节点存量，实测严重低估真实排队
（例：Gate_L7_West_Vert 路由口径下 node people 约 60，而 `_resource_queues` 峰值 1789）。

现已撤销该特例：闸机与其它资源一样，路由 Q 一律取
`_resource_queues[("facility", gate)]`（再叠加本轮 `_aa_round_queue_adjustment`），
即「已选择该闸机、被 μ 挡下、沿楼扶梯/通道向上游延伸的整条排队」。
`current_resource_queue` 已抽出 `physical_resource_queue` 统一处理，闸机不再有特例分支。

配套字段分离：
- `gate_node_occupancy`（闸机节点存量）：仅用于空间/密度/诊断，不进 Q/μ。
- `gate_spillback_queue`（legacy 空间回压）：单列，默认 exempt 下恒 0，不混入主 Q。

Improved+Q 与 AA 共用同一 `physical_resource_queue` 口径，保证路由决策与
`bottleneck_resources` 评价指标（本就用 `_resource_queues` 统计 `peak_queue`）一致。
