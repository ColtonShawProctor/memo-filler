#!/usr/bin/env python3
"""
Fill Fairbridge Deal Memo template locally (no S3).

Reads deal JSON and template .docx from disk, uses DealInputToSchemaMapper
and docxtpl to produce a filled memo.

Usage:
  python fill_local.py --template "/Users/crus/Downloads/FB Deal Memo_Template.docx" --input broward_blvd_deal.json --output Deal_Memo_broward-blvd.docx
  python fill_local.py --template "/path/to/template.docx" --input deals.json [--deal-index 0] [--output out.docx]
"""

import argparse
import json
import sys
from pathlib import Path

# Use mapper and fill from main (no S3 calls)
from main import DealInputToSchemaMapper, fill_template


def main():
    p = argparse.ArgumentParser(description="Fill FB Deal Memo template from local JSON and template file.")
    p.add_argument("--template", "-t", required=True, help="Path to .docx template")
    p.add_argument("--input", "-i", default=None, help="Path to JSON file, or '-' for stdin (array of deal objects or single deal)")
    p.add_argument("--output", "-o", default=None, help="Output .docx path (default: Deal_Memo_<deal_id>.docx)")
    p.add_argument("--deal-index", type=int, default=0, help="Index of deal in array (default 0)")
    args = p.parse_args()

    template_path = Path(args.template)
    if not template_path.exists():
        print(f"Error: Template not found: {template_path}", file=sys.stderr)
        sys.exit(1)

    if args.input == "-" or args.input is None:
        raw = json.load(sys.stdin)
    else:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"Error: Input JSON not found: {input_path}", file=sys.stderr)
            sys.exit(1)
        with open(input_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

    if isinstance(raw, list):
        if not raw:
            print("Error: JSON array is empty", file=sys.stderr)
            sys.exit(1)
        deal = raw[args.deal_index]
    elif isinstance(raw, dict) and raw.get("deal_id") is not None:
        deal = raw
    else:
        print("Error: JSON must be a deal object (with deal_id) or array of deal objects", file=sys.stderr)
        sys.exit(1)

    deal_id = deal.get("deal_id", "deal")
    output_path = Path(args.output) if args.output else Path(f"Deal_Memo_{deal_id}.docx")

    mapper = DealInputToSchemaMapper(deal)
    schema_data = mapper.transform()

    template_bytes = template_path.read_bytes()
    filled_bytes = fill_template(template_bytes, schema_data, {})

    output_path.write_bytes(filled_bytes)
    print(f"Wrote {len(filled_bytes)} bytes to {output_path.absolute()}")


if __name__ == "__main__":
    main()
