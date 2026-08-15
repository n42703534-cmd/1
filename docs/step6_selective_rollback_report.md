# Step 6 选择性回退报告

时间：2026-07-26  
状态：已只回退 Step 6 的共同物理层；Step 7、Improved 临时高成本和 Step 6B 后续代码保留。

## 当前版本保存

回退前的完整版本已复制到：

`C:\Users\28146\Desktop\network\network\backups\preserve_before_step6_selective_rollback_20260726_102627`

回退前 SHA-256：

- `network.py`: `D0AD5DBE35DA74576A0D3362BF119C4E3F7EEFDE4370E59F2DBF7F4D40220A77`
- `single_path_routing.py`: `838353085E5C5A7CB1B0FCD8CF559D51FE24441E261040BEC733BE502D1FE4FA`
- `algorithm_comparison.py`: `F63C6E771903CEF52B42444114A605A84C7BC9C6FAAB047E759281C9E2DA9AA5`
- `test_routing_regressions.py`: `946E51F351E7F21FB9A45FD098E0D0B5755397F94BE81073680A5F91342391C3`

## Step 5C 基准确认

以下目录是 Step 6 修改前的备份：

`staged_modifications/step6_gate_service_order/backup`

其 SHA-256 与 `staged_modifications/step5c_edge_near_jam_diagnostics/version_snapshot.md`
记录的 Step 5C 验收后 SHA-256 完全一致：

- `network.py`: `34984201885158346762F07A21E0178A5D804D122800A181E111084DA087616C`
- `single_path_routing.py`: `D756109A78A76AA0A6D50D24A5B00865B0AEAC9F1D590BDD12CE71ADDC8660A0`
- `algorithm_comparison.py`: `9925F6A70459AF0D7FD7FB2FC9DDBFB62DFFDE125C34466EDE801A1D956A0D98`

因此本次回退边界不是按时间或注释猜测，而是由 Step 6 修改前后文件差异确定。

## 已回退的 Step 6 物理行为

1. Gate 服务资源重新映射到进入 Gate 的边。
2. `service_capacity_consumed` 在人员进入 Gate 时设为 `True`。
3. 不再为进入 Gate 的在途记录登记未来 Gate 服务请求。
4. Gate 节点重新设为不参与有限空间接收。
5. 因此 Gate 不再按 Step 6 的“进入后排队、离开时服务、满员后上游回溢”流程运行。

这恢复了 Step 5C 的服务顺序：

`上游 -> 进入 Gate 时消耗闸机能力 -> Gate 节点 -> 闸机后通道`

## 明确保留的后续修改

- Step 7 的 Improved Gate 密度统计代码；
- Improved 临时高成本逐步恢复代码；
- Step 6B 的统一积压函数、回调、诊断字段和回归测试代码；
- Step 6/6B 的诊断输出兼容代码。

这些后续代码仍在文件中，但共同物理层已经不再采用 Step 6 的离开 Gate 服务方式。

## 重要限制

当前版本不是“纯 Step 5C 文件快照”。纯 Step 5C 快照不包含 Step 7、临时高成本和 Step 6B。
当前版本是：

`Step 5C 物理层 + 保留的后续算法/诊断代码`

特别是 Step 6B 的统一 Q 和 Improved `Q/μ` 代码仍然存在。由于 Step 5C 下 Gate
服务发生在进入时，这些后续等待诊断与物理服务顺序不再具有 Step 6B 原设计中的同一含义，
后续验收时不能把它们当成已经物理一致。

## 回退后 SHA-256

- `network.py`: `CA3F141E59373ECD252CC83E053F1D356FA76E5D6B01D84FFAF7748E6302B8D0`
- `single_path_routing.py`: `9F9371FACEC0599533628C85504D79D1AC9FCC7A8962DB4BCD5248E7F35F97E5`
- `algorithm_comparison.py`: `F63C6E771903CEF52B42444114A605A84C7BC9C6FAAB047E759281C9E2DA9AA5`
- `test_routing_regressions.py`: `946E51F351E7F21FB9A45FD098E0D0B5755397F94BE81073680A5F91342391C3`

已执行静态 `git diff --check`，未发现空白错误。本次未运行仿真。
