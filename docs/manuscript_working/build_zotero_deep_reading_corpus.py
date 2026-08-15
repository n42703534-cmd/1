from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "manuscript_working" / "27_zotero_deep_reading_corpus.json"
BASE_URL = "http://127.0.0.1:23119/api/users/0"


SELECTED_ITEMS = {
    "R9KTTSQW": "core_framework",
    "XPJBUP4M": "core_framework",
    "GMHF8A6K": "core_framework",
    "ZXT3LHCP": "core_framework",
    "NVCRI2G2": "core_framework",
    "KJBRNNEI": "core_framework",
    "RSGBKACX": "core_framework",
    "I5B7WA9Q": "core_framework",
    "75BAPU3J": "transfer_fire_validation",
    "RQGYAQX6": "actual_station_experiment",
    "CIV5EXIW": "agent_based_station_capacity",
    "FBRLJGRA": "simulation_time_analysis",
    "6NC6D3ZJ": "guided_path_planning",
    "BPQDMNCP": "prediction_based_route_choice",
    "JNCRY9Q9": "facility_service_chain",
    "KKYAMMMM": "node_queueing_dta",
    "RT65SAGN": "dynamic_network_loading",
    "T2QCZLYD": "crowd_prediction_control",
    "UYB3DIHS": "astar_method_support",
    "2XRWJ6M7": "astar_method_support",
    "PJ2XRQ3A": "robust_dynamic_flow_support",
    "HHECV3AK": "improved_astar_parameter_source",
}


SECTION_PATTERNS = {
    "abstract": re.compile(r"\bA\s*B\s*S\s*T\s*R\s*A\s*C\s*T\b|\bAbstract\b", re.I),
    "introduction": re.compile(r"^\s*1\.?\s+Introduction\b", re.I | re.M),
    "literature": re.compile(r"^\s*(2|3)?\.?\s*(Related research|Related work|Literature review)\b", re.I | re.M),
    "model_method": re.compile(
        r"^\s*\d+(\.\d+)?\.?\s+(The proposed model|Model|Methods?|Methodology|Framework|Passenger flow|Evacuation simulation|Path planning|Route choice)\b",
        re.I | re.M,
    ),
    "solving": re.compile(r"^\s*\d+(\.\d+)?\.?\s+(Solving|Solution|Model solving|Algorithm|Optimization)\b", re.I | re.M),
    "case_results": re.compile(r"^\s*\d+(\.\d+)?\.?\s+(Case study|Results?|Experiments?|Numerical example|Simulation)\b", re.I | re.M),
    "conclusion": re.compile(r"^\s*\d+\.?\s+Conclusions?\b", re.I | re.M),
}


def api_get(path: str):
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        headers={"Zotero-API-Version": "3"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def file_url_to_path(file_url: str) -> Path | None:
    if not file_url.startswith("file:///"):
        return None
    parsed = urllib.parse.urlparse(file_url)
    return Path(urllib.parse.unquote(parsed.path).lstrip("/"))


def get_file_url(attachment_key: str) -> str | None:
    try:
        return api_get(f"/items/{urllib.parse.quote(attachment_key)}/file/view/url")
    except Exception:
        return None


def summarize_creators(creators):
    names = []
    for creator in creators or []:
        if "name" in creator:
            names.append(creator["name"])
        else:
            first = creator.get("firstName", "")
            last = creator.get("lastName", "")
            names.append(" ".join([first, last]).strip())
    return [name for name in names if name]


def year_from_date(date_value: str | None):
    if not date_value:
        return None
    match = re.search(r"(19|20)\d{2}", date_value)
    return match.group(0) if match else None


def clean_text(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf(path: Path):
    doc = fitz.open(path)
    pages = []
    all_text_parts = []
    for index, page in enumerate(doc):
        text = clean_text(page.get_text())
        pages.append(
            {
                "pdf_page": index + 1,
                "character_count": len(text),
                "text": text[:7000],
            }
        )
        all_text_parts.append(f"\n\n[[PAGE {index + 1}]]\n{text}")
    full_text = "\n".join(all_text_parts)
    headings = []
    for line in full_text.splitlines():
        stripped = line.strip()
        if re.match(r"^(\d+(\.\d+)*\.?\s+|[A-Z][A-Za-z ]{2,45}$)", stripped):
            if 4 <= len(stripped) <= 120:
                headings.append(stripped)
    headings = list(dict.fromkeys(headings))[:80]

    snippets = {}
    for label, pattern in SECTION_PATTERNS.items():
        match = pattern.search(full_text)
        if not match:
            snippets[label] = ""
            continue
        start = match.start()
        snippets[label] = clean_text(full_text[start : start + 2600])

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "source_path": str(path),
        "source_sha256": digest,
        "page_count": doc.page_count,
        "heading_candidates": headings,
        "section_snippets": snippets,
        "first_pages": pages[:3],
    }


def attachment_paths_for_item(item_key: str):
    paths = []
    try:
        item = api_get(f"/items/{urllib.parse.quote(item_key)}")
    except Exception:
        item = None
    if item and item.get("data", {}).get("itemType") == "attachment":
        url = get_file_url(item_key)
        path = file_url_to_path(url or "")
        if path and path.exists() and path.suffix.lower() == ".pdf":
            paths.append(path)
        return paths

    try:
        children = api_get(f"/items/{urllib.parse.quote(item_key)}/children")
    except Exception:
        children = []
    for child in children:
        if child.get("data", {}).get("itemType") != "attachment":
            continue
        child_key = child.get("key")
        url = get_file_url(child_key)
        path = file_url_to_path(url or "")
        if path and path.exists() and path.suffix.lower() == ".pdf":
            paths.append(path)
    return paths


def read_item(item_key: str, role: str):
    try:
        item = api_get(f"/items/{urllib.parse.quote(item_key)}")
        data = item.get("data", {})
    except Exception:
        data = {
            "itemType": "attachment",
            "title": "基于改进A*算法的多层邮轮疏散系统仿真_蒙盾",
            "creators": [],
            "date": None,
        }
    paths = attachment_paths_for_item(item_key)
    pdf = extract_pdf(paths[0]) if paths else None
    return {
        "item_key": item_key,
        "role": role,
        "item_type": data.get("itemType"),
        "title": data.get("title"),
        "creators": summarize_creators(data.get("creators")),
        "year": year_from_date(data.get("date") or data.get("accessDate")),
        "publication": data.get("publicationTitle"),
        "doi": data.get("DOI"),
        "abstract_note": clean_text(data.get("abstractNote") or ""),
        "pdf": pdf,
    }


def main():
    records = [read_item(key, role) for key, role in SELECTED_ITEMS.items()]
    OUT.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "source": "Zotero local API and local PDF attachments",
                "record_count": len(records),
                "records": records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(str(OUT))
    print(f"records={len(records)}")


if __name__ == "__main__":
    main()
