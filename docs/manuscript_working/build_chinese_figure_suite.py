from __future__ import annotations

import sys
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "manuscript_working" / "figures_cn"
OUT.mkdir(parents=True, exist_ok=True)
RUN = ROOT / "outputs" / "algorithm_compare" / "mode4_20260808_173528"
PF = ROOT / "docs" / "manuscript_working" / "figures"

COLORS = {
    "improved": "#7A7D80",
    "aa": "#1769AA",
    "pf": "#D28E2B",
    "train": "#9FC5E8",
    "platform": "#5B8FF9",
    "hall": "#61B5A2",
    "transfer": "#9B7EBD",
    "ink": "#252525",
    "light": "#E8EBEF",
    "red": "#C84C4C",
    "green": "#3A8D64",
}


def style() -> None:
    mpl.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Microsoft YaHei", "Arial", "DejaVu Sans"],
        "font.size": 7.5,
        "axes.labelsize": 8,
        "axes.titlesize": 9,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 0.75,
        "legend.frameon": False,
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
    })


def save(fig: plt.Figure, name: str) -> None:
    for suffix, kwargs in {
        ".svg": {}, ".pdf": {}, ".png": {"dpi": 400},
        ".tiff": {"dpi": 600, "pil_kwargs": {"compression": "tiff_lzw"}},
    }.items():
        fig.savefig(OUT / f"{name}{suffix}", bbox_inches="tight", facecolor="white", **kwargs)
    plt.close(fig)


def panel(ax: plt.Axes, label: str) -> None:
    ax.text(-0.12, 1.06, label, transform=ax.transAxes, fontsize=10,
            fontweight="bold", ha="left", va="top")


def fig1_study_design() -> None:
    fig = plt.figure(figsize=(7.2, 4.25))
    gs = fig.add_gridspec(2, 4, height_ratios=[1.05, 0.95], hspace=0.36, wspace=0.28)
    ax = fig.add_subplot(gs[0, :]); ax.axis("off")
    boxes = [
        (0.01, "真实站体与客流", "CAD 几何\n站内基准客流\n列车到达客流", COLORS["light"]),
        (0.265, "共同物理执行器", "行走时间\n设施服务率\n有限接收与溢回", "#E8F1EE"),
        (0.52, "路径决策", "Improved A*\nAA* 到达时刻队列感知", "#E7F0FA"),
        (0.775, "双层验证", "网络仿真\nPathfinder 微观复现\n模块消融", "#F7EEE0"),
    ]
    for x, title, body, color in boxes:
        patch = mpl.patches.FancyBboxPatch((x, 0.17), 0.205, 0.67,
            boxstyle="round,pad=0.012,rounding_size=0.018", fc=color, ec="#88929B", lw=0.8)
        ax.add_patch(patch)
        ax.text(x+0.1025, 0.69, title, ha="center", va="center", weight="bold", fontsize=8.2)
        ax.text(x+0.1025, 0.42, body, ha="center", va="center", linespacing=1.45, color="#40464B")
    for x in [0.22, 0.475, 0.73]:
        ax.annotate("", xy=(x+0.035, 0.505), xytext=(x, 0.505),
                    arrowprops=dict(arrowstyle="-|>", lw=1, color="#59636B"))
    ax.text(0.0, 1.02, "a", transform=ax.transAxes, fontsize=10, weight="bold")

    axb = fig.add_subplot(gs[1, :2]); axb.axis("off")
    axb.set_title("研究问题", loc="left", weight="bold")
    questions = [
        "RQ1  到达时刻队列感知能否改善尾部清空与等待暴露？",
        "RQ2  改善是否以更长绕行和更高计算代价为交换？",
        "RQ3  改善由哪些规划机制驱动，并能否在微观模型中复现？",
    ]
    for i, q in enumerate(questions):
        y = 0.82 - i*0.31
        axb.add_patch(mpl.patches.Circle((0.035, y), 0.024, fc=COLORS["aa"], ec="none"))
        axb.text(0.08, y, q, va="center", fontsize=7.7)
    panel(axb, "b")

    axc = fig.add_subplot(gs[1, 2:]); axc.axis("off")
    axc.set_title("证据与结论的对应关系", loc="left", weight="bold")
    evidence = [
        ("场景真实性", "CAD + 实际客流构成", COLORS["improved"]),
        ("算法效果", "T95/T100、等待、负荷均衡", COLORS["aa"]),
        ("外部复现", "Pathfinder 个体完成时间", COLORS["pf"]),
        ("机制归因", "五项单模块消融", COLORS["green"]),
    ]
    for i, (left, right, color) in enumerate(evidence):
        y = 0.84 - i*0.22
        axc.plot([0.02, 0.20], [y, y], color=color, lw=3, solid_capstyle="round")
        axc.text(0.24, y, left, va="center", weight="bold")
        axc.text(0.52, y, right, va="center", color="#4F555A")
    axc.set_xlim(0, 1)
    panel(axc, "c")
    fig.suptitle("研究设计：以真实换乘站为对象检验到达时刻队列感知路径规划", x=0.02,
                 ha="left", fontsize=11, weight="bold")
    save(fig, "fig1_study_design_cn")


