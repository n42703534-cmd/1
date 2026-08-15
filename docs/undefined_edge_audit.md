# Undefined edge audit

审计日期：2026-07-21

结论：下列 35 条旧配置边引用 7 个当前未定义的 L2 扶梯节点。当前代码、节点配置和 `calc_platform_dists.py` 均未提供这些设施，但这不足以证明现实车站中一定不存在这些扶梯，因此全部标为 `requires_manual_confirmation`，未自动恢复、也未创建虚构节点。构图器继续对任何未定义端点抛出 `ValueError`。

| 原配置组 | 起点 | 终点 | 缺失节点 | 可能所属线路 | 当前处理状态 |
|---|---|---|---|---|---|
| L2_VERTICAL_TO_GATE | Escalator_L2_up2 | Gate_L2_N_West | Escalator_L2_up2 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_up2 | Gate_L2_N_East | Escalator_L2_up2 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_up2 | Gate_L2_S_West | Escalator_L2_up2 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_up2 | Gate_L2_S_East | Escalator_L2_up2 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_down2 | Gate_L2_N_West | Escalator_L2_down2 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_down2 | Gate_L2_N_East | Escalator_L2_down2 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_down2 | Gate_L2_S_West | Escalator_L2_down2 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_down2 | Gate_L2_S_East | Escalator_L2_down2 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_up3 | Gate_L2_N_West | Escalator_L2_up3 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_up3 | Gate_L2_N_East | Escalator_L2_up3 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_up3 | Gate_L2_S_West | Escalator_L2_up3 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_up3 | Gate_L2_S_East | Escalator_L2_up3 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_down3 | Gate_L2_N_West | Escalator_L2_down3 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_down3 | Gate_L2_N_East | Escalator_L2_down3 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_down3 | Gate_L2_S_West | Escalator_L2_down3 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_down3 | Gate_L2_S_East | Escalator_L2_down3 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_up4 | Gate_L2_N_West | Escalator_L2_up4 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_up4 | Gate_L2_N_East | Escalator_L2_up4 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_up4 | Gate_L2_S_West | Escalator_L2_up4 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_up4 | Gate_L2_S_East | Escalator_L2_up4 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_up5 | Gate_L2_N_West | Escalator_L2_up5 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_up5 | Gate_L2_N_East | Escalator_L2_up5 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_up5 | Gate_L2_S_West | Escalator_L2_up5 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_up5 | Gate_L2_S_East | Escalator_L2_up5 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_up6 | Gate_L2_N_West | Escalator_L2_up6 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_up6 | Gate_L2_N_East | Escalator_L2_up6 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_up6 | Gate_L2_S_West | Escalator_L2_up6 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_GATE | Escalator_L2_up6 | Gate_L2_S_East | Escalator_L2_up6 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_VIRTUAL | Escalator_L2_up2 | VN_L2_Corner_1 | Escalator_L2_up2 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_VIRTUAL | Escalator_L2_up3 | VN_L2_Corner_1 | Escalator_L2_up3 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_VIRTUAL | Escalator_L2_down2 | VN_L2_Corner_1 | Escalator_L2_down2 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_VIRTUAL | Escalator_L2_up4 | VN_L2_Corner_1 | Escalator_L2_up4 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_VIRTUAL | Escalator_L2_up5 | VN_L2_Corner_1 | Escalator_L2_up5 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_VIRTUAL | Escalator_L2_down3 | VN_L2_Corner_1 | Escalator_L2_down3 | L2 | requires_manual_confirmation |
| L2_VERTICAL_TO_VIRTUAL | Escalator_L2_up6 | VN_L2_Corner_1 | Escalator_L2_up6 | L2 | requires_manual_confirmation |

