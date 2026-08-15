# Zotero 相关论文方法章与案例章写法矩阵

## 目的

本文件用于重构本文“模型、求解、案例研究”三部分的写作流程。它不是文献综述，也不是参考文献表，而是从 Zotero 本地 PDF 中抽取同类 SCI 论文的章节组织方式，作为后续正式稿重写的结构依据。

## 已读取的 Zotero 本地论文样本

### Wei et al., 2026, Simulation Modelling Practice and Theory

题名：Dynamic firefighting route planning for efficient evacuation in complex subway stations

章节流程：

| 章节 | 功能 |
|---|---|
| 3 The proposed model | 提出完整模型，而不是只介绍单个算法 |
| 3.1 Robust optimization model for firefighting route | 定义消防路线问题、网络、目标与约束 |
| 3.2 BKA-GRU node time prediction model | 为上层路线优化提供节点通行时间预测 |
| 3.3 Comprehensive evaluation method | 建立最终效果评价指标 |
| 4 Solving method | 将模型转化为可解形式并说明求解算法 |
| 5.1 Node passage time prediction results | 先验证中间预测模块 |
| 5.2 Performance analysis of model solutions | 再分析模型求解方案性能 |
| 5.3 Integration analysis | 最后把消防路线与乘客疏散效果合并评价 |

对本文的启发：

方法章必须先说明“本文提出的 AA 模型是什么”，再说明它由哪些子模型构成。实验章不能一开始就比较总疏散时间，而应先验证 AA 的核心中间模块，即“到达时刻设施负荷预测”是否实际改变路径评价。

### Yang et al., 2022, Applied Mathematical Modelling

题名：Path planning for guided passengers during evacuation in subway station based on multi-objective optimization

章节流程：

| 章节 | 功能 |
|---|---|
| 3 Model | 先建立行人运动模型、成本模型、引导员分配模型和路径规划模型 |
| 3.5 Model solution | 单独说明 NSGA-II 如何求解路径规划模型 |
| 4 Model validation | 先验证模型基础模块，包括社会力模型和最小成本模型 |
| 5 Analysis of simulation results | 最后分析仿真结果和方案效果 |

对本文的启发：

“模型”和“求解”必须分开。第 3 章应讲 AA 的模型构成和路径代价，第 4 章才讲时间依赖 A* 标签、事件登记、共享容量执行。案例研究要先验证模型模块，再看整体效果。

### Xu et al., 2024, Journal of Building Engineering

题名：Optimization of emergency evacuation in complex rail transit station

章节流程：

| 章节 | 功能 |
|---|---|
| 3 Methodology | 说明 BIM、Pathfinder、仿真假设、人员特征和 ASET/RSET 指标 |
| 4 Case study | 先写空间建模、火灾场景、疏散路线和人数设置 |
| 4.5 Simulation results | 再分析 ASET/RSET、障碍物、伤员、关键时间点和闸机流率 |
| 5 Discussion | 讨论疏散引导、移动障碍物、人数变化和措施比较 |

对本文的启发：

案例章不能只写“低负荷、高负荷、敏感性”。应先把案例站、空间建模、场景构造和人数输入交代清楚，再围绕关键设施、关键时间点、出口/闸机/通道负荷来解释结果。

### Feng et al., 2026, Journal of Building Engineering

题名：Fire simulation and evacuation optimization for metro stations with interpretability

章节流程：

| 章节 | 功能 |
|---|---|
| 3 Methodology | 先提出整体混合方法框架 |
| 3.1 Evacuation analysis and objectives | 定义疏散目标和影响因素 |
| 3.2 Evacuation simulation and scenarios design | 设计火灾和疏散仿真场景 |
| 3.3 Prediction and optimization | 建立预测、解释和优化方法 |
| 4 Case study | 写案例背景、场景设计、预测结果、解释性分析和优化结果 |
| 5 Discussion | 讨论烟气影响、算法比较和改进措施 |

对本文的启发：

如果本文保留 Pathfinder 对照和适用边界分析，它们不能作为零散附录，而应放在“综合效果与适用边界”中，回答 AA 在什么换乘客流比例、到达重叠程度和瓶颈强度下有效。

### Liu and Zou, 2024, Journal of Building Engineering

题名：Dynamic evacuation path planning for subway station fire based on IACO

章节流程：

| 章节 | 功能 |
|---|---|
| 2 Fire model | 先建立火灾场景和风险环境 |
| 3 Evacuation model | 再建立疏散路径规划模型 |
| 3.1 Algorithm comparison | 引入对照算法 |
| 3.2 Algorithm model | 说明算法原理和改进 |
| 4 Algorithm simulation experiment | 用算法仿真实验比较路径和场景调整效果 |

