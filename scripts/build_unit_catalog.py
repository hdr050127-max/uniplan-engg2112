"""Extract a local code/title index from Sydney's published CSP unit list.

This is a build-time task. The student input app never requests catalogue data
while a student types. The CSP list is broad but is not asserted to contain
every University unit or to prove that a unit runs in a particular session.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pypdf import PdfReader


SOURCE_URL = (
    "https://www.sydney.edu.au/content/dam/corporate/documents/study/"
    "fees-and-costs/2026-unit-of-study-csp-fees.pdf"
)
ROW_RE = re.compile(r"(?m)^([A-Z]{4}\d{4}) (.+?) (\d{6}) \d+\.\d+")


def extract_catalogue(pdf_path: Path) -> dict[str, str]:
    units: dict[str, str] = {}
    for page in PdfReader(str(pdf_path)).pages:
        for match in ROW_RE.finditer(page.extract_text() or ""):
            code, title = match.group(1), " ".join(match.group(2).split())
            if code in units and units[code] != title:
                raise ValueError(f"Conflicting titles for {code}")
            units[code] = title
    if len(units) < 1000:
        raise ValueError(f"Only {len(units)} units parsed; check the source layout")
    return units


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--output-dir", type=Path, default=Path("data/catalog"))
    parser.add_argument("--source-url", default=SOURCE_URL)
    args = parser.parse_args()
    if args.year != 2026 and args.source_url == SOURCE_URL:
        parser.error("Pass --source-url when building a catalogue for another year")
    units = extract_catalogue(args.pdf)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / f"units_{args.year}_csp.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("unit_code", "unit_name"))
        writer.writerows(sorted(units.items()))
    metadata = {
        "catalog_year": args.year,
        "source_url": args.source_url,
        "source_scope": f"{args.year} Commonwealth Supported Place units; not all university units",
        "retrieved_at": datetime.now(ZoneInfo("Australia/Sydney")).isoformat(timespec="seconds"),
        "unit_count": len(units),
    }
    meta_path = args.output_dir / f"units_{args.year}_csp_meta.json"
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(units)} units to {csv_path}")


if __name__ == "__main__":
    main()