def fig2_demand() -> None:
    data = pd.DataFrame({
        "线路": ["2号线", "7号线", "16号线", "18号线", "磁浮"],
        "列车到达": [4800, 3240, 2460, 3300, 1918],
        "站台候车": [236, 219, 42, 178, 0],
        "站厅": [350, 112, 15, 125, 0],
        "换乘": [526, 169, 27, 188, 0],
    })
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(7.2, 3.15), gridspec_kw={"width_ratios":[1.72, 1]})
    x = np.arange(len(data)); bottom = np.zeros(len(data))
    specs = [("列车到达", COLORS["train"]), ("站台候车", COLORS["platform"]),
             ("站厅", COLORS["hall"]), ("换乘", COLORS["transfer"])]
    for col, color in specs:
        ax.bar(x, data[col], bottom=bottom, color=color, width=0.68, label=col,
               edgecolor="white", linewidth=0.4)
        bottom += data[col].to_numpy()
    for xi, total in zip(x, bottom):
        ax.text(xi, total+100, f"{int(total):,}", ha="center", va="bottom", fontsize=7)
    ax.set_xticks(x, data["线路"]); ax.set_ylabel("人数"); ax.set_title("各线路高负荷人口构成", loc="left")
    ax.legend(ncol=2, loc="upper right"); ax.set_ylim(0, 6400); panel(ax, "a")

    low, high = 2187, int(bottom.sum())
    ax2.barh([1,0], [low, high], color=[COLORS["improved"], COLORS["aa"]], height=0.45)
    ax2.set_yticks([1,0], ["基准需求", "列车到达叠加需求"])
    ax2.set_xlabel("总人数"); ax2.set_title("两类需求场景", loc="left")
    ax2.set_xlim(0, 19000)
    for y, v in zip([1,0], [low,high]): ax2.text(v+250, y, f"{v:,}", va="center", weight="bold")
    ax2.text(0.03, -0.34, "高负荷 = 2,187 人站内基准客流 + 15,718 人列车到达客流",
             transform=ax2.transAxes, fontsize=7, color="#4F555A")
    panel(ax2, "b")
    fig.suptitle("场景构造保留了可追溯的人口来源与线路差异", x=0.02, ha="left", fontsize=10.5, weight="bold")
    fig.tight_layout(rect=[0,0,1,0.94])
    save(fig, "fig2_demand_composition_cn")


