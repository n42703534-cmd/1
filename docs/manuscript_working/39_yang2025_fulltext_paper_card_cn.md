# Yang et al. (2025) 全文 Paper Card

> Source coverage: Full paper
> Extraction confidence: High
> Locator mode: page-grounded
> Primary analytical lens: Methods / algorithm / system paper
> Secondary analytical lens: Resource and simulation evidence chain
> Context verification: Paper-only
> Card completeness: Complete relative to supplied source

## 01 文献身份

标题：*Optimization of passenger evacuation path in flood scenarios considering companion behaviors*  
作者：Xiaoxia Yang, Jiahui Wan, Haojie Zhu, Chuan-Zhi (Thomas) Xie, Botao Zhang  
期刊：*Simulation Modelling Practice and Theory* 145 (2025) 103212  
DOI：10.1016/j.simpat.2025.103212  
论文类型：方法与案例仿真研究  
全文来源：用户提供的本地 PDF，24 页，已逐页提取并渲染核读  
本卡用途：校准龙阳路论文的完整实验流程、Pathfinder 角色、图表证据链和结果写法；不移植洪水/结伴指标。

## 02 一句话概括

该文在地铁站洪水场景中把水动力、结伴行为、道路中断、疏散时间与拥堵纳入路径优化模型，以 ETACO 求解路径，再在 Pathfinder 中执行和评价优化方案。[Paper: PDF pp. 3–10, 18–23]

## 03 研究问题与研究缺口

作者指出，既有疏散路径研究通常把乘客视为相互独立的个体，而灾害中的同行群体会占用更大横向空间、协调移动并改变速度；同时，洪水和路径中断改变可行网络。因此研究问题是：如何在洪水条件下联合考虑结伴比例、疏散时间、风险、拥堵和道路中断，生成可执行的路径方案，并评价优化前后的疏散安全。[Paper: PDF pp. 1–4]

对龙阳路稿的边界：该缺口属于“洪水—结伴—中断”的前提，不能改写为“到达时刻队列”缺口；龙阳路稿只能借鉴其从问题到执行评价的结构。

## 04 核心贡献

1. 构建同时考虑结伴程度、疏散时间、洪水风险、拥堵和中断路段的路径优化模型。[Paper: PDF p. 3]
2. 设计 ETACO 求解策略并与传统 ACO 比较收敛迭代数和目标值。[Paper: PDF pp. 7–10, 18–19]
3. 用 Pathfinder Steering 执行路径策略，并以个体/平均疏散时间、风险和平均拥堵时间构成评价体系。[Paper: PDF pp. 6, 19–22]

## 05 方法结构

完整流程由 Fig.1 概括：Fluent 生成水深与流速；站体转为节点—路段网络；模型联合洪水、结伴、拥堵和道路中断；ETACO 求解路径；Pathfinder 执行；相对熵权法形成安全等级评价。（p.3）

方法细分为：路段疏散时间计算（pp.4–5）、风险计算（p.5）、拥堵计算（pp.5–6）、多目标路径模型（p.6）、Pathfinder 疏散效果评价（p.6）、ETACO 过程（pp.7–10）。

## 06 数据、案例与软件

案例为一座实际地铁站，论文给出 Pathfinder 的站体仿真图（Fig.4）和 Fluent/Pathfinder 参数表（Table 1）。（pp.9–11）

Fluent 与 Pathfinder 独立运行并通过数据衔接；Pathfinder 使用 Steering 模式。文中明确以 Pathfinder 模拟指定策略下乘客的具体运动行为，再计算疏散效果，而不是让 Pathfinder 替代其 ETACO 优化模型。（pp.3, 6）

## 07 变量、目标与指标

优化目标包括疏散时间、风险和拥堵，并考虑道路中断及结伴比例。（pp.4–6）评价指标为最终个体/总疏散时间 $T_s$、平均个体疏散时间 $T_{ae}$、最大不稳定风险 $R_h$ 和平均个体拥堵持续时间 $T_{ac}$。（p.6）

