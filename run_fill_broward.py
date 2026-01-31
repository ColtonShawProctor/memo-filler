#!/usr/bin/env python3
"""
One-off: load the broward deal JSON (paste or path), fill the FB template, write output.
Run from repo root. Edit DEAL_JSON_PATH or paste JSON into broward_blvd_deal.json first.
"""
import json
import sys
from pathlib import Path

# Ensure we can import main
sys.path.insert(0, str(Path(__file__).resolve().parent))
from main import DealInputToSchemaMapper, fill_template

TEMPLATE_PATH = Path("/Users/crus/Downloads/FB Deal Memo_Template.docx")
DEAL_JSON_PATH = Path(__file__).parent / "broward_blvd_deal.json"
OUTPUT_PATH = Path(__file__).parent / "Deal_Memo_broward-blvd.docx"


def main():
    if not TEMPLATE_PATH.exists():
        print(f"Template not found: {TEMPLATE_PATH}")
        print("Set TEMPLATE_PATH in this script or put template at that path.")
        sys.exit(1)

    if DEAL_JSON_PATH.exists():
        with open(DEAL_JSON_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    else:
        print("No broward_blvd_deal.json found. Create it with your deal JSON (array of one deal).")
        sys.exit(1)

    deal = raw[0] if isinstance(raw, list) else raw
    schema_data = DealInputToSchemaMapper(deal).transform()
    template_bytes = TEMPLATE_PATH.read_bytes()
    filled_bytes = fill_template(template_bytes, schema_data, {})
    OUTPUT_PATH.write_bytes(filled_bytes)
    print(f"Wrote {OUTPUT_PATH} ({len(filled_bytes)} bytes)")


if __name__ == "__main__":
    main()
