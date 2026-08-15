# 1 引言

## 1.1 研究背景与意义

截至2024年底，中国大陆共有61个城市开通城市轨道交通线路，运营总里程突破11000 km，其中地铁线路占比超过75%[1]。庞大的线网规模在为市民出行提供便利的同时，也使地铁车站——尤其是多线换乘枢纽——固有的空间封闭、多层立体布局、换乘通道纵横交错和闸机通行能力不对称等特征，在火灾、洪水或人员恐慌等突发事件中转变为人群疏散的严峻风险。近年来的事故记录表明这一风险的现实性：2015年4月深圳地铁黄贝岭站恐慌踩踏致12人受伤；2017年9月伦敦Parsons Green站爆炸致至少29人受伤；2021年7月郑州地铁5号线洪水倒灌致14人遇难。风暴和洪水已被统计为地铁事故中第三高发的灾害类型，约占事故总量的11%[2–4]。这些事件反复表明，在突发事件中正确、高效的疏散路径引导是保障乘客人身安全的关键环节。

行人疏散动力学研究一般被划分为经验实证研究与模型研究两大范畴[5]。模型研究又可细分为规划模型与仿真模型。规划模型利用Dijkstra算法[6]、A*算法及其变体[7–8]和蚁群算法[9]等在给定网络拓扑和乘客分布下生成最优疏散路径集；仿真模型则依托社会力模型[10–11]、元胞自动机模型[12]及商用平台（PathFinder, Anylogic, MassMotion）模拟站内人群的时空演化、识别瓶颈区域并预测疏散时间[13–15]。受安全风险和运营条件的制约，真实地铁车站中大规模高密度的全尺寸疏散实验几乎不可行——所有既有实证方法在地铁站空间的具体性和特殊性方面均存在显著局限[2]——因此仿真模拟目前仍是该领域主流的研究手段。然而，无论规划模型还是仿真模型，其精度均高度依赖模型参数的经验标定，缺乏实测数据支撑的仿真结果可能在疏散时间和瓶颈分布上出现严重偏差[2]。在此背景下，突破单一仿真工具链的闭环验证，将独立的外部仿真基准引入疏散策略的评估体系，是该领域研究亟须进展的方向。

在地铁车站场景中，乘客疏散路径优化涉及三个紧密关联的子问题：设施容量（闸机、楼扶梯）的定量建模，路径规划目标的数学形式化，以及规划的在线执行与验证。在设施容量方面，闸机是连接付费区与非付费区的关键控制节点，其通行效率受闸机数量、单道宽度和客流到达模式的综合影响[16–17]。值得特别注意的是，Li等[2]在贵阳五里冲地铁站的原尺寸实地实验中观察到，乘客在闸机处的通道选择取决于最终出口决策而非通道宽度本身。这一实验发现对路径规划具有重要启示：如果乘客在宏观行为层面已经将其闸机通道选择捆绑到出口决策之上，那么将容量感知从单个设施层提前到出口评估层——即在路径搜索阶段就按出口方向对应的闸机通行能力修正各候选方向的排序——是在行为逻辑上更为合理、在工程效果上更为直接的介入方式。

## 1.2 研究现状与不足

在路径规划层面，现有工作可归纳为两类。第一类为**静态路径优化**：在疏散开始前一次性规划完整路径，典型方法包括以最小化疏散时间为目标的单目标模型[18]，以及综合考虑疏散时间、拥挤度和风险的多目标模型[10,19]，通常通过NSGA-II算法求解Pareto最优解集。第二类为**动态逐跳引导**：不预先固定完整路径，在每个决策步内依据当前节点与下游节点的实时拥堵信息选择下一跳方向[20–21]。与静态优化相比，动态引导对时变拥堵具有更好的实时响应能力，且对因设施失效导致的局部网络变化更具弹性。然而，这两类方法在以下两个方面存在共同的不足。

其一，**出口容量信息在路径决策中是"被动感知"而非"主动嵌入"的**。现有拥挤度度量通常以边或节点上的累计使用人数为代理[22]，不显式区分同一车站内不同闸机组的通行能力差异。在动态引导方法中，容量信息隐含在瓶颈节点的排队等待时间项中，仅在该节点已被大量客流积压后才在代价函数中被显著体现——此时较弱出口已被大规模客流阻塞，任何进一步的路由调整均因上游回压过高而收效甚微。当两条路径的预估通行时间相似但其终端闸机组的通行能力相差数倍时，现有的静态和动态方法均难以在路径决策阶段主动避免将过多客流导向弱出口，导致高负荷场景下局部瓶颈持续恶化。