def fig3_method() -> None:
    fig = plt.figure(figsize=(7.2, 4.2))
    gs = fig.add_gridspec(2, 3, height_ratios=[1.05, 1], hspace=0.38, wspace=0.32)
    ax = fig.add_subplot(gs[0, :]); ax.axis("off")
    xs = [0.04, 0.24, 0.44, 0.64, 0.84]
    labels = ["当前位置\n$t_0$", "物理行走\n$\\ell/v(\\rho)$", "预测资源队列\n$Q_r(\\tau)/\\mu_r$",
              "空间接收等待\n$W_s(\\tau)$", "候选出口\n目标值"]
    colors = [COLORS["light"], "#E6EEF7", "#BCD5EE", "#9FC4E4", "#6FA6D2"]
    ax.plot([xs[0], xs[-1]], [0.48,0.48], color="#A7B0B8", lw=2)
    for x, lab, c in zip(xs, labels, colors):
        ax.add_patch(mpl.patches.Circle((x,0.48),0.045,fc=c,ec="#61717E",lw=0.8,zorder=3))
        ax.text(x,0.2,lab,ha="center",va="center",fontsize=7.4)
    ax.annotate("到达时刻随前序行走与等待累积更新", xy=(0.72,0.72), xytext=(0.28,0.72),
                arrowprops=dict(arrowstyle="-|>",color=COLORS["aa"],lw=1.2), color=COLORS["aa"],ha="center")
    ax.text(0,1.02,"a",transform=ax.transAxes,fontsize=10,weight="bold")

    axb=fig.add_subplot(gs[1,0]); axb.axis("off"); axb.set_title("AA* 规划代价",loc="left",weight="bold")
    axb.text(0.02,0.74,r"$C(P)=\sum [t+w^{q}+w^{s}] + \lambda R(P)$",
             fontsize=10,color=COLORS["ink"])
    axb.text(0.02,0.46,"行走时间 + 资源等待\n+ 空间接收等待",fontsize=7.3,linespacing=1.45)
    axb.text(0.02,0.18,"密度暴露惩罚区分\n同等时间下的拥挤路径",fontsize=7.2,color="#4F555A",linespacing=1.4)
    panel(axb,"b")

    axc=fig.add_subplot(gs[1,1]); axc.axis("off"); axc.set_title("时变多标签搜索",loc="left",weight="bold")
    axc.text(0.05,0.82,"同一节点保留多个到达时刻标签",fontsize=7.4)
    for i,(t,c) in enumerate([(42,51),(55,48),(68,57)]):
        y=.60-i*.18; axc.add_patch(mpl.patches.FancyBboxPatch((.08,y-.05),.76,.10,boxstyle="round,pad=.01",fc="#EAF2F9",ec="#8DA9C2"))
        axc.text(.14,y,f"到达 {t} s",va="center",fontsize=7.1); axc.text(.57,y,f"目标值 {c}",va="center",fontsize=7.1)
    axc.text(.05,.08,"避免过早合并不同未来队列状态",color="#4F555A",fontsize=7.0); panel(axc,"c")

    axd=fig.add_subplot(gs[1,2]); axd.axis("off"); axd.set_title("单模块消融",loc="left",weight="bold")
    items=["到达时刻队列预测","资源队列等待","空间接收等待","多标签搜索","密度风险惩罚"]
    for i,item in enumerate(items):
        y=.8-i*.17; axd.add_patch(mpl.patches.Rectangle((.05,y-.035),.07,.07,fc=COLORS["aa"],ec="none",alpha=1-i*.12)); axd.text(.17,y,item,va="center")
    panel(axd,"d")
    fig.suptitle("AA* 将路径代价与预计到达瓶颈的状态对齐",x=.02,ha="left",fontsize=10.5,weight="bold")
    save(fig,"fig3_aa_method_cn")


