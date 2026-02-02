#!/usr/bin/env python3
"""
Comprehensive test script to validate DealInputToSchemaMapper transform output
against the template variables documented in TEMPLATE_VARIABLES_FOR_CLAUDE.md
"""

import json
import sys
from main import DealInputToSchemaMapper

# Required top-level variables from TEMPLATE_VARIABLES_FOR_CLAUDE.md
REQUIRED_TOP_LEVEL_VARS = {
    # Cover & TOC
    "cover": dict,
    "toc": str,
    
    # Deal Facts
    "deal_facts": dict,
    "deal_facts_raw": dict,
    "transaction_overview": dict,
    
    # Loan Terms
    "loan_terms": dict,
    "loan_terms_raw": dict,
    "interest_rate_display": str,
    "origination_fee_display": str,
    "exit_fee_display": str,
    
    # Leverage
    "leverage": dict,
    "leverage_raw": dict,
    "LTC": str,
    "LTV": str,
    
    # Sources & Uses
    "sources_list": list,
    "uses_list": list,
    "sources_total": str,
    "uses_total": str,
    "sources_uses_max_rows": (int, float),
    "sources_and_uses": dict,
    
    # Capital Stack
    "capital_stack_sources": list,
    "capital_stack_uses": list,
    "capital_stack_total": str,
    "capital_stack_title": str,
    "capital_stack": dict,
    
    # Sponsor
    "sponsor_table": list,
    "sponsors": list,
    "sponsor": dict,
    
    # Loan Issues
    "loan_issues_income_producing": list,
    "loan_issues_development": list,
    "loan_issues_disclosure": str,
    "loan_issues": dict,
    
    # Collaborative Ventures
    "collaborative_ventures_list": list,
    "collaborative_ventures_disclosure": str,
    "collaborative_ventures": dict,
    
    # Closing Disbursement
    "closing_disbursement": dict,
    "disbursement_payoff": str,
    "disbursement_broker_fee": str,
    "disbursement_origination_fee": str,
    "disbursement_closing_costs": str,
    "disbursement_lender_legal": str,
    "disbursement_borrower_legal": str,
    "disbursement_misc": str,
    "disbursement_interest_reserve": str,
    "disbursement_total": str,
    "disbursement_sponsor_equity": str,
    "disbursement_fairbridge_release": str,
    "disbursement_rows": list,
    
    # Due Diligence
    "due_diligence": dict,
    
    # Property & Valuation
    "property_overview": dict,
    "property_overview_narrative": str,
    "property_value": dict,
    "property": dict,
    
    # Location & Market
    "location_overview": dict,
    "market_overview": dict,
    "location": dict,
    "market": dict,
    
    # Narratives
    "narratives": dict,
    "exit_strategy": dict,
    "foreclosure_assumptions": dict,
    "active_litigation": dict,
    
    # Other Sections
    "sections": dict,
    "deal_highlights": dict,
    "risks_and_mitigants": dict,
    "validation_flags": dict,
    "third_party_reports": dict,
    "foreclosure_analysis": dict,
    "zoning_entitlements": dict,
    
    # Financial Information (from recent additions)
    "financial_information": dict,
    "equity_partner": (str, dict),
}

# Required sections within sections dict
REQUIRED_SECTIONS = [
    "transaction_overview",
    "executive_summary",
    "sources_and_uses",
    "loan_terms",
    "property",
    "litigation",
    "location",
    "market",
    "sponsorship",
    "third_party_reports",
    "financial_analysis",
    "exit_strategy",
    "zoning_entitlements",
    "foreclosure_analysis",
    "risks_and_mitigants",
    "deal_highlights",
    "due_diligence",
    "validation_flags",
]

def check_type(value, expected_type):
    """Check if value matches expected type(s)."""
    if expected_type is None:
        return True
    if isinstance(expected_type, tuple):
        return isinstance(value, expected_type)
    return isinstance(value, expected_type)

def test_transform(payload_file: str):
    """Load payload and test transform output against template doc requirements."""
    print(f"Loading payload from {payload_file}...")
    with open(payload_file, 'r') as f:
        data = json.load(f)
    
    # Handle array format
    if isinstance(data, list) and len(data) > 0:
        deal = data[0]
    elif isinstance(data, dict):
        deal = data
    else:
        raise ValueError("Payload must be a dict or array with one deal object")
    
    print("Creating mapper...")
    mapper = DealInputToSchemaMapper(deal)
    
    print("Running transform...")
    output = mapper.transform()
    
    print("\n" + "="*60)
    print("TESTING AGAINST TEMPLATE_VARIABLES_FOR_CLAUDE.md")
    print("="*60)
    
    # Test top-level variables
    print("\n=== Testing Required Top-Level Variables ===")
    missing_vars = []
    wrong_type_vars = []
    
    for var_name, expected_type in REQUIRED_TOP_LEVEL_VARS.items():
        if var_name not in output:
            missing_vars.append(var_name)
            print(f"❌ MISSING: {var_name}")
        else:
            value = output[var_name]
            if not check_type(value, expected_type):
                wrong_type_vars.append((var_name, type(value).__name__, expected_type))
                print(f"⚠️  WRONG TYPE: {var_name} (got {type(value).__name__}, expected {expected_type})")
            else:
                print(f"✅ {var_name} ({type(value).__name__})")
    
    # Test sections
    print("\n=== Testing Required Sections ===")
    sections = output.get("sections", {})
    missing_sections = []
    
    for section in REQUIRED_SECTIONS:
        if section not in sections:
            missing_sections.append(section)
            print(f"❌ MISSING section: {section}")
        else:
            print(f"✅ Found section: {section}")
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    total_issues = len(missing_vars) + len(wrong_type_vars) + len(missing_sections)
    
    if missing_vars:
        print(f"\n❌ Missing {len(missing_vars)} variables:")
        for var in missing_vars:
            print(f"   - {var}")
    
    if wrong_type_vars:
        print(f"\n⚠️  {len(wrong_type_vars)} variables have wrong type:")
        for var, got, expected in wrong_type_vars:
            print(f"   - {var}: got {got}, expected {expected}")
    
    if missing_sections:
        print(f"\n❌ Missing {len(missing_sections)} sections:")
        for section in missing_sections:
            print(f"   - {section}")
    
    if total_issues == 0:
        print("\n✅ PASSED: All required variables and sections present with correct types")
        return True
    else:
        print(f"\n❌ FAILED: {total_issues} issue(s) found")
        return False

if __name__ == "__main__":
    payload_file = sys.argv[1] if len(sys.argv) > 1 else "full_payload_broward.json"
    success = test_transform(payload_file)
    sys.exit(0 if success else 1)
