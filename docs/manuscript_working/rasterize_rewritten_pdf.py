from pathlib import Path

import fitz
from PIL import Image, ImageDraw


HERE = Path(__file__).resolve().parent
RENDER = HERE / "render_rewritten_cn"
PDF = RENDER / "43_tust_manuscript_rewritten_cn_two_loads.pdf"


def main():
    doc = fitz.open(PDF)
    page_paths = []
    for i, page in enumerate(doc, start=1):
        pix = page.get_pixmap(matrix=fitz.Matrix(1.55, 1.55), alpha=False)
        out = RENDER / f"page-{i:02d}.png"
        pix.save(out)
        page_paths.append(out)

    thumbs = []
    for i, path in enumerate(page_paths, start=1):
        im = Image.open(path).convert("RGB")
        im.thumbnail((425, 600))
        tile = Image.new("RGB", (445, 640), "white")
        tile.paste(im, ((445 - im.width) // 2, 28))
        ImageDraw.Draw(tile).text((12, 8), f"Page {i}", fill="black")
        thumbs.append(tile)

    cols = 4
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 445, rows * 640), "#dadada")
    for j, tile in enumerate(thumbs):
        sheet.paste(tile, ((j % cols) * 445, (j // cols) * 640))
    sheet.save(RENDER / "contact_sheet.png", quality=95)
    print(f"pages={len(page_paths)}")


if __name__ == "__main__":
    main()