def fig4_network_results() -> None:
    summary = pd.read_csv(RUN / "charts" / "compiled_summary_metrics.csv")
    lines = pd.read_csv(RUN / "charts" / "compiled_line_clearance.csv")
    exits = pd.read_csv(RUN / "charts" / "compiled_exit_usage.csv")
    methods=["ImprovedAStar","AdaptiveQueueAwareAStar"]; labels=["Improved A*","AA*"]
    fig=plt.figure(figsize=(7.2,5.0)); gs=fig.add_gridspec(2,3,height_ratios=[1,1.05],hspace=.42,wspace=.42)
    metrics=[("T95_seconds","T95 (s)"),("T100_seconds","T100 (s)"),("mean_total_evacuation_time_seconds_per_person","人均完成时间 (s)")]
    for k,(col,title) in enumerate(metrics):
        ax=fig.add_subplot(gs[0,k]); vals=[float(summary.loc[summary.metric==col,m].iloc[0]) for m in methods]
        ax.bar([0,1],vals,color=[COLORS["improved"],COLORS["aa"]],width=.62)
        ax.set_xticks([0,1],labels,rotation=17,ha="right"); ax.set_title(title,loc="left")
        for x,v in enumerate(vals): ax.text(x,v+max(vals)*.025,f"{v:.0f}",ha="center",fontsize=7)
        ax.set_ylim(0,max(vals)*1.18); panel(ax,chr(ord('a')+k))
    ax=fig.add_subplot(gs[1,:2]); pivot=lines.pivot(index="line",columns="method",values="clearance_time_seconds").reindex(["L2","L7","L16","L18","Maglev"])
    x=np.arange(len(pivot)); w=.34
    ax.bar(x-w/2,pivot["Improved"],width=w,color=COLORS["improved"],label="Improved A*")
    ax.bar(x+w/2,pivot["AA"],width=w,color=COLORS["aa"],label="AA*")
    ax.set_xticks(x,["2号线","7号线","16号线","18号线","磁浮"]); ax.set_ylabel("线路清空时间 (s)")
    ax.set_title("线路级尾部清空发生了结构性重分配",loc="left"); ax.legend(ncol=2); panel(ax,"d")
    ax2=fig.add_subplot(gs[1,2]); j=[float(summary.loc[summary.metric=="exit_load_jain_index",m].iloc[0]) for m in methods]; f=[float(summary.loc[summary.metric=="key_facility_load_jain_index",m].iloc[0]) for m in methods]
    ax2.plot([0,1],j,marker="o",color="#5E8C6A",lw=1.5,label="出口")
    ax2.plot([0,1],f,marker="o",color="#8E6C9F",lw=1.5,label="关键设施")
    ax2.set_xticks([0,1],labels,rotation=17,ha="right"); ax2.set_ylim(0,1); ax2.set_ylabel("Jain 均衡指数")
    ax2.set_title("负荷均衡",loc="left"); ax2.legend(); panel(ax2,"e")
    fig.suptitle("网络仿真表明 AA* 主要改善尾部清空、等待暴露与设施负荷分配",x=.02,ha="left",fontsize=10.5,weight="bold")
    save(fig,"fig4_network_high_load_cn")


