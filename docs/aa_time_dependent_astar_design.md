# Adaptive Queue-Aware A*：时间依赖搜索设计

正式 AA 为 `AdaptiveQueueAwareAStar`，搜索入口是
`single_path_routing.time_dependent_astar()`。`MesoscopicPhysicalTimeAStar` 和
`MesoscopicCurrentQueueAwareAStar` 仅保留为历史实验方法，不再是默认入口。

每个自然到达批次独立执行完整图 A*。标签包含节点、累计预计时间、预计到达时刻和前驱。
扩展 `u -> v` 时：

`cost = physical_travel_time + predicted_resource_wait + predicted_spatial_wait`

后续资源 ETA 包含此前全部行走和等待。启发值仅缓存静态自由流时间下界；不缓存动态完整路径，
也不使用固定 K 条候选路径。路径建议仍由共同整数化、共享资源容量和下游接收规则执行。

同一轮按 `arrival_time, source_group, node, batch_id` 确定性排序。前一批路径确定后，
其整数人数立即写入本轮资源/空间到达事件，后一批的 A* 因而看到更新后的预测状态。

性能缓存仅包括静态启发下界、资源映射及按资源/节点建立的到达事件索引；这些缓存不包含路径，
不会令同节点批次复用第一条动态路径。
