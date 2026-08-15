# Zotero 相关论文写法抽取记录

本记录用于支撑方法章与案例研究章的重写，不作为论文正文。Zotero 本地 API 当前返回 403，因此本轮采用只读方式读取本地 Zotero 数据库与 PDF 附件，没有修改 Zotero 条目。

## 已读取的相关论文样本

| Zotero key | 论文 | 期刊 | DOI | 主要可借鉴写法 |
|---|---|---|---|---|
| R9KTTSQW | Wei et al. (2026), Dynamic firefighting route planning for efficient evacuation in complex subway stations | Simulation Modelling Practice and Theory | 10.1016/j.simpat.2025.103223 | “提出模型-求解方法-案例研究”分章；案例中先分析节点通行时间预测，再分析路线方案性能，最后综合消防路线与乘客疏散效果。 |
| XPJBUP4M | Feng et al. (2026), Fire simulation and evacuation optimization for metro stations with interpretability | Journal of Building Engineering | 10.1016/j.jobe.2025.114798 | 方法章先做疏散目标与影响因素分析，再构造仿真场景和多目标预测优化；案例章先写背景和场景，再写预测结果、解释性和优化结果。 |
| GMHF8A6K | Xu et al. (2024), Optimization of emergency evacuation in complex rail transit station | Journal of Building Engineering | 10.1016/j.jobe.2024.110321 | 方法章介绍 BIM、Pathfinder、仿真假设、人员特征和 ASET/RSET；案例章按空间建模、火灾场景、疏散路线、人数设定和仿真结果展开。 |
| ZXT3LHCP | Guo and Zhang (2022), Simulation-based passenger evacuation optimization in metro stations considering multi-objectives | Automation in Construction | 10.1016/j.autcon.2021.104010 | 先分析地铁站疏散目标，再构建仿真和代理模型，最后进行多目标优化；实验章按背景、建模、预测、优化顺序组织。 |
| NVCRI2G2 | Guo and Zhang (2022), Adaptive multi-objective optimization for emergency evacuation at metro stations | Reliability Engineering & System Safety | 10.1016/j.ress.2021.108210 | 强调自适应规则和场景化优化，案例章先复现仿真/代理模型，再评价自适应优化。 |
| 6NC6D3ZJ | Yang et al. (2022), Path planning for guided passengers during evacuation in subway station | Applied Mathematical Modelling | 10.1016/j.apm.2022.07.024 | 模型章按行人运动模型、最小成本模型、引导员配置、路径规划和模型求解展开；实验先做模型验证，再做仿真结果分析。 |
| KKYAMMMM | Wen et al. (2024), A passenger flow spatial-temporal distribution model for a passenger transit hub considering node queuing | Transportation Research Part C | 10.1016/j.trc.2024.104640 | 枢纽网络构建后，先定义 link/node travel time，再定义动态路径选择和动态客流加载；节点排队是方法主体。 |
| RT65SAGN | Zheng and Mou (2023), A Dynamic Network Loading Model for Hub Station Pedestrian Flow Collection and Distribution | Mathematics | 10.3390/math11173654 | 把真实枢纽抽象为设施节点网络，并同步更新节点客流信息；仿真章区分低峰、高峰和优化控制。 |
| JNCRY9Q9 | Shen et al. (2024), Model cascading overload failure and dynamic vulnerability analysis of facility network of metro station | Reliability Engineering & System Safety | 10.1016/j.ress.2023.109711 | 先建立车站设施网络、节点负荷与容量，再定义脆弱性指标和级联过载过程，案例解释关键节点和流量重分配。 |
| RSGBKACX | Yang et al. (2025), Two-stage stochastic optimization of passenger evacuation routes in metro stations | Reliability Engineering & System Safety | 10.1016/j.ress.2025.111047 | 方法章先给行人运动与最小成本模型，再给两阶段随机优化；案例章包含场景、人数、事故位置、行为影响、模型对照和敏感性。 |
| UCVRBPEQ | Yang et al. (2025), Partition independent control and collaborative optimization of high-density crowd in subway stations | Chaos, Solitons & Fractals | 10.1016/j.chaos.2025.117108 | 先给微观仿真框架、宏观演化识别、分区控制和评价方法；案例章先分析控制对客流动态影响，再验证识别模型和控制效果。 |
| RQGYAQX6 | Li et al. (2025), Experimental study in an actual full-size subway station | Tunnelling and Underground Space Technology | 10.1016/j.tust.2025.106962 | 实验论文按实验准备、实验场景、实验流程、数据提取和观测指标展开，再分析轨迹、行为选择、速度和疏散时间。 |
| 75BAPU3J | Wang et al. (2025), Smoke flow and evacuation safety in an underground rail transit transfer station | Buildings | 10.3390/buildings15173008 | 转换站火灾论文按 PyroSim、Pathfinder、火灾模型和人员疏散模型建模；结果按烟气、温度、可见度、ASET 和人员疏散展开。 |
| KJBRNNEI | Yang et al. (2024), An efficient evacuation path optimization for passengers in subway stations under floods | Tunnelling and Underground Space Technology | 10.1016/j.tust.2023.105473 | 模型章包含灾害模型、行人运动模型和两阶段路径优化；案例章先做节点通行时间预测，再做路径计算和优化效果评价。 |
| TDMMNNHM | Li et al. (2026), An evacuation model considering multi-attribute group decision-making behavior | Reliability Engineering & System Safety | 10.1016/j.ress.2025.111976 | 模型章非常细：假设、出口决策、信息共享、主观评价、转移概率和运动规则；实验章先验证模型，再做参数/机制分析。 |

## 对本文的结构修正结论

1. 方法章不应以“算法比对”开头，而应以大型多线换乘站的疏散对象系统开头：多来源客流、换乘关系、共享设施、设施服务和尾部清空。
2. AA 应写成路径组织模型，而不是单纯算法名称。其核心模块是到达时刻队列预测、未来事件登记、时间依赖搜索和共享容量动态加载。
3. 实验章应先验证中间机制，再比较最终结果。对应到本文，先写“到达负荷与队列预测结果验证”，再写“整体疏散效率与瓶颈改善分析”。
4. 换乘客流应作为解释整体疏散效果的机制变量，而不是把论文目标缩窄为“换乘客流疏散”。
5. 敏感性分析应围绕换乘客流比例、列车到达重叠程度和关键共享设施服务能力展开；速度-密度参数只属于基础运动模型取值，不应作为本文主要适用边界。
