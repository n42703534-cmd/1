# 多线地铁换乘与地铁站疏散相关 SCI/SCIE 文献清单

检索日期：2026-08-06  
用途：为论文题目、引言、相关工作和方法参数论证准备英文 SCI/SCIE 文献池。

## 使用边界

1. 这里的“SCI/SCIE”按期刊层面初筛，不等同于已经逐篇在学校 Web of Science 后台核验。定稿前仍需用 WoS 核对收录类型、期刊分区和文献类型。
2. “直接相关”指论文对象明确是 metro/subway transfer station、interchange station、multi-line transfer station、transfer passage 或 transfer passenger flow。
3. “方法补充”指论文不一定研究多线换乘站，但其地铁站疏散、路径优化、队列容量或仿真方法可支撑本文。

## A. 直接相关：多线/换乘站/换乘客流

| 优先级 | 文献 | 期刊与年份 | DOI | 与本文关系 |
| --- | --- | --- | --- | --- |
| 必读 | Wang K. et al. Emergency Evacuation Paths for Three-line Transfer Subway Station by AnyLogic Simulation: A Case Study | IET Intelligent Transport Systems, 2025 | 10.1049/itr2.70075 | 直接研究三线换乘地铁站应急疏散路径，题名和问题定位都值得参考。 |
| 必读 | Tian Y. et al. Simulation-based optimization analysis of passenger flow organization in metro interchange stations using AnyLogic | Scientific Reports, 2026 | 10.1038/s41598-026-41719-5 | 直接研究大型地铁换乘站客流组织、瓶颈识别和优化，和我们的“换乘站 + 仿真 + 组织优化”很接近。 |
| 必读 | Cui D. et al. Prediction and warning method for large passenger flow in metro transfer stations based on spatial and temporal characteristics of personnel trajectories | Expert Systems with Applications, 2026 | 10.1016/j.eswa.2025.129193 | 直接研究换乘站大客流预测和预警，可支撑高负荷换乘站风险背景。 |
| 必读 | Zhu K. et al. Evaluating the impact of transfer passage on emergency evacuation safety in transit hub | Accident Analysis and Prevention, 2026 | 10.1016/j.aap.2025.108281 | 直接研究地铁换乘站中换乘通道启用/控制对疏散安全的影响，可支撑“换乘通道与瓶颈分流”讨论。 |
| 必读 | Luo T. et al. Assessing metro station facility network resilience to cascading failures using a coupled map lattice approach | Physica A, 2026 | 10.1016/j.physa.2026.131368 | 以北京西直门三线换乘枢纽为例，将站内设施映射为有向分层网络，和我们“设施网络/瓶颈传播”相关。 |
| 重点 | Zhou W., Wang W., Zhao D. Passenger Flow Forecasting in Metro Transfer Station Based on the Combination of Singular Spectrum Analysis and AdaBoost-Weighted Extreme Learning Machine | Sensors, 2020 | 10.3390/s20123555 | 直接研究换乘站客流预测，可用于说明换乘站大客流具有时间序列预测需求。 |
| 重点 | Pan H.-C. et al. Optimal Train Skip-Stop Operation at Urban Rail Transit Transfer Stations for Nonrecurrent Extreme Passenger Flow Mitigation | Journal of Transportation Engineering, Part A: Systems, 2020 | 10.1061/JTEPBS.0000355 | 研究多线协调跳停以缓解换乘站非常态极端客流，偏运营控制，但与多线换乘风险治理相关。 |
| 可读 | Xu L. et al. Subway Multi-Station Coordinated Dynamic Control Method Considering Transfer Inbound Passenger Flow | Sustainability, 2024 | 10.3390/su162411292 | 考虑换乘进站客流的多站协同控制，偏运营限流；SCI/SCIE 状态需 WoS 再核。 |
| 可读 | Kim C. et al. What Makes Urban Transportation Efficient? Evidence from Subway Transfer Stations in Korea | Sustainability, 2017 | 10.3390/su9112054 | 从 DEA 角度评价首尔地铁换乘站效率，适合用于换乘效率背景，不适合直接支撑疏散算法。 |

## B. 相关但需核 SCI 状态或不宜作为主证据

| 文献 | 期刊与年份 | DOI | 备注 |
| --- | --- | --- | --- |
| Edrisi A. et al. Simulating metro station evacuation using three agent-based exit choice models | Case Studies on Transport Policy, 2021 | 10.1016/j.cstp.2021.06.011 | 案例为德黑兰两线换乘站，内容很贴题；但期刊 SCI/ESCI 信息存在不同来源说法，定稿前必须 WoS 复核。 |
| Zhang J. et al. Dynamic flow analysis and crowd management for transfer stations: a case study of Suzhou Metro | Public Transport, 2024 | 10.1007/s12469-024-00357-8 | 内容直接研究苏州换乘站客流组织，但期刊 SCI 状态不确定，暂列候补。 |
| Lei B. et al. Research on passenger flow control at metro transfer stations based on real-time flow calculation of streamlines | Railway Sciences, 2024 | 10.1108/RS-08-2024-0033 | 内容贴近换乘站流线和控制，但期刊不宜先按 SCI 主文献使用。 |
| Li C. Research on the Three-line Transfer Scheme at Fangzhicheng Station of Xi'an Metro | Urban Mass Transit, 2021 | 10.16037/j.1007-869x.2021.10.008 | 中文工程案例，适合理解三线换乘布局，不是 SCI。 |