对龙阳路稿的边界：这些指标来自洪水安全评价体系。龙阳路研究可使用完成时间和拥堵暴露，但不得复制 $R_h$、SIL 或相对熵权重，因为我们的情景无洪水且没有相同评价前提。

## 08 算法与比较协议

ETACO 由文中给出的自适应参数和策略构成，算法流程见 Fig.3。（pp.7–10）求解层的比较对象为传统 ACO，使用收敛迭代数 CN 与最优值 OV，结果见 Table 4。（pp.18–19）

执行评价层另比较 natural evacuation、ACO 路径和 ETACO 路径。p.19 将 natural evacuation 描述为 Pathfinder Steering 下遵循邻近原则的自然疏散；论文没有使用“PF-LQ”这一名称。

## 09 关键公式与实验流程

原文核心公式族包括 Equation 1–3（个体与结伴速度及水动力影响）、Equation 4–6（滑移/倾覆与不稳定风险）、Equation 7–12（拥堵、容量、路径目标和归一化）、Equation 13（Pathfinder Steering 的速度—位置更新）、Equation 14（SIL 评价）、Equation 15–29（ETACO 更新与自适应策略）、Equation 30–31（全局网络效率和路段效率）。本卡不逐式移植，因为龙阳路稿不采用这些公式；该清单只用于确认原文方法闭环。[Paper: PDF pp. 4–11, Equation 1–31]

公式库存：Equation 1, Equation 2, Equation 3, Equation 4, Equation 5, Equation 6, Equation 7, Equation 8, Equation 9, Equation 10, Equation 11, Equation 12, Equation 13, Equation 14, Equation 15, Equation 16, Equation 17, Equation 18, Equation 19, Equation 20, Equation 21, Equation 22, Equation 23, Equation 24, Equation 25, Equation 26, Equation 27, Equation 28, Equation 29, Equation 30, Equation 31。

实验流程如下：

1. 基于网络效率选择关键中断路段。[Paper: PDF pp. 10–11, Figure 5]
2. 模拟不同洪水入侵速度下楼梯和闸机水深/流速（Fig.6; pp.11–12）。
3. 分析目标权重和子代价范围（Figs.7–9; pp.12–14）。
4. 改变乘客数量与结伴比例，分析完成时间和速度（Figs.10–12; pp.14–16）。
5. 改变中断路段数量，分析 LOS、完成时间分布和拥堵持续时间（Figs.13–16; pp.16–18）。
6. 比较 ACO/ETACO 求解性能（Tables 3–4; pp.18–19）。
7. 在 Pathfinder 中比较自然疏散、ACO 与 ETACO 的最大密度空间分布和节点流量（Fig.17, Table 5; pp.19–20）。
8. 结合多种条件做安全等级和优化前后对照（Table 6, Figs.18–21; pp.20–22）。

## 10 主要结果

作者报告：结伴比例提高会延长疏散时间并降低平均速度；ETACO 相比传统 ACO 平均收敛改进率为 23%，平均最优目标改进率为 16%；中断路段增多会加重疏散困难；相对 natural evacuation，ETACO 路径方案降低疏散时间和最大路段风险，并提高综合安全水平。（pp.14–23）

这些结论只在作者设定的洪水、结伴和中断场景下成立；不能作为龙阳路 AA* 的结果证据。

## 11 图表证据清单

