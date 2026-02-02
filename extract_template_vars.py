#!/usr/bin/env python3
"""
Extract template variables from a Word template file and compare with our schema output.
"""

import sys
from docxtpl import DocxTemplate
from io import BytesIO

def extract_template_variables(template_path: str):
    """Extract all template variables from a .docx template."""
    print(f"Loading template: {template_path}")
    try:
        with open(template_path, 'rb') as f:
            template_bytes = f.read()
        
        template_stream = BytesIO(template_bytes)
        doc = DocxTemplate(template_stream)
        variables = doc.get_undeclared_template_variables()
        
        print(f"\nFound {len(variables)} template variables:")
        print("=" * 60)
        
        # Sort for easier reading
        sorted_vars = sorted(variables)
        for var in sorted_vars:
            print(f"  - {var}")
        
        return set(variables)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return set()

if __name__ == "__main__":
    template_file = sys.argv[1] if len(sys.argv) > 1 else "FB_Deal_Memo_Template.docx"
    extract_template_variables(template_file)