## C. 方法补充：地铁站疏散、路径优化、容量与仿真

| 优先级 | 文献 | 期刊与年份 | DOI | 可用于本文哪一部分 |
| --- | --- | --- | --- | --- |
| 必读 | Yang X. et al. Path planning for guided passengers during evacuation in subway station based on multi-objective optimization | Applied Mathematical Modelling, 2022 | 10.1016/j.apm.2022.07.024 | 路径引导、多目标优化、避免瓶颈提前到达；可支撑方法对比和题名结构。 |
| 必读 | Zhang L. et al. Simulation-based route planning for pedestrian evacuation in metro stations: A case study | Automation in Construction, 2016 | 10.1016/j.autcon.2016.08.031 | 地铁站疏散路线规划经典仿真论文，可支撑“仿真 + 路径规划”研究框架。 |
| 必读 | Guo K. et al. Simulation-based multi-objective optimization towards proactive evacuation planning at metro stations | Engineering Applications of Artificial Intelligence, 2023 | 10.1016/j.engappai.2023.105858 | BIM/AnyLogic/机器学习结合的主动疏散优化，适合写相关工作。 |
| 必读 | Tang Y. et al. BIM-based safety design for emergency evacuation of metro stations | Automation in Construction, 2021 | 10.1016/j.autcon.2020.103511 | 支撑地铁站应急疏散安全设计和 BIM/仿真方法。 |
| 重点 | Shi C. et al. Modeling and safety strategy of passenger evacuation in a metro station in China | Safety Science, 2012 | 10.1016/j.ssci.2010.07.017 | 地铁站疏散策略、楼扶梯/闸机等设施通行能力与工程计算。 |
| 重点 | Jiang C. S. et al. Crowding in platform staircases of a subway station in China during rush hours | Safety Science, 2009 | 10.1016/j.ssci.2008.10.003 | 楼梯瓶颈、实测校准、拥挤通行能力；可支撑设施瓶颈讨论。 |
| 重点 | Lei W. et al. Simulation of pedestrian crowds' evacuation in a huge transit terminal subway station | Physica A, 2012 | 10.1016/j.physa.2012.06.033 | 大型地铁枢纽疏散仿真，讨论密度、出口宽度、闸机对疏散时间的影响。 |
| 重点 | Xu X.-Y. et al. Analysis of subway station capacity with the use of queueing theory | Transportation Research Part C, 2014 | 10.1016/j.trc.2013.10.010 | 队列网络、站点服务容量、关键节点敏感性；和本文“设施服务队列”高度相关。 |
| 重点 | Xu X.-Y. et al. Capacity-oriented passenger flow control under uncertain demand: Algorithm development and real-world case study | Transportation Research Part E, 2016 | 10.1016/j.tre.2016.01.004 | 站点服务容量、限流、仿真算法，可支撑高负荷控制场景。 |
| 可读 | Hu M. A high-fidelity three-dimensional simulation method for evaluating passenger flow organization and facility layout at metro stations | Simulation, 2017 | 10.1177/0037549717715107 | AnyLogic + 3D/VR 评价地铁站客流组织与设施布局。 |
| 可读 | Chen X. et al. A multiagent-based model for pedestrian simulation in subway stations | Simulation Modelling Practice and Theory, 2017 | 10.1016/j.simpat.2016.12.001 | 多智能体地铁站行人仿真模型，可用于说明仿真建模路线。 |
| 可读 | Wu P. et al. Evacuation optimization of a typical multi-exit subway station: Overall partition and local railing | Simulation Modelling Practice and Theory, 2022 | 10.1016/j.simpat.2021.102425 | 多出口地铁站疏散优化，适合补充“分区+局部设施调整”类方法。 |

## 建议阅读顺序

1. 先读 A 组前 6 篇，确定“多线/换乘站”论文的题名、问题定位和常用指标。
2. 再读 C 组前 5 篇，补足疏散路径优化和仿真方法的相关工作。
3. 最后读队列容量类文献：Xu et al. 2014、Xu et al. 2016、Jiang et al. 2009。这三篇对我们“设施服务队列”和“容量不是纯几何值”的写法最有用。

## 对当前论文题目的启示

SCI/SCIE 相关论文的题名一般把场景和任务放在前面，例如 “metro interchange stations”“three-line transfer subway station”“metro transfer stations”“evacuation path optimization”。算法、软件或模型通常放在后半句，如 “using AnyLogic”“based on multi-objective optimization”“using a coupled map lattice approach”。因此，当前题目不宜写成“基于 AA* 的……”，更适合写成：

考虑设施服务队列的多线地铁换乘站应急疏散仿真与路径优化
