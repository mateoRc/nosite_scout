"""Lead export format parsing and writers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from .constants import LEAD_COLUMNS

try:
    import pandas as pd
except ModuleNotFoundError:
    pd = None


def parse_formats(raw: str) -> list[str]:
    formats = [part.strip().lower() for part in raw.split(",") if part.strip()]
    allowed = {"csv", "json", "xlsx", "xml"}
    if "all" in formats:
        if len(formats) > 1:
            raise ValueError("Use 'all' by itself, not mixed with other formats")
        return ["csv", "json", "xlsx", "xml"]
    invalid = sorted(set(formats) - allowed)
    if invalid:
        raise ValueError(f"Unsupported export format(s): {', '.join(invalid)}")
    return formats or ["csv"]


def export_xml(rows: list[dict[str, Any]], path: Path) -> None:
    root = ET.Element("leads")
    for row in rows:
        element = ET.SubElement(root, "lead")
        for key in LEAD_COLUMNS:
            child = ET.SubElement(element, key)
            child.text = "" if row.get(key) is None else str(row[key])
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def export_rows(rows: list[dict[str, Any]], formats: list[str], out_dir: str) -> list[Path]:
    if pd is None:
        raise RuntimeError("pandas is required for exports. Run: pip install -r requirements.txt")
    output_dir = Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    frame = pd.DataFrame(rows, columns=LEAD_COLUMNS)
    paths = []
    for format_name in formats:
        path = output_dir / f"nosite_scout_{timestamp}.{format_name}"
        if format_name == "csv":
            frame.to_csv(path, index=False)
        elif format_name == "json":
            frame.to_json(path, orient="records", indent=2, force_ascii=False)
        elif format_name == "xlsx":
            frame.to_excel(path, index=False, engine="openpyxl")
        elif format_name == "xml":
            export_xml(rows, path)
        paths.append(path)
    return paths
