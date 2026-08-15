from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).resolve().parent
FIG = HERE / "figures_revised"
OUT = FIG / "figure_suite_contact_sheet.png"

FILES = [
    ("图1 站体空间结构", "fig_station_spatial_structure_cn.png"),
    ("图2 AA* 方法机制", "fig_aa_method_revised_cn.png"),
    ("图3 需求场景构成", "fig_demand_revised_cn.png"),
    ("图4 网络高负荷结果", "fig_network_high_load_revised_cn.png"),
    ("图5 来源—出口重分配", "fig_flow_redistribution_revised_cn.png"),
    ("图6 单模块消融", "fig_ablation_revised_cn.png"),
    ("图7 Pathfinder 完成分布", "fig_pathfinder_high_load_revised_cn.png"),
    ("图8 Pathfinder 取舍", "fig_pathfinder_tradeoff_revised_cn.png"),
]


def font(size, bold=False):
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def main():
    tile_w, tile_h = 1000, 690
    canvas = Image.new("RGB", (tile_w * 2 + 90, tile_h * 4 + 135), "#eef0f1")
    draw = ImageDraw.Draw(canvas)
    draw.text((45, 26), "中文论文主图套件｜高负荷结果版", fill="#22272b", font=font(28, True))
    draw.text((45, 69), "统一蓝—红—中性灰；分布与机制证据优先；不使用原始 572 节点网络图", fill="#60686d", font=font(18))
    for idx, (label, filename) in enumerate(FILES):
        x = 30 + (idx % 2) * (tile_w + 30)
        y = 115 + (idx // 2) * tile_h
        tile = Image.new("RGB", (tile_w, tile_h - 20), "white")
        td = ImageDraw.Draw(tile)
        td.text((22, 16), label, fill="#202529", font=font(21, True))
        im = Image.open(FIG / filename).convert("RGB")
        im.thumbnail((tile_w - 44, tile_h - 92))
        tile.paste(im, ((tile_w - im.width) // 2, 58 + (tile_h - 92 - im.height) // 2))
        canvas.paste(tile, (x, y))
    canvas.save(OUT, quality=94)
    print(OUT)


if __name__ == "__main__":
    main()