def fig5_pathfinder() -> None:
    completion=pd.read_csv(PF/"fig2_pathfinder_high_load_completion_source.csv")
    summary=pd.read_csv(PF/"table_pathfinder_high_load_summary.csv")
    paired=pd.read_csv(PF/"table_pathfinder_high_load_paired.csv").iloc[0]
    colors={"Improved A*":COLORS["improved"],"AA*":COLORS["aa"],"PF-LQ":COLORS["pf"]}
    fig=plt.figure(figsize=(7.2,4.3)); gs=fig.add_gridspec(2,3,height_ratios=[1.3,1],hspace=.4,wspace=.38)
    ax=fig.add_subplot(gs[0,:2])
    for m,g in completion.groupby("method"):
        ax.plot(g.exit_time_s,g.cumulative_completed_pct,color=colors[m],lw=1.5 if m=="AA*" else 1.2,label=m)
    ax.set_xlim(0,1500);ax.set_ylim(0,100);ax.set_xlabel("个体完成时间 (s)");ax.set_ylabel("累计完成比例 (%)");ax.legend(ncol=3,loc="lower right");ax.set_title("完整累计完成曲线",loc="left");panel(ax,"a")
    axb=fig.add_subplot(gs[0,2]); qs=["T50_s","T80_s","T95_s","T99_s","T100_s"]; y=np.arange(len(qs))
    for m in colors:
        row=summary[summary.method==m].iloc[0]; axb.plot([row[q] for q in qs],y,marker="o",ms=3,color=colors[m],lw=1)
    axb.set_yticks(y,["T50","T80","T95","T99","T100"]);axb.invert_yaxis();axb.set_xlabel("时间 (s)");axb.set_title("中位数至尾部",loc="left");panel(axb,"b")
    axc=fig.add_subplot(gs[1,0]); sub=summary.set_index("method").loc[["Improved A*","AA*","PF-LQ"]]
    vals=sub.mean_exit_time_s; axc.bar(range(3),vals,color=[colors[m] for m in sub.index]);axc.set_xticks(range(3),sub.index,rotation=20,ha="right");axc.set_ylabel("平均完成时间 (s)");axc.set_title("平均完成时间",loc="left");panel(axc,"c")
    axd=fig.add_subplot(gs[1,1]); vals=sub.T100_s; axd.bar(range(3),vals,color=[colors[m] for m in sub.index]);axd.set_xticks(range(3),sub.index,rotation=20,ha="right");axd.set_ylabel("T100 (s)");axd.set_title("最大完成时间",loc="left");panel(axd,"d")
    axe=fig.add_subplot(gs[1,2]); axe.axis("off"); axe.set_title("AA* 与 Improved A* 的个体配对",loc="left")
    stats=[("配对人数",f"{int(paired.paired_n):,}"),("AA* 更快",f"{paired.AA_faster_pct:.1f}%"),("平均节省",f"{paired.mean_time_saved_by_AA_s:.1f} s"),("中位节省",f"{paired.median_time_saved_by_AA_s:.1f} s")]
    for i,(k,v) in enumerate(stats):
        yy=.8-i*.22;axe.text(.02,yy,k,color="#5A6065");axe.text(.98,yy,v,ha="right",weight="bold",color=COLORS["aa"] if i else COLORS["ink"])
    panel(axe,"e")
    fig.suptitle("Pathfinder 高负荷外部复现：AA* 改善尾部清空，但 PF-LQ 的平均完成时间更短",x=.02,ha="left",fontsize=10.2,weight="bold")
    save(fig,"fig5_pathfinder_validation_cn")


def fig6_source_exit_redistribution() -> None:
    data = pd.read_csv(RUN / "charts" / "compiled_exit_source_by_line.csv")
    line_order = ["L2", "L7", "L16", "L18", "Maglev"]
    exit_order = [
        "Exit_L2_2", "Exit_L2_3", "Exit_L2_4", "Exit_L2_6",
        "Exit_L7_7", "Exit_L7_8/9", "Exit_L16_10", "Exit_L16_11_east",
        "Exit_L16_11_west", "Exit_L18_12", "Exit_L18_13", "Exit_L18_17",
        "Exit_Maglev_18", "Exit_Maglev_19", "Exit_Maglev_20", "Exit_Maglev_21",
    ]
    short = ["2-2", "2-3", "2-4", "2-6", "7-7", "7-8/9", "16-10", "16-11E",
             "16-11W", "18-12", "18-13", "18-17", "磁18", "磁19", "磁20", "磁21"]

    def matrix(method: str) -> pd.DataFrame:
        sub = data[data.method == method]
        return (sub.pivot_table(index="line", columns="exit_name", values="people", aggfunc="sum", fill_value=0)
                .reindex(index=line_order, columns=exit_order, fill_value=0))

    improved = matrix("Improved")
    aa = matrix("AA")
    diff = aa - improved
    vmax = max(float(improved.to_numpy().max()), float(aa.to_numpy().max()))
    dmax = float(np.abs(diff.to_numpy()).max())
    fig, axes = plt.subplots(3, 1, figsize=(7.2, 5.1), gridspec_kw={"height_ratios": [1, 1, 1.05], "hspace": .44})
    for idx, (ax, values, title) in enumerate(zip(
        axes, [improved, aa, diff],
        ["Improved A*", "AA*", "AA* - Improved A*（正值表示 AA* 分配更多）"],
    )):
        if idx < 2:
            image = ax.imshow(values, aspect="auto", cmap="Blues", vmin=0, vmax=vmax)
        else:
            image = ax.imshow(values, aspect="auto", cmap="RdBu_r", vmin=-dmax, vmax=dmax)
        ax.set_yticks(range(len(line_order)), ["2号线", "7号线", "16号线", "18号线", "磁浮"])
        ax.set_xticks(range(len(short)), short, rotation=48, ha="right")
        ax.set_title(title, loc="left")
        ax.set_ylabel("客流来源")
        ax.tick_params(length=0)
        for spine in ax.spines.values():
            spine.set_visible(False)
        cbar = fig.colorbar(image, ax=ax, fraction=.015, pad=.012)
        cbar.ax.tick_params(labelsize=6)
        panel(ax, chr(ord("a") + idx))
    axes[-1].set_xlabel("疏散出口（线路-出口编号）")
    fig.suptitle("AA* 改变来源线路—出口分配，形成站级负荷重构", x=.02, ha="left", fontsize=10.5, weight="bold")
    save(fig, "fig6_source_exit_redistribution_cn")


