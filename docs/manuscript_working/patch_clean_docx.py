from __future__ import annotations

import re
import zipfile
from pathlib import Path


WORK = Path(__file__).resolve().parent
SRC = WORK / "43_tust_manuscript_rewritten_cn_two_loads.docx"
DST = WORK / "44_tust_manuscript_rewritten_cn_two_loads_clean.docx"
FIG = WORK / "figures_revised"


def para_text(xml: str) -> str:
    parts = re.findall(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", xml, flags=re.S)
    parts += re.findall(r"<m:t(?:\s[^>]*)?>(.*?)</m:t>", xml, flags=re.S)
    return "".join(parts)


def replace_para_text(xml: str, old_prefix: str, new_text: str) -> tuple[str, bool]:
    pattern = re.compile(r"<w:p\b[^>]*>.*?</w:p>", flags=re.S)
    for match in list(pattern.finditer(xml)):
        block = match.group(0)
        if not para_text(block).startswith(old_prefix):
            continue
        t_matches = list(re.finditer(r"<w:t(\s[^>]*)?>(.*?)</w:t>", block, flags=re.S))
        if not t_matches:
            return xml, False
        first = t_matches[0]
        replacement = f"<w:t{first.group(1) or ''}>{new_text}</w:t>"
        block_new = block[: first.start()] + replacement + block[first.end() :]
        # Remove any additional text nodes from the old paragraph.
        block_new = re.sub(
            r"<w:t(\s[^>]*)?>.*?</w:t>",
            lambda m: replacement if m.start() == block_new.find(replacement) else "<w:t></w:t>",
            block_new,
            count=0,
            flags=re.S,
        )
        # The replacement above may have been duplicated; normalize to one text node.
        first_new = re.search(r"<w:t(\s[^>]*)?>.*?</w:t>", block_new, flags=re.S)
        if first_new:
            prefix = block_new[: first_new.start()]
            suffix = block_new[first_new.end() :]
            suffix = re.sub(r"<w:t(\s[^>]*)?>.*?</w:t>", "<w:t></w:t>", suffix, flags=re.S)
            block_new = prefix + replacement + suffix
        return xml[: match.start()] + block_new + xml[match.end() :], True
    return xml, False


def remove_para(xml: str, prefix: str) -> tuple[str, bool]:
    pattern = re.compile(r"<w:p\b[^>]*>.*?</w:p>", flags=re.S)
    for match in list(pattern.finditer(xml)):
        block = match.group(0)
        if para_text(block).startswith(prefix):
            return xml[: match.start()] + xml[match.end() :], True
    return xml, False


def main() -> None:
    with zipfile.ZipFile(SRC, "r") as zin:
        document = zin.read("word/document.xml").decode("utf-8")

        # Remove the explicitly rejected passenger-level pairing paragraph and equation.
        document, ok_pair = remove_para(document, "Improved A* 与 AA* 的乘客姓名集合一致")
        document, ok_delta = remove_para(document, "(9)ΔTi=TiImproved−TiAA")

        replacements = {
            "在 Pathfinder 连续空间运动中，AA* 路径相对 Improved A* 路径":
                "在 Pathfinder 连续空间运动中，AA* 路径相对 Improved A* 路径将平均完成时间从 435.5 s 降至 396.0 s，T95 从 1024.5 s 降至 985.1 s，T100 从 1414.6 s 降至 1298.3 s；平均拥堵时间由 311.3 s 降至 276.6 s。三项完成时间指标和拥堵暴露尾部均显示，AA* 的站级尾部改善能够在连续空间执行中复现。",
            "图8 Pathfinder 高负荷完成时间与拥堵暴露分布":
                "图8 Pathfinder 高负荷完成时间与拥堵暴露分布。（a）全部乘客的经验累计完成曲线；（b）完成时间分位剖面；（c）乘客移动距离的经验累计分布；（d）累计拥堵暴露的尾部分布。Goto Any Exit 只做场景级比较。",
            "低负荷 Pathfinder 三组协议均使用 2,187 名乘客":
                "低负荷 Pathfinder 三组协议均使用 2,187 名乘客和同一 SHA-256 几何文件。Improved A* 的平均完成时间、T95 和 T100 分别为 117.6、254.6 和 319.0 s；AA* 分别为 120.8、254.6 和 319.0 s。AA* 的平均拥堵时间为 9.2 s/人，略低于 Improved A* 的 9.4 s/人，但平均移动距离由 120.7 m 增至 124.7 m。由此可见，低负荷下两种预分配路径的 T95 和 T100 相同，AA* 的差异主要体现在略低的平均拥堵暴露和略高的移动距离，而没有转化为更短的连续空间平均完成时间。",
            "图10 Pathfinder 两种负荷下的连续空间复现":
                "图10 Pathfinder 两种负荷下的连续空间复现。（a）三种协议的经验累计完成曲线；（b）完成时间分位剖面；（c）平均完成时间与尾部完成时间的联合比较；（d）拥堵暴露尾部。颜色区分协议，实线为低负荷，虚线为高负荷。",
            "Pathfinder Goto Any Exit 揭示了平均效率与尾部清空的分离":
                "Pathfinder Goto Any Exit 揭示了平均效率与尾部清空的分离，而且这一现象在两种负荷下均出现。自主选出口能够让大量乘客快速完成，但局部选择累积后，少量乘客可能进入持续更久的残余阶段。AA* 在高负荷下同时降低平均完成时间、T95、T100 和拥堵暴露；在低负荷下，AA* 与 Improved A* 的 T95、T100 相同，仅平均拥堵暴露略低而平均完成时间略高。因而本文同时报告平均值、尾部指标、移动代价和计算代价，避免用单一指标概括不同协议。",
            "AA* 的运行代价明显高于 Improved A*":
                "AA* 的运行代价明显高于 Improved A*，高负荷时差异尤其明显，更适合转化为列车、站台或客流批次级引导策略，通过动态标志、广播或现场组织实施，而不是要求每名乘客进行高频个体重规划。低负荷结果显示，资源竞争减弱后，网络层的等待暴露仍可降低，但连续空间中的完成时间指标未进一步缩短，因此实施评价应同时关注批次级清空和连续空间运动结果。",
            "本文将多线换乘站疏散路径规划表述为共享服务能力上的到达时刻协调":
                "本文将多线换乘站疏散路径规划表述为共享服务能力上的到达时刻协调，并提出在时变多标签搜索中推进当前队列、在途承诺流量与资源服务过程的 AA*。高负荷网络仿真表明，AA* 相比 Improved A* 同时缩短 T95–T100 尾部并减少累计静止暴露，其实现机制是增加部分移动以避开未来共享瓶颈；低负荷下，AA* 仍降低 T95 和静止暴露，但不改变 T100。消融将资源队列等待识别为基础机制，将到达时刻预测识别为主要增益来源，并显示多标签与密度暴露主要收紧最末端清空。Pathfinder 连续空间复现表明，AA* 的平均和尾部改善在高负荷下可以复现；在低负荷下，两种预分配路径的 T95、T100 相同，AA* 主要表现为略低的平均拥堵暴露和略高的移动距离。软件原生 Goto Any Exit 在两种负荷下均取得较低平均或 T95，却保留略长的 T100，进一步区分了典型乘客效率与全站残余尾部。",
        }
        changed = []
        for prefix, text in replacements.items():
            document, ok = replace_para_text(document, prefix, text)
            changed.append((prefix[:18], ok))

        with zipfile.ZipFile(DST, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename == "word/document.xml":
                    data = document.encode("utf-8")
                elif info.filename == "word/media/image8.png":
                    data = (FIG / "fig_pathfinder_high_load_revised_cn.png").read_bytes()
                elif info.filename == "word/media/image10.png":
                    data = (FIG / "fig_load_stratified_pathfinder_cn.png").read_bytes()
                zout.writestr(info, data)

    print({"removed_pairing": ok_pair, "removed_delta": ok_delta, "replacements": changed, "output": str(DST)})


if __name__ == "__main__":
    main()