- Fig.1：完整技术路线。（p.3）
- Fig.2：自适应参数随迭代变化。（p.8）
- Fig.3：ETACO 流程。（p.10）
- Fig.4：Pathfinder 站体仿真。（p.10）
- Fig.5：路段对全局网络效率的影响。（p.11）
- Fig.6：不同入侵速度下水深/流速时间变化。（p.12）
- Figs.7–9：权重、目标和子代价范围。（pp.12–14）
- Figs.10–12：乘客量与结伴比例对疏散时间/速度的影响。（pp.14–16）
- Figs.13–16：路径中断情景、LOS 热图、完成时间分布和拥堵时间。（pp.16–18）
- Fig.17：自然疏散与路径优化的最大密度热图及节点流量。（p.19）
- Figs.18–21：指标等级、权重、优化前后指标和 SIL。（pp.20–22）
- Table 1：Fluent/Pathfinder 参数。（p.11）
- Table 2：LOS 等级阈值。（p.16）
- Table 3：ACO 参数。（p.18）
- Table 4：ACO/ETACO 求解性能。（p.19）
- Table 5：节点交通量。（p.19）
- Table 6：安全评价的实验条件。（p.20）

## 12 图表叙事特点

论文不是用一张汇总柱图代替实验，而是先给对象和算法，再用时间变化、空间热图、分布图和节点流量解释机制，最后汇总评价。这种“对象—过程—空间—分布—指标”的顺序可用于龙阳路稿。其不足是部分结果图的信息密度较高，龙阳路稿应进一步统一配色、坐标尺度和图内标注。

## 13 Pathfinder 证据角色

已确认事实：Pathfinder 是运动执行和疏散效果评价平台；自然疏散、ACO 路径与 ETACO 路径在其中比较。（pp.6, 19–22）  
已确认事实：论文未出现 “PF-LQ”。  
合理迁移：龙阳路稿可把 Pathfinder 定义为跨模型微观复现平台。  
不可迁移：不能仅因 Yang 等使用了 natural evacuation，就把龙阳路 Goto Any Exit 声称为同一个严格控制组；两者的行为配置必须以各自模型文件为准。

## 14 可迁移到龙阳路论文的写作做法

1. 方法段先以一张完整流程图连接数据、优化、执行和评价。
2. 案例段同时展示真实站体/几何来源和模型化对象。
3. 算法图只解释真正新增的机制，不用 RQ 海报替代方法。
4. 结果段必须出现过程证据和空间/设施机制证据，不能只给站级条形图。
5. 软件验证应完整写明输入路径、行为执行、输出指标及优化前后比较。

## 15 不可迁移项

洪水水动力公式、结伴比例、道路中断集合、LOS 阈值、ACO/ETACO 参数、相对熵权重和 SIL 评价均依赖该文自己的研究前提。龙阳路研究无火灾、设施均可用，不能引用这些部分为本项目参数或评价体系。

## 16 Agent-derived research candidates

创新状态：unverified（本节是面向龙阳路项目的研究迁移建议，不声称已完成先验技术检索）。

核心假设：如果候选路径按预计到达时刻而非决策时刻评估共享设施队列，则可以减少尾部清空时间和等待暴露；其增益会随需求强度变化。

初步方法：在相同物理执行层下比较 Improved A* 和 AA*，逐项关闭队列等待、到达时刻预测、空间接纳、多标签与密度暴露模块，并把固定路径映射进 Pathfinder。

Validation / 验证：使用低/高负荷、站级完成分布、线路清空、设施与出口重分配、消融和 Pathfinder 跨模型复现构成证据链。

Possible failure modes / 可能失败方式：到达预测误差累积、预分配路径在微观环境中失配、计算时间过高，或某些附加模块在特定负荷下没有独立增益。

对龙阳路修订的直接决策：

1. 删除 “PF-LQ”，改为 Pathfinder Goto Any Exit；Locally Quickest 只用于解释技术手册中的内部机制。
2. Pathfinder 小节改名为“跨模型微观复现”，不称现场外部验证。
3. 主图扩充为站体/需求/方法/站级分布/线路清空/设施与出口重分配/消融/Pathfinder 分布/负荷比较的证据链。
4. AA* 的研究目的写为改善共享瓶颈的等待暴露与尾部清空，并同时报告绕行与计算代价。
5. 消融按模块关闭，结果如实显示资源等待和到达时刻预测是主要机制，空间接纳预测在当前汇总结果中为零增益。