def fig8_pathfinder_tradeoff() -> None:
    summary = pd.read_csv(PF / "table_pathfinder_high_load_summary.csv").set_index("method")
    methods = ["Improved A*", "AA*", "PF-LQ"]
    colors = [COLORS["improved"], COLORS["aa"], COLORS["pf"]]
    sub = summary.loc[methods]
    fig = plt.figure(figsize=(7.2, 4.25))
    gs = fig.add_gridspec(2, 2, hspace=.48, wspace=.38)

    ax = fig.add_subplot(gs[0, 0])
    x = np.arange(3)
    ax.bar(x, sub.mean_level_congestion_s, color=colors, width=.64, label="水平区域")
    ax.bar(x, sub.mean_stair_congestion_s, bottom=sub.mean_level_congestion_s,
           color=[mpl.colors.to_rgba(c, .48) for c in colors], width=.64, label="楼梯")
    ax.set_xticks(x, methods, rotation=17, ha="right")
    ax.set_ylabel("人均拥堵时间 (s)")
    ax.set_title("拥堵暴露构成", loc="left")
    ax.legend(ncol=2, loc="upper right")
    panel(ax, "a")

    ax = fig.add_subplot(gs[0, 1])
    ax.bar(x, sub.mean_distance_m, color=colors, width=.64)
    ax.set_xticks(x, methods, rotation=17, ha="right")
    ax.set_ylabel("人均移动距离 (m)")
    ax.set_title("移动距离", loc="left")
    for xx, value in zip(x, sub.mean_distance_m):
        ax.text(xx, value + 2, f"{value:.1f}", ha="center", fontsize=7)
    ax.set_ylim(0, max(sub.mean_distance_m) * 1.18)
    panel(ax, "b")

    ax = fig.add_subplot(gs[1, 0])
    offsets = {"Improved A*": (-70, 3), "AA*": (6, -2), "PF-LQ": (7, 3)}
    for method, color in zip(methods, colors):
        row = sub.loc[method]
        ax.scatter(row.mean_exit_time_s, row.T100_s, s=42, color=color, zorder=3)
        ax.annotate(method, (row.mean_exit_time_s, row.T100_s), xytext=offsets[method], textcoords="offset points", fontsize=7)
    ax.set_xlabel("平均完成时间 (s)")
    ax.set_ylabel("T100 (s)")
    ax.set_title("平均效率—尾部清空取舍", loc="left")
    ax.set_xlim(355, 445)
    ax.set_ylim(1280, 1475)
    ax.annotate("更优方向", xy=(350, 1285), xytext=(408, 1430),
                arrowprops=dict(arrowstyle="-|>", color="#6D747A", lw=.9), color="#6D747A")
    panel(ax, "c")

    ax = fig.add_subplot(gs[1, 1])
    metric_cols = ["mean_exit_time_s", "T100_s", "mean_congestion_time_s", "mean_distance_m"]
    metric_labels = ["平均完成", "T100", "拥堵时间", "移动距离"]
    reference = sub.loc["Improved A*", metric_cols].astype(float)
    reductions = []
    for method in ["AA*", "PF-LQ"]:
        values = sub.loc[method, metric_cols].astype(float)
        reductions.append(((reference - values) / reference * 100).to_numpy(dtype=float))
    reductions = np.asarray(reductions)
    lim = float(np.max(np.abs(reductions)))
    image = ax.imshow(reductions, cmap="RdBu", vmin=-lim, vmax=lim, aspect="auto")
    ax.set_xticks(range(4), metric_labels, rotation=20, ha="right")
    ax.set_yticks(range(2), ["AA*", "PF-LQ"])
    for i in range(2):
        for j in range(4):
            value = reductions[i, j]
            ax.text(j, i, f"{value:+.1f}%", ha="center", va="center", fontsize=7,
                    color="white" if abs(value) > lim * .5 else COLORS["ink"])
    ax.set_title("相对 P-Improved 的改善率", loc="left")
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.colorbar(image, ax=ax, fraction=.045, pad=.03, label="降低率 (%)")
    panel(ax, "d")
    fig.suptitle("Pathfinder 结果揭示平均效率、尾部清空与路径距离的不同运行点", x=.02, ha="left", fontsize=10.3, weight="bold")
    save(fig, "fig8_pathfinder_tradeoff_cn")