其二，**已有效果评估大多在单一仿真工具链内完成**——路径优化在数学模型中求解后，在同一软件环境中将优化结果注入仿真模型进行比较[10,19,23–24]。此类"优化前vs.优化后"的对比缺乏与独立外部仿真基准的系统性交叉验证：结论可能受制于特定软件内置行为模式（如PathFinder的Steering模式或SFPE模式）的固有偏差[2]，且较难被独立复现和工程采纳。PathFinder的Goto Any Exit行为模式代表了纯粹基于空间邻近性和动态密度感知的无引导行人行为——将其作为独立的外部基准，能够提供比软件内部比较更具说服力和可重复性的评价准则。

## 1.3 本文工作

为弥补上述不足，本文以龙阳路五线换乘站为研究对象，构建了基于图网络的高精度车站疏散仿真模型，并提出一种**出口容量感知的自适应单步引导算法——Adaptive Queue-Aware A\* (AA\*)**。

龙阳路站位于上海轨道交通网络中，汇集L2、L7、L16、L18和磁悬浮五条线路。各线路站台标高差异最大超过30 m（L18站台埋深约16.97 m，L16站台高架约12.53 m），站厅之间通过长距离换乘通道、扶梯组和天桥连接，是典型的深层-高架混合换乘枢纽。该站共设16个地面出口，其中L2站厅拥有EXIT 2（4道宽闸机，μ≈2.78 pers/s）、EXIT 3（5道宽闸机，μ≈3.47 pers/s）、EXIT 4（7道宽闸机，μ≈4.86 pers/s）和EXIT 6（3道宽闸机，μ≈2.08 pers/s），闸机通行能力最大差距约2.3倍，构成典型的不对称出口配置，为检验动态路径引导中的容量感知能力提供了天然的实验场景。

AA\*算法的核心设计如下。在每个疏散步长内，首先根据Fruin速度—密度模型和即时排队信息计算网络中每条边的时变代价 $g = l/v(\rho) + Q/\mu$（前项为密度制约的通行时间，后项为瓶颈节点的排队等待时间），然后通过A\*搜索获得到达各候选出口的最低代价路径。在此之后，AA\*对候选出口集进行**容量敏感排序**：对每条候选路径，提取其通往出口沿途的最后一个服务瓶颈节点（通常为闸机）的通行能力$\mu_k$，将路径原始代价$c_j$按当量公式 $\tilde{c}_j=c_j/\sqrt{\mu_k}$ 进行折扣。该加权项独立于即时排队变量$Q$，在空队列状态下即可为通向宽闸机的路径赋予排序优势，实现从疏散首步开始的主动容量感知分流。同时，AA\*通过惯性保持机制确保仅在代价改善幅度超过预设阈值时才触发路径切换，以抑制代价微小波动引起的不稳定振荡，并保持引导信号在时间轴上的连续性。算法输出为每个活跃节点的单一下一跳方向，人流在此基础上以严格单路径方式沿边流动，不引入设施级并行分流或强制出口分配，从而将路径决策层与执行物理层之间的边界保持清晰。

本文的主要贡献体现在三个方面：

**(1) 将瓶颈通行能力直接嵌入路径排序层。** 通过$\tilde{c}_j=c_j/\sqrt{\mu_k}$的折扣公式，容量感知在空队列状态下即可发挥作用。在稀疏流量阶段的主动偏向可有效减少高负荷阶段弱出口前的大规模队列积压，构成"先展宽、后治堵"的双阶段策略。

**(2) 以Pathfinder作为独立外部基准进行双场景系统评价。** 在常规突发（mode1, 2187人）和双向列车满载（mode4, 17905人）两个场景下，系统比较AA\*与Improved A\*[20]在总疏散时间、累计排队时间(person·s)、中等和重度拥挤暴露(person·s)以及出口利用均衡性(HHI指数)等多项指标上的差异。通过逐设施（站台等候区→楼扶梯→闸机→出口）路径溯源，定量分析容量感知机制对不同客源组出口选择分布的调控作用及缓解弱出口拥堵的物理机理。

**(3) 建立了执行模型与路径模型的清晰边界。** 通过将并行设施校正和回压（spillback）等非路径层面的执行效应显式分离，使AA\*的路径决策与底层人流推进之间的因果关系可被独立分析、定量归因和参数校准，为后续的模型改进和工程部署提供清晰的模块化框架。

## 1.4 论文结构

