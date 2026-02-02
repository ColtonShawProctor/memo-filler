#!/usr/bin/env python3
"""
Test transform output against actual template variables extracted from template.docx
"""

import json
import sys
from docxtpl import DocxTemplate
from io import BytesIO
from main import DealInputToSchemaMapper

def extract_template_variables(template_path: str):
    """Extract all template variables from a .docx template."""
    with open(template_path, 'rb') as f:
        template_bytes = f.read()
    template_stream = BytesIO(template_bytes)
    doc = DocxTemplate(template_stream)
    return set(doc.get_undeclared_template_variables())

def test_against_template(payload_file: str, template_file: str):
    """Test transform output against actual template variables."""
    print(f"Loading template: {template_file}")
    template_vars = extract_template_variables(template_file)
    print(f"Found {len(template_vars)} variables in template\n")
    
    print(f"Loading payload: {payload_file}")
    with open(payload_file, 'r') as f:
        data = json.load(f)
    
    if isinstance(data, list) and len(data) > 0:
        deal = data[0]
    elif isinstance(data, dict):
        deal = data
    else:
        raise ValueError("Payload must be a dict or array with one deal object")
    
    print("Running transform...")
    mapper = DealInputToSchemaMapper(deal)
    output = mapper.transform()
    
    # Get top-level keys only (template expects dicts, not flattened keys)
    output_keys = set(output.keys())
    
    print("\n" + "="*60)
    print("COMPARING TEMPLATE VARIABLES vs TRANSFORM OUTPUT")
    print("="*60)
    
    # Variables template expects but we don't provide
    missing_in_output = template_vars - output_keys
    # Variables we provide but template doesn't use (informational)
    extra_in_output = output_keys - template_vars
    
    print(f"\n❌ Template variables NOT in output ({len(missing_in_output)}):")
    for var in sorted(missing_in_output):
        print(f"   - {var}")
    
    if extra_in_output:
        print(f"\nℹ️  Output variables NOT in template ({len(extra_in_output)}):")
        for var in sorted(list(extra_in_output)[:20]):  # Show first 20
            print(f"   - {var}")
        if len(extra_in_output) > 20:
            print(f"   ... and {len(extra_in_output) - 20} more")
    
    # Check for common aliases
    print("\n" + "="*60)
    print("CHECKING FOR COMMON ALIASES")
    print("="*60)
    
    alias_checks = {
        "financial_info": "financial_information",
        "financial_information": "financial_info",
    }
    
    for template_var, possible_alias in alias_checks.items():
        if template_var in missing_in_output and possible_alias in output_keys:
            print(f"⚠️  Template uses '{template_var}' but we provide '{possible_alias}'")
    
    print("\n" + "="*60)
    if missing_in_output:
        print(f"❌ FAILED: {len(missing_in_output)} template variables missing from output")
        return False
    else:
        print("✅ PASSED: All template variables present in output")
        return True

if __name__ == "__main__":
    payload_file = sys.argv[1] if len(sys.argv) > 1 else "full_payload_broward.json"
    template_file = sys.argv[2] if len(sys.argv) > 2 else "FB_Deal_Memo_Template.docx"
    success = test_against_template(payload_file, template_file)
    sys.exit(0 if success else 1)
