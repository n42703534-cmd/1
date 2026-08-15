from __future__ import annotations

import json
import re
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs" / "manuscript_working" / "24_zotero_pdf_logic_extracts.json"

TARGET_DOIS = {
    "10.1016/j.tust.2023.105473",
    "10.1016/j.apm.2022.07.024",
    "10.1016/j.autcon.2021.104010",
    "10.1016/j.ress.2023.109711",
    "10.1016/j.jnlssr.2024.04.001",
}

FIG_RE = re.compile(r"(?im)(?:^|\n)\s*Fig\.\s*(\d+)\s*[.:]\s*([^\n]{0,260})")
TABLE_RE = re.compile(r"(?im)(?:^|\n)\s*Table\s+(\d+)\s*\n?([^\n]{0,220})")


def tidy(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def main() -> None:
    records = json.loads(SOURCE.read_text(encoding="utf-8"), strict=False)
    selected = [r for r in records if str(r.get("doi", "")).lower() in TARGET_DOIS]

    for record in selected:
        path = Path(record["pdf_path"])
        reader = PdfReader(path)
        figures: dict[int, tuple[int, str]] = {}
        tables: dict[int, tuple[int, str]] = {}
        for page_no, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            for number, caption in FIG_RE.findall(text):
                figures.setdefault(int(number), (page_no, tidy(caption)))
            for number, caption in TABLE_RE.findall(text):
                tables.setdefault(int(number), (page_no, tidy(caption)))

        print("=" * 100)
        print(record["title"])
        print(f"DOI: {record.get('doi')} | pages: {len(reader.pages)}")
        print(f"Main figures detected: {len(figures)} | Main tables detected: {len(tables)}")
        print("Figures:")
        for number in sorted(figures):
            page_no, caption = figures[number]
            print(f"  Fig. {number} (PDF page {page_no}): {caption}")
        print("Tables:")
        for number in sorted(tables):
            page_no, caption = tables[number]
            print(f"  Table {number} (PDF page {page_no}): {caption}")


if __name__ == "__main__":
    main()