第2节介绍车站疏散网络建模方法，包括节点与边的定义、设施通行能力参数标定和站台等候区的粒化表示。第3节详细阐述AA\*算法设计，涵盖边代价函数、容量感知出口排序和惯性保持机制。第4节给出实验设置与mode1/mode4双场景多指标对比结果。第5节进行拥堵溯源与容量感知机制分析，量化AA\*调节出口分布的空间路径。第6节讨论方法的适用条件与局限性。第7节总结全文。

## 参考文献

[1] 中国城市轨道交通协会. 城市轨道交通2024年度统计和分析报告, 2025.
[2] Li C, Tian Z, Yang R, et al. Experimental study for investigating the pedestrian evacuation dynamics pattern in an actual full-size subway station. Tunn Undergr Space Technol, 2025, 166: 106962.
[3] Yang X, Dai W, Li Y, et al. An efficient evacuation path optimization for passengers in subway stations under floods. Tunn Undergr Space Technol, 2024, 143: 105473.
[4] Yu H, Wang Y, Qiu P, et al. Analysis of natural and man-made accidents happened in subway stations and trains. MATEC Web Conf, 2019, 272: 01031.
[5] Haghani M, Sarvi M. Crowd behaviour and motion: Empirical methods. Transp Res Part B, 2018, 107: 253–294.
[6] Huo F, Li Y, Li C, et al. An extended model for pedestrian evacuation in subway station during flood disaster. Tunn Undergr Space Technol, 2022, 129: 104690.
[7] Zuo M, Zhang Y, Wang J, et al. Dynamic route optimization method based on improved A* algorithm and fire prediction data. Tunn Undergr Space Technol, 2024, 146: 105681.
[8] Bai J, Lv X, Nie L, et al. Evacuation route determination in indoor architectural environments based on dynamic fire risk assessment. Buildings, 2025, 15: 1715.
[9] Dorigo M, Maniezzo V, Colorni A. Ant system: optimization by a colony of cooperating agents. IEEE Trans Syst Man Cybern Part B, 1996, 26(1): 29–41.
[10] Yang X, Yang Y, Li Y, et al. Path planning for guided passengers during evacuation in subway station based on multi-objective optimization. Appl Math Model, 2022, 111: 777–801.
[11] Yang X, Yang X, Wang Q, et al. Guide optimization in pedestrian emergency evacuation. Appl Math Comput, 2020, 365: 124711.
[12] Zheng Y, Li X, Jia B, et al. Simulation of pedestrians' evacuation dynamics with underground flood spreading based on cellular automaton. Simul Model Pract Theory, 2019, 94: 149–161.
[13] Kai W, Li S, Zhang H. Simulate the escape behavior of pedestrians. Saf Sci, 2020, 128: 104784.
[14] Huo F, Li Y, Li C, et al. Identifying evacuation bottlenecks in subway stations. Tunn Undergr Space Technol, 2022, 125: 104508.
[15] Li Y, Li C, Zhang H, et al. A modified social force model for evacuation under flood conditions in subway stations. Saf Sci, 2025, 175: 106283.
[16] Fang Y, Shi Q, Hu H, et al. Analysis of pedestrian lane change behavior at ticket gate facilities in subway stations. J Adv Transp, 2022, 2022: 1–12.
[17] Han X, He X, Cong B. Simulation analysis of traffic capacity for ticket gates of metro station. Adv Electron Eng Commun Manag, 2012, 549–553.
[18] Shi C, Zhong M, Nong X, et al. Modeling and safety strategy of passenger evacuation in a metro station in China. Saf Sci, 2012, 50(5): 1319–1332.
[19] Guo K, Zhang L. Simulation-based passenger evacuation optimization in metro stations considering multi-objectives. Autom Constr, 2022, 133: 104010.
[20] Meng D, Hu Z, Zhang H. 基于改进A*算法的多层邮轮疏散系统仿真. J Syst Simul, 2022, 34(6): 1375.
[21] Dai W, Yang X, Li Y. Adaptive single-next-hop guidance for evacuation path planning. Tunn Undergr Space Technol, 2025, submitted.
[22] Feliciani C, Nishinari K. Measurement of congestion and intrinsic risk in pedestrian crowds. Transp Res Part C, 2018, 91: 124–155.
[23] Yang X, Zhang R, Li Y, et al. Passenger evacuation path planning in subway station under multiple fires based on multiobjective robust optimization. IEEE Trans Intell Transp Syst, 2022, 23(11): 21915–21931.
[24] Yang X, Yang Y, Qu D, et al. Multi-objective optimization of evacuation route for heterogeneous passengers in the metro station considering node efficiency. IEEE Trans Intell Transp Syst, 2023, 24(9): 9264–9278.