def fig_station_network() -> None:
    import network as net

    graph = net.build_graph()
    include_types = {
        "platform", "platform_waiting_zone", "stair", "escalator",
        "queue_area", "gate_wide", "gate_tripod", "passageway", "exit",
    }
    nodes = [n for n, d in graph.nodes(data=True) if d.get("type") in include_types]
    pos = {n: graph.nodes[n].get("pos") for n in nodes}
    nodes = [n for n in nodes if pos[n] is not None]
    pos = {n: pos[n] for n in nodes}
    type_colors = {
        "platform": "#98A7B5", "platform_waiting_zone": "#C7D0D8",
        "stair": "#7E6AA2", "escalator": "#B59AC8",
        "queue_area": "#B9D7CD", "gate_wide": "#61B5A2", "gate_tripod": "#438F80",
        "passageway": "#C9AA7A", "exit": "#D28E2B",
    }
    type_sizes = {"platform": 24, "platform_waiting_zone": 7, "stair": 13, "escalator": 13,
                  "queue_area": 8, "gate_wide": 14, "gate_tripod": 14, "passageway": 12, "exit": 28}

    fig, (ax, axb) = plt.subplots(1, 2, figsize=(7.2, 4.25), gridspec_kw={"width_ratios":[2.3,1]})
    for u, v in graph.edges():
        if u in pos and v in pos:
            ax.plot([pos[u][0], pos[v][0]], [pos[u][1], pos[v][1]], color="#CDD2D6", lw=.38, zorder=1)
    for typ, color in type_colors.items():
        subset=[n for n in nodes if graph.nodes[n].get("type")==typ]
        if not subset: continue
        ax.scatter([pos[n][0] for n in subset],[pos[n][1] for n in subset],s=type_sizes[typ],
                   c=color,edgecolors="white",linewidths=.3,zorder=2,label=typ)
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    for spine in ax.spines.values(): spine.set_visible(False)
    ax.set_title("CAD 派生的站内设施拓扑",loc="left"); panel(ax,"a")

    axb.axis("off"); axb.set_title("模型规模与映射对象",loc="left")
    counts=[("全部节点",graph.number_of_nodes()),("有向边",graph.number_of_edges()),("出口",sum(graph.nodes[n].get("type")=="exit" for n in graph)),
            ("楼梯",sum(graph.nodes[n].get("type")=="stair" for n in graph)),("自动扶梯",sum(graph.nodes[n].get("type")=="escalator" for n in graph)),
            ("闸机/排队区",sum(graph.nodes[n].get("type") in {"gate_wide","gate_tripod","queue_area"} for n in graph))]
    for i,(k,v) in enumerate(counts):
        y=.86-i*.12; axb.text(.02,y,k,color="#555B60");axb.text(.62,y,f"{v:,}",weight="bold",color=COLORS["ink"])
    legend_items=[("站台/候车区","#98A7B5"),("楼扶梯","#8F78AA"),("闸机/排队区","#61B5A2"),("通道","#C9AA7A"),("出口","#D28E2B")]
    for i,(lab,c) in enumerate(legend_items):
        y=.32-i*.085;axb.scatter(.04,y,s=25,c=c);axb.text(.11,y,lab,va="center",fontsize=7.2)
    axb.set_xlim(0,1);axb.set_ylim(0,1);panel(axb,"b")
    fig.suptitle("真实站体被映射为可计算的设施—通道有向网络",x=.02,ha="left",fontsize=10.5,weight="bold")
    save(fig,"fig_station_network_cn")