对本文的启发：

ImprovedAStar 应在“计算对照方法”中出现，不能被写成现实原方案，也不能抢占 AA 模型的主线。对照的作用是说明 AA 的预测-执行耦合是否有意义。

### Zheng and Mou, 2023, Mathematics

题名：A Dynamic Network Loading Model for Hub Station Pedestrian Flow Collection and Distribution

章节流程：

| 章节 | 功能 |
|---|---|
| 2 Methods | 抽象枢纽站网络并建立乘客流传播模型 |
| 2.2 Network Model | 明确设施节点和网络结构 |
| 2.3 Macro Dynamics Pedestrian Flow Model | 建立宏观动态传播模型 |
| 3 Simulation | 分别分析平峰和高峰客流集散 |
| 4 Optimization | 在仿真结果基础上提出客流控制方法和优化结果 |

对本文的启发：

龙阳路站的“换乘客流”应作为全站多源客流汇聚机制的核心解释变量，而不是单独把“换乘客流疏散”当作研究对象。实验应解释换乘流如何与站台流、列车到达流在共享设施上叠加，并如何影响整体疏散。

## 对本文正式稿的流程重构

### 第 3 章：提出的模型

建议标题：队列感知的多线换乘站疏散路径组织模型

章节功能：介绍 AA 作为本文提出的完整模型，而不是先介绍站内网络、再零散介绍算法。

建议结构：

| 小节 | 应写内容 |
|---|---|
| 3.1 问题描述与模型总体框架 | 说明大型五线换乘站中多源客流在共享设施上汇聚，提出 AA 的路径决策层和设施服务执行层 |
| 3.2 站内疏散网络与共享设施容量模型 | 定义站台、换乘通道、楼扶梯、闸机、出口和共享资源映射 |
| 3.3 多来源批次与到达负荷预测模型 | 定义站台流、列车到达流、换乘流；预测批次到达设施时的队列和等待 |
| 3.4 AA 路径组织模型 | 定义路径代价、时间依赖标签、路径重评估条件 |
| 3.5 疏散效果评价方法 | 定义总体时间、尾部滞留、设施队列、来源组分解、Pathfinder 趋势一致性 |

### 第 4 章：模型求解方法

建议标题：AA 模型求解与共享容量执行

章节功能：说明第 3 章模型如何转化为可执行算法，避免继续介绍模型本身。

建议结构：

| 小节 | 应写内容 |
|---|---|
| 4.1 模型状态与搜索标签转换 | 把批次状态、设施队列、未来到达事件转成时间依赖 A* 标签 |
| 4.2 AA 路径搜索与事件登记 | 说明每个批次搜索、预计到达事件写入、后续批次读取预测状态 |
| 4.3 共享容量执行与客流守恒 | 说明路径只是移动意图，实际通过由统一设施容量和下游接收约束执行 |
| 4.4 计算对照方法 | 说明 ImprovedAStar 只是计算基准，不是官方方案；比较差异限定在路径组织逻辑 |

### 第 5 章：案例研究

建议标题：龙阳路站案例研究

章节功能：按“中间模块验证 -> 方案性能 -> 综合疏散效果”的顺序证明 AA 对整体疏散问题的作用。

建议结构：

| 小节 | 应写内容 |
|---|---|
| 5.1 案例车站与疏散场景 | 介绍龙阳路站五线换乘属性、CAD 建模、低负荷和高负荷场景、客流输入 |
| 5.2 到达负荷预测结果分析 | 先验证 AA 是否预测关键设施队列、是否改变路径排序 |
| 5.3 路径组织方案性能分析 | 比较低负荷和高负荷下 AA 与 ImprovedAStar 的疏散时间、停滞、队列和出口利用 |
| 5.4 换乘客流汇聚机制分析 | 分解换乘流、站台流、列车到达流在共享设施上的叠加关系 |
| 5.5 Pathfinder 对照与适用边界 | 用 Pathfinder 趋势验证和换乘比例/到达重叠/设施容量扰动说明适用范围 |

## 需要避免的错误写法

1. 不把 AA 写成“比 ImprovedAStar 更优的算法实验”，而应写成“用于组织多线换乘站多源客流疏散的队列感知模型”。
2. 不把 ImprovedAStar 写成原有官方疏散方案，只作为计算基准。
3. 不把敏感性分析写成速度-密度参数扰动。本文边界应围绕换乘客流比例、列车到达重叠程度和关键共享设施容量。
4. 不在正式稿中出现 Mode 1、Mode 4，而写成低负荷常规应急场景和高负荷满载列车叠加场景。
5. 不在模型章堆砌参数来源。参数来源应进入参数表或附录，正文只说明模型变量及其物理意义。