def fig_ablation() -> None:
    candidates = sorted((ROOT / "outputs" / "ablation").glob("mode4_*/ablation_results.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        return
    frames = []
    for path in candidates:
        frame = pd.read_csv(path)
        frame["_source_mtime"] = path.stat().st_mtime
        frames.append(frame)
    data = pd.concat(frames, ignore_index=True)
    data = data.sort_values("_source_mtime", ascending=False).drop_duplicates("variant", keep="first")
    variant_order = [
        "Full AA*", "No arrival-time queue prediction", "No resource-queue waiting cost",
        "No spatial receiving wait", "Single-label search", "No density-risk penalty",
    ]
    data["_order"] = data["variant"].map({name: i for i, name in enumerate(variant_order)})
    data = data.sort_values("_order").reset_index(drop=True)
    if len(data) < 2:
        return
    label_map = {
        "Full AA*":"完整 AA*", "No arrival-time queue prediction":"无到达时刻预测",
        "No resource-queue waiting cost":"无资源等待代价", "No spatial receiving wait":"无空间接收等待",
        "Single-label search":"单标签搜索", "No density-risk penalty":"无密度风险惩罚",
    }
    data["label"] = data.variant.map(label_map).fillna(data.variant)
    full = data.iloc[0]
    fig=plt.figure(figsize=(7.2,4.2));gs=fig.add_gridspec(2,3,height_ratios=[1,1],hspace=.44,wspace=.38)
    plots=[("T95_s","T95 (s)"),("T100_s","T100 (s)"),("stationary_person_s","累计停滞 (百万人·s)"),
           ("mean_total_evacuation_time_s","人均完成时间 (s)"),("total_movement_distance_m","总移动距离 (km)"),("wall_clock_s","运行时间 (s)")]
    for i,(col,title) in enumerate(plots):
        ax=fig.add_subplot(gs[i//3,i%3]);vals=data[col].astype(float).copy()
        if col=="stationary_person_s": vals=vals/1e6
        if col=="total_movement_distance_m": vals=vals/1e3
        colors=[COLORS["aa"]]+[mpl.colors.to_rgba(COLORS["aa"],.35+.1*j) for j in range(1,len(data))]
        y=np.arange(len(data));ax.barh(y,vals,color=colors,height=.63)
        ax.set_yticks(y,data.label if i in {0,3} else [""]*len(data));ax.invert_yaxis();ax.set_title(title,loc="left")
        for yy,v in zip(y,vals): ax.text(v+max(vals)*.02,yy,f"{v:.1f}" if max(vals)<100 else f"{v:.0f}",va="center",fontsize=6.6)
        ax.set_xlim(0,max(vals)*1.19);panel(ax,chr(ord('a')+i))
    fig.suptitle("单模块消融：逐项识别 AA* 的有效规划机制",x=.02,ha="left",fontsize=10.4,weight="bold")
    save(fig,"fig7_ablation_cn")


def main() -> None:
    style(); fig1_study_design(); fig2_demand(); fig_station_network(); fig3_method(); fig4_network_results(); fig6_source_exit_redistribution(); fig5_pathfinder(); fig8_pathfinder_tradeoff(); fig_ablation()
    print(OUT)


if __name__ == "__main__": main()
