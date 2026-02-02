"""
Memo Filler Service - Fairbridge Deal Memo Generator

FastAPI service that fills Word templates using Jinja2/docxtpl engine.
Designed for complex templates with loops, conditionals, and nested data.

NEW in v2.0: Direct Layer 2 → Deal Memo endpoint (/fill-from-layer2)

Version: 2.0.0
"""

import os
import re
import base64
from copy import deepcopy
from io import BytesIO
from typing import Dict, Any, Optional, List
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import boto3
from botocore.config import Config
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Inches, Mm
from PIL import Image

app = FastAPI(title="Memo Filler Service", version="2.0.0")

# =============================================================================
# S3 Configuration
# =============================================================================
S3_ENDPOINT = "https://nyc3.digitaloceanspaces.com"
S3_BUCKET = "fam.workspace"
S3_REGION = "nyc3"

s3_client = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
    region_name=S3_REGION,
    config=Config(s3={'addressing_style': 'path'})
)

# =============================================================================
# Image dimension constraints
# =============================================================================
MAX_WIDTH_INCHES = 6.5
MAX_HEIGHT_INCHES = 8.0

IMAGE_WIDTHS = {
    "IMAGE_SOURCES_USES": 6.5,
    "IMAGE_CAPITAL_STACK_CLOSING": 6.5,
    "IMAGE_CAPITAL_STACK_MATURITY": 6.5,
    "IMAGE_LOAN_TO_COST": 6.0,
    "IMAGE_LTV_LTC": 6.0,
    "IMAGE_AERIAL_MAP": 4.5,
    "IMAGE_LOCATION_MAP": 4.5,
    "IMAGE_REGIONAL_MAP": 4.5,
    "IMAGE_SITE_PLAN": 5.5,
    "IMAGE_STREET_VIEW": 5.5,
    "IMAGE_FORECLOSURE_DEFAULT": 6.5,
    "IMAGE_FORECLOSURE_NOTE": 6.5,
}


# =============================================================================
# Helper Functions for Data Processing
# =============================================================================
def escape_jinja_syntax(obj, path="root"):
    """
    Recursively escape Jinja-like syntax in string values to prevent template errors.
    LLM-generated narratives may contain {{ }} which Jinja interprets as variables.
    """
    if isinstance(obj, str):
        if '{{' in obj or '{%' in obj:
            print(f"ESCAPE_JINJA: Found Jinja syntax at {path}: {obj[:100]}...")
        return obj.replace('{{', '{ {').replace('}}', '} }').replace('{%', '{ %').replace('%}', '% }')
    elif isinstance(obj, dict):
        return {k: escape_jinja_syntax(v, f"{path}.{k}") for k, v in obj.items()}
    elif isinstance(obj, list):
        return [escape_jinja_syntax(item, f"{path}[{i}]") for i, item in enumerate(obj)]
    return obj


def parse_currency_to_number(val) -> float:
    """
    Convert currency string like '$35,610,000' to a number.
    Returns 0.0 for None, empty, or unparseable values.
    """
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        # Remove currency symbols, commas, spaces
        cleaned = val.replace('$', '').replace(',', '').replace(' ', '').strip()
        if not cleaned:
            return 0.0
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    return 0.0


# =============================================================================
# Layer 2 to Schema Mapper (Embedded)
# =============================================================================
class Layer2ToSchemaMapper:
    """
    Maps Layer 2 extraction output to the Fairbridge Memo Template schema.
    Handles multiple PFS data structures to capture ALL sponsors.
    """

    def __init__(self, layer2_data: List[Dict[str, Any]]):
        self.raw_data = layer2_data
        self.docs_by_type = self._index_by_document_type()

    def _index_by_document_type(self) -> Dict[str, List[Dict]]:
        index = {}
        for item in self.raw_data:
            dd_name = item.get('dd_name', 'Unknown')
            if dd_name not in index:
                index[dd_name] = []
            index[dd_name].append(item.get('extracted_data', {}))
        return index

    def _get_doc(self, dd_name: str, index: int = 0) -> Dict[str, Any]:
        docs = self.docs_by_type.get(dd_name, [])
        return docs[index] if index < len(docs) else {}

    def _get_all_docs(self, dd_name: str) -> List[Dict[str, Any]]:
        return self.docs_by_type.get(dd_name, [])

    def _format_currency(self, value: Any) -> str:
        if value is None:
            return "N/A"
        try:
            num = float(value)
            if num >= 1_000_000:
                return f"${num/1_000_000:,.2f}M"
            elif num >= 1_000:
                return f"${num:,.0f}"
            else:
                return f"${num:,.2f}"
        except (ValueError, TypeError):
            return str(value)

    def _format_percent(self, value: Any) -> str:
        if value is None:
            return "N/A"
        try:
            return f"{float(value):.2f}%"
        except (ValueError, TypeError):
            return str(value)

    def _safe_get(self, data: Dict, *keys, default=None):
        result = data
        for key in keys:
            if isinstance(result, dict):
                result = result.get(key, default)
            else:
                return default
        return result if result is not None else default

    def _build_cover(self) -> Dict[str, Any]:
        appraisal = self._get_doc('Appraisal')
        prop_details = self._safe_get(appraisal, 'property_details', default={})
        address = self._safe_get(prop_details, 'address', default={})

        property_name = self._safe_get(prop_details, 'property_name', default='')
        street = self._safe_get(address, 'street', default='')
        city = self._safe_get(address, 'city', default='')
        state = self._safe_get(address, 'state', default='')
        zip_code = self._safe_get(address, 'zip', default='')
        full_address = f"{street}, {city}, {state} {zip_code}".strip(', ')

        return {
            "memo_subtitle": "CREDIT COMMITTEE MEMO",
            "memo_title": "BRIDGE LOAN REQUEST",
            "property_name": property_name,
            "property_address": full_address,
            "credit_committee": [
                "Tony Balbo, Partner",
                "Keith Konon, Partner",
                "Greg Halajian, CFO"
            ],
            "underwriting_team": ["Colton Proctor, Associate"],
            "memo_date": datetime.now().strftime("%B %d, %Y")
        }

    def _build_transaction_overview(self) -> Dict[str, Any]:
        appraisal = self._get_doc('Appraisal')
        term_sheet = self._get_doc('Term Sheet')

        prop_details = self._safe_get(appraisal, 'property_details', default={})
        valuation = self._safe_get(appraisal, 'valuation_summary', default={})
        loan_terms = self._safe_get(term_sheet, 'loan_terms', default={})
        improvements = self._safe_get(prop_details, 'improvements', default={})
        land_area = self._safe_get(prop_details, 'land_area', default={})

        market_values = self._safe_get(valuation, 'market_value_conclusions', default=[])
        as_is_value = None
        stabilized_value = None
        for mv in market_values:
            if 'As Is' in mv.get('appraisal_premise', ''):
                as_is_value = mv.get('value_conclusion')
            if 'Stabilized' in mv.get('appraisal_premise', ''):
                stabilized_value = mv.get('value_conclusion')

        loan_amount = self._safe_get(loan_terms, 'loan_amount', default='')
        loan_amount_num = None
        if isinstance(loan_amount, str):
            match = re.search(r'\$?([\d,]+)', loan_amount)
            if match:
                loan_amount_num = int(match.group(1).replace(',', ''))
        elif isinstance(loan_amount, (int, float)):
            loan_amount_num = loan_amount

        ltv = None
        if loan_amount_num and as_is_value:
            ltv = (loan_amount_num / as_is_value) * 100

        gla = self._safe_get(improvements, 'gross_leasable_area_sf')
        gla_str = f"{gla:,} SF" if isinstance(gla, (int, float)) else "N/A"

        return {
            "deal_facts": [
                {"label": "Property Type", "value": self._safe_get(prop_details, 'property_type', default='Retail')},
                {"label": "Property Name", "value": self._safe_get(prop_details, 'property_name', default='')},
                {"label": "Location", "value": f"{self._safe_get(prop_details, 'address', 'city', default='')}, {self._safe_get(prop_details, 'address', 'state', default='')}"},
                {"label": "Land Area", "value": f"{self._safe_get(land_area, 'acres', default='N/A')} acres"},
                {"label": "Building SF", "value": gla_str},
                {"label": "Year Built", "value": str(self._safe_get(improvements, 'year_built', default='N/A'))},
                {"label": "Occupancy", "value": self._format_percent(self._safe_get(prop_details, 'occupancy', 'current_occupancy_percent'))},
            ],
            "loan_terms": [
                {"label": "Loan Amount", "value": self._format_currency(loan_amount_num)},
                {"label": "Term", "value": f"{self._safe_get(loan_terms, 'term_months', default='N/A')} months"},
                {"label": "Amortization", "value": self._safe_get(loan_terms, 'amortization', default='Interest Only')},
                {"label": "Extension", "value": f"{self._safe_get(loan_terms, 'extension_option', 'count', default='1')}x {self._safe_get(loan_terms, 'extension_option', 'term_months', default='6')}-month"},
                {"label": "Origination Fee", "value": self._safe_get(loan_terms, 'origination_fee', default='1.00%')},
                {"label": "Exit Fee", "value": self._safe_get(loan_terms, 'exit_fee', default='1.00%')},
            ],
            "leverage_metrics": [
                {"label": "As-Is Value", "value": self._format_currency(as_is_value)},
                {"label": "Stabilized Value", "value": self._format_currency(stabilized_value)},
                {"label": "Loan-to-Value (As-Is)", "value": self._format_percent(ltv) if ltv else "N/A"},
                {"label": "Loan Amount", "value": self._format_currency(loan_amount_num)},
            ]
        }

    def _build_executive_summary(self) -> Dict[str, Any]:
        appraisal = self._get_doc('Appraisal')
        prop_details = self._safe_get(appraisal, 'property_details', default={})
        redevelopment = self._safe_get(appraisal, 'redevelopment_plan', default={})

        property_name = self._safe_get(prop_details, 'property_name', default='the property')
        city = self._safe_get(prop_details, 'address', 'city', default='')
        state = self._safe_get(prop_details, 'address', 'state', default='')
        gla = self._safe_get(prop_details, 'improvements', 'gross_leasable_area_sf', default=0)

        narrative = f"Fairbridge is being asked to provide a bridge loan secured by {property_name}, "
        narrative += f"a {gla:,} SF retail center located in {city}, {state}. "
        if redevelopment.get('description'):
            narrative += f"\n\nThe business plan involves: {redevelopment['description']}"

        key_highlights = [
            f"Property: {property_name}",
            f"Location: {city}, {state}",
            f"GLA: {gla:,} SF" if gla else "GLA: See appraisal",
        ]
        occupancy = self._safe_get(prop_details, 'occupancy', 'current_occupancy_percent')
        if occupancy:
            key_highlights.append(f"Current Occupancy: {occupancy}%")

        return {
            "narrative": narrative,
            "key_highlights": key_highlights,
            "recommendation": "APPROVE - Subject to conditions",
            "conditions": [
                "Standard closing conditions",
                "Satisfactory title and survey review",
                "Completion of legal documentation"
            ]
        }

    def _build_sources_and_uses(self) -> Dict[str, Any]:
        sources_uses_docs = self._get_all_docs('Sources & Uses')
        sources = []
        uses = []

        for doc in sources_uses_docs:
            if 'sources' in doc:
                for item in doc.get('sources', []):
                    sources.append({
                        "label": item.get('description', item.get('label', 'Source')),
                        "amount": self._format_currency(item.get('amount')),
                        "percent": self._format_percent(item.get('percentage', item.get('percent')))
                    })
            if 'uses' in doc:
                for item in doc.get('uses', []):
                    uses.append({
                        "label": item.get('description', item.get('label', 'Use')),
                        "amount": self._format_currency(item.get('amount')),
                        "release_conditions": item.get('release_conditions', item.get('notes', ''))
                    })

        return {
            "fairbridge_sources_uses": {
                "sources": sources if sources else [{"label": "TBD", "amount": "TBD", "percent": "TBD"}],
                "uses": uses if uses else [{"label": "TBD", "amount": "TBD", "release_conditions": "TBD"}]
            }
        }

    def _build_property(self) -> Dict[str, Any]:
        appraisal = self._get_doc('Appraisal')
        prop_details = self._safe_get(appraisal, 'property_details', default={})
        improvements = self._safe_get(prop_details, 'improvements', default={})
        land_area = self._safe_get(prop_details, 'land_area', default={})

        gla = self._safe_get(improvements, 'gross_leasable_area_sf', default='N/A')
        gla_str = f"{gla:,}" if isinstance(gla, (int, float)) else gla

        narrative = f"The subject property is {self._safe_get(prop_details, 'property_name', default='a retail center')} "
        narrative += f"located at {self._safe_get(prop_details, 'address', 'street', default='')}. "
        narrative += f"The property consists of {self._safe_get(improvements, 'number_of_buildings', default='multiple')} buildings "
        narrative += f"totaling {gla_str} SF of gross leasable area "
        narrative += f"on approximately {self._safe_get(land_area, 'acres', default='N/A')} acres."

        land_sf = self._safe_get(land_area, 'square_feet')
        land_str = f"{self._safe_get(land_area, 'acres', default='N/A')} acres"
        if isinstance(land_sf, (int, float)):
            land_str += f" ({land_sf:,} SF)"

        metrics = [
            {"label": "Property Name", "value": self._safe_get(prop_details, 'property_name', default='N/A')},
            {"label": "Property Type", "value": self._safe_get(prop_details, 'property_type', default='Retail')},
            {"label": "Land Area", "value": land_str},
            {"label": "Gross Leasable Area", "value": f"{gla_str} SF"},
            {"label": "Number of Buildings", "value": str(self._safe_get(improvements, 'number_of_buildings', default='N/A'))},
            {"label": "Year Built", "value": str(self._safe_get(improvements, 'year_built', default='N/A'))},
            {"label": "Year Renovated", "value": str(self._safe_get(improvements, 'year_renovated', default='N/A'))},
            {"label": "Condition", "value": self._safe_get(improvements, 'condition', default='N/A')},
            {"label": "Current Occupancy", "value": self._format_percent(self._safe_get(prop_details, 'occupancy', 'current_occupancy_percent'))},
            {"label": "Stabilized Occupancy", "value": self._format_percent(self._safe_get(prop_details, 'occupancy', 'stabilized_occupancy_percent'))},
        ]

        anchors = self._safe_get(prop_details, 'anchor_tenants', default=[])
        if anchors:
            metrics.append({"label": "Anchor Tenants", "value": ", ".join(anchors[:5])})

        return {"description_narrative": narrative, "metrics": metrics}

    def _build_location(self) -> Dict[str, Any]:
        appraisal = self._get_doc('Appraisal')
        prop_details = self._safe_get(appraisal, 'property_details', default={})
        address = self._safe_get(prop_details, 'address', default={})

        city = address.get('city', '')
        county = address.get('county', '')
        state = address.get('state', '')

        narrative = f"The property is located in {city}, {county}, {state}. "
        narrative += "The area benefits from strong demographics and accessibility. "
        narrative += "Please refer to the appraisal for detailed location analysis."

        return {"narrative": narrative}

    def _build_market(self) -> Dict[str, Any]:
        return {
            "narrative": "Market analysis indicates favorable conditions for the subject property type. "
                        "Please refer to the appraisal for detailed market analysis including "
                        "comparable sales, rental comparables, and market trends."
        }

    def _build_sponsorship(self) -> Dict[str, Any]:
        """
        CRITICAL: Captures ALL sponsors with full financial details.
        Handles multiple PFS data structures.
        """
        pfs_docs = self._get_all_docs('PFS')
        sreo_docs = self._get_all_docs('SREO')

        sponsors = []
        seen_names = set()
        financial_summary = []

        for pfs in pfs_docs:
            name = None

            # Pattern 1: principals array (Steve Hudson's format)
            principals = self._safe_get(pfs, 'principals', default=[])
            if principals and isinstance(principals, list):
                for principal in principals:
                    if isinstance(principal, dict):
                        name = principal.get('name', '')
                        if name and 'Hudson' in name:
                            break

            # Pattern 2: signer_information (Charles Ladd's format)
            if not name:
                name = self._safe_get(pfs, 'signer_information', 'name', default='')

            # Pattern 3: personal_financial_statement.personal_info
            if not name:
                name = self._safe_get(pfs, 'personal_financial_statement', 'personal_info', 'name', default='')

            # Pattern 4: direct name field
            if not name:
                name = pfs.get('name', pfs.get('individual_name', ''))

            if not name:
                continue

            # Normalize for deduplication
            name_key = name.lower().replace(',', '').replace('.', '').replace('jr', '').strip()
            if name_key in seen_names:
                continue
            seen_names.add(name_key)

            # Extract financial data
            financial = self._safe_get(pfs, 'financial_summary', default={})
            assets = self._safe_get(financial, 'assets', default={})
            total_assets = assets.get('total_assets', 0)

            liabilities_section = self._safe_get(financial, 'liabilities_and_net_worth', default={})
            liabilities = self._safe_get(liabilities_section, 'liabilities', default={})
            total_liabilities = liabilities.get('total_liabilities', 0)
            if not total_liabilities:
                total_liabilities = self._safe_get(financial, 'liabilities', 'total_liabilities', default=0)

            net_worth = liabilities_section.get('net_worth', 0)
            if not net_worth and total_assets:
                net_worth = total_assets - (total_liabilities or 0)

            # Extract liquidity
            cash = assets.get('cash_and_cash_equivalents', 0)
            if not cash:
                for item in assets.get('items', []):
                    if 'cash' in item.get('asset_type', '').lower():
                        cash = item.get('value', 0)
                        break

            securities = assets.get('marketable_securities', 0)
            if not securities:
                for item in assets.get('items', []):
                    if 'securities' in item.get('asset_type', '').lower() and 'listed' in item.get('asset_type', '').lower():
                        securities = item.get('value', 0)
                        break

            liquidity = (cash or 0) + (securities or 0)

            if total_assets or net_worth:
                sponsors.append({
                    "name": name,
                    "total_assets": total_assets,
                    "net_worth": net_worth,
                    "liquidity": liquidity,
                    "cash": cash,
                    "securities": securities
                })

                financial_summary.append({"label": f"{name} - Total Assets", "value": self._format_currency(total_assets)})
                financial_summary.append({"label": f"{name} - Net Worth", "value": self._format_currency(net_worth)})
                financial_summary.append({"label": f"{name} - Cash & Securities", "value": self._format_currency(liquidity)})

        # Fallback to FB Underwriting/Term Sheet if no PFS data
        if not sponsors:
            for doc in self._get_all_docs('FB Underwriting') + self._get_all_docs('Term Sheet'):
                sponsorship = self._safe_get(doc, 'sponsorship', default={})
                guarantors = self._safe_get(sponsorship, 'guarantors', default={})
                if guarantors:
                    names = guarantors.get('names', [])
                    combined_nw = guarantors.get('combined_net_worth', 0)
                    combined_cash = guarantors.get('combined_cash_position', 0)
                    combined_securities = guarantors.get('combined_securities_holdings', 0)

                    for name in names:
                        sponsors.append({"name": name, "total_assets": None, "net_worth": None, "liquidity": None})

                    financial_summary.append({"label": "Combined Net Worth (Guarantors)", "value": self._format_currency(combined_nw)})
                    financial_summary.append({"label": "Combined Liquidity", "value": self._format_currency((combined_cash or 0) + (combined_securities or 0))})
                    break

        # Calculate combined totals (use parse_currency_to_number to handle string values)
        combined_net_worth = sum(parse_currency_to_number(s.get('net_worth')) for s in sponsors)
        combined_liquidity = sum(parse_currency_to_number(s.get('liquidity')) for s in sponsors)

        if sponsors and combined_net_worth > 0:
            financial_summary.insert(0, {"label": "COMBINED NET WORTH", "value": self._format_currency(combined_net_worth)})
            financial_summary.insert(1, {"label": "COMBINED LIQUIDITY", "value": self._format_currency(combined_liquidity)})

        # Build overview narrative
        sponsor_names = [s['name'] for s in sponsors]
        if sponsor_names:
            overview = f"The principals on this transaction are {' and '.join(sponsor_names)}. "
            overview += f"Combined net worth of the guarantors is {self._format_currency(combined_net_worth)} "
            overview += f"with combined liquidity of {self._format_currency(combined_liquidity)}."
        else:
            overview = "Sponsor information to be completed."

        # Build track record from SREO
        track_record = []
        for sreo in sreo_docs:
            properties = self._safe_get(sreo, 'properties', default=[])
            for prop in properties:
                property_name = prop.get('property_name', prop.get('name', ''))
                if not property_name or property_name == 'N/A':
                    continue
                outcome = prop.get('status', '')
                if not outcome:
                    disposition = prop.get('disposition', {})
                    outcome = disposition.get('status', 'Active') if isinstance(disposition, dict) else 'Active'
                track_record.append({"property": property_name, "role": prop.get('role', 'Principal'), "outcome": outcome})
                if len(track_record) >= 10:
                    break
            if len(track_record) >= 10:
                break

        if not track_record:
            track_record.append({"property": "See SREO for details", "role": "Principal", "outcome": "Various"})

        return {
            "overview_narrative": overview,
            "financial_summary": financial_summary if financial_summary else [{"label": "TBD", "value": "TBD"}],
            "track_record": track_record,
            "_sponsors_detail": sponsors
        }

    def _build_risks_and_mitigants(self) -> Dict[str, Any]:
        return {
            "overall_risk_score": "MODERATE",
            "recommendation_narrative": "Based on the analysis, this transaction presents acceptable risk levels for Fairbridge. The strong sponsor financials and property fundamentals support the loan request.",
            "risk_items": [
                {"category": "Credit/Sponsor", "score": "Low", "risk": "Sponsor net worth and liquidity meet requirements", "mitigant": "Strong combined financials of guarantors"},
                {"category": "Market", "score": "Moderate", "risk": "Retail market conditions", "mitigant": "Strong location and anchor tenant mix"},
                {"category": "Property", "score": "Moderate", "risk": "Property condition and age", "mitigant": "Recent renovations and ongoing maintenance"},
                {"category": "Exit", "score": "Low", "risk": "Refinance or sale at maturity", "mitigant": "Multiple exit strategies available"}
            ]
        }

    def _build_validation_flags(self) -> Dict[str, Any]:
        checks = {
            "Appraisal": bool(self._get_doc('Appraisal')),
            "Term Sheet": bool(self._get_doc('Term Sheet')),
            "PFS": bool(self._get_all_docs('PFS')),
            "SREO": bool(self._get_all_docs('SREO')),
            "Phase I ESA": bool(self._get_doc('Phase I ESA')),
            "Zoning": bool(self._get_doc('Zoning')),
            "Title": bool(self._get_doc('Title & Survey')),
        }

        total = len(checks)
        passed = sum(1 for v in checks.values() if v)
        critical_flags = []
        warning_flags = []

        for check, available in checks.items():
            if not available:
                if check in ['Appraisal', 'Term Sheet', 'PFS']:
                    critical_flags.append({"rule": f"{check} Required", "message": f"{check} document not found in extraction"})
                else:
                    warning_flags.append({"rule": f"{check} Recommended", "message": f"{check} document not found - verify if required"})

        return {
            "summary": {"total_checks": total, "passed": passed, "warnings": len(warning_flags), "failed": len(critical_flags)},
            "critical_flags": critical_flags,
            "warning_flags": warning_flags
        }

    def _build_third_party_reports(self) -> Dict[str, Any]:
        appraisal = self._get_doc('Appraisal')
        phase1 = self._get_doc('Phase I ESA')

        doc_info = self._safe_get(appraisal, 'document_info', default={})
        appraisers = self._safe_get(appraisal, 'parties', 'appraisers', default=[])
        valuation = self._safe_get(appraisal, 'valuation_summary', 'market_value_conclusions', default=[])

        appraiser_name = appraisers[0].get('name', 'N/A') if appraisers else 'N/A'

        as_is_value = None
        stabilized_value = None
        for mv in valuation:
            if 'As Is' in mv.get('appraisal_premise', ''):
                as_is_value = mv.get('value_conclusion')
            if 'Stabilized' in mv.get('appraisal_premise', ''):
                stabilized_value = mv.get('value_conclusion')

        phase1_info = self._safe_get(phase1, 'report_info', default={})
        phase1_findings = self._safe_get(phase1, 'findings', default={})

        return {
            "appraisal": {
                "firm": self._safe_get(doc_info, 'company_name', default='CBRE'),
                "appraiser": appraiser_name,
                "effective_date": self._safe_get(doc_info, 'date_of_report', default='N/A'),
                "as_is_value": self._format_currency(as_is_value),
                "stabilized_value": self._format_currency(stabilized_value),
                "cap_rate": "See appraisal"
            },
            "environmental": {
                "firm": self._safe_get(phase1_info, 'firm', self._safe_get(phase1_info, 'preparer', default='N/A')),
                "report_date": self._safe_get(phase1_info, 'date', default='N/A'),
                "current_recs": str(len(self._safe_get(phase1_findings, 'recommendations', default=[]))),
                "phase_ii_required": "No" if not self._safe_get(phase1_findings, 'phase_ii_required') else "Yes",
                "findings": self._safe_get(phase1_findings, 'summary', default='No significant findings.')
            }
        }

    def _build_zoning_entitlements(self) -> Dict[str, Any]:
        zoning = self._get_doc('Zoning')
        appraisal = self._get_doc('Appraisal')
        current_zoning = self._safe_get(zoning, 'current_zoning',
                         self._safe_get(appraisal, 'zoning', 'current_zoning', default='N/A'))

        return {
            "summary_narrative": "The property's zoning is consistent with its current use. Please refer to the zoning report for detailed entitlement analysis.",
            "current_zoning": str(current_zoning),
            "proposed_zoning": "No change proposed",
            "entitlement_status": "Entitled for current use"
        }

    def _build_foreclosure_analysis(self) -> Dict[str, Any]:
        default_rate_rows = []
        note_rate_rows = []
        for q in range(1, 9):
            row = {
                "Quarter": f"Q{q}",
                "Beginning_Balance": "TBD",
                "Legal_Fees": "TBD",
                "Taxes": "TBD",
                "Insurance": "TBD",
                "Total_Carrying_Costs": "TBD",
                "Interest_Accrued": "TBD",
                "Ending_Balance": "TBD",
                "Property_Value": "TBD",
                "LTV": "TBD"
            }
            default_rate_rows.append(row.copy())
            note_rate_rows.append(row.copy())

        return {
            "scenario_default_rate": {"rows": default_rate_rows},
            "scenario_note_rate": {"rows": note_rate_rows}
        }

    def transform(self) -> Dict[str, Any]:
        """Transform Layer 2 data to template schema format."""
        return {
            "cover": self._build_cover(),
            "toc": "{{TOC}}",
            "sections": {
                "transaction_overview": self._build_transaction_overview(),
                "executive_summary": self._build_executive_summary(),
                "sources_and_uses": self._build_sources_and_uses(),
                "property": self._build_property(),
                "location": self._build_location(),
                "market": self._build_market(),
                "sponsorship": self._build_sponsorship(),
                "risks_and_mitigants": self._build_risks_and_mitigants(),
                "validation_flags": self._build_validation_flags(),
                "third_party_reports": self._build_third_party_reports(),
                "zoning_entitlements": self._build_zoning_entitlements(),
                "foreclosure_analysis": self._build_foreclosure_analysis()
            }
        }


# =============================================================================
# Deal Input (New Format) → Template Schema Mapper
# =============================================================================
class DealInputToSchemaMapper:
    """
    Maps Layer 3 output (deal JSON with required memo fields) to the
    template schema expected by fill_template(). Input is the exact
    Layer 3 output: deal_id, cover, deal_facts, loan_terms, sponsor,
    narratives, etc.
    """

    def __init__(self, deal: Dict[str, Any]):
        self.deal = deal
        self._cover = deal.get("cover") or {}
        self._property = deal.get("property") or {}
        self._deal_facts = deal.get("deal_facts") or {}
        self._loan_terms = deal.get("loan_terms") or {}
        self._leverage = deal.get("leverage") or {}
        self._closing_disbursement = deal.get("closing_disbursement") or {}
        self._sponsor = deal.get("sponsor") or {}
        print(f"DEBUG DealInputToSchemaMapper.__init__: deal keys = {list(deal.keys())}")
        print(f"DEBUG: self._sponsor = {self._sponsor}")
        print(f"DEBUG: self._sponsor.get('name') = {self._sponsor.get('name')}")
        print(f"DEBUG: self._sponsor.get('guarantors') = {self._sponsor.get('guarantors')}")
        self._sources_uses = deal.get("sources_and_uses") or {}
        self._valuation = deal.get("valuation") or {}
        self._narratives = deal.get("narratives") or {}
        self._risks = deal.get("risks_and_mitigants") or {}
        self._highlights = deal.get("deal_highlights") or {}
        self._due_diligence = deal.get("due_diligence") or {}
        self._environmental = deal.get("environmental") or {}
        self._zoning = deal.get("zoning") or {}
        self._normalize_from_layer3_shape()

    def _normalize_from_layer3_shape(self) -> None:
        """If flat keys are empty, try Layer 3 alternate structure (deal_memo_ready, extracted_data, etc.)."""
        deal = self.deal
        memo = deal.get("deal_memo_ready") or {}
        extracted = deal.get("extracted_data") or {}
        if not self._deal_facts:
            self._deal_facts = memo.get("deal_facts_table") or {}
        if not self._leverage:
            self._leverage = memo.get("leverage_ratios_table") or deal.get("calculations", {}).get("leverage_ratios") or {}
        if not self._loan_terms:
            lt = extracted.get("loan_terms") or {}
            self._loan_terms = lt.get("data") if isinstance(lt.get("data"), dict) else (lt or {})
        if not self._closing_disbursement:
            self._closing_disbursement = memo.get("closing_disbursement") or deal.get("closing_disbursement") or {}
        if not self._cover and (deal.get("deal_identification") or memo):
            di = deal.get("deal_identification") or {}
            self._cover = {
                "property_address": di.get("property_address", ""),
                "credit_committee": di.get("sponsor_names") or di.get("credit_committee", ""),
                "underwriting_team": di.get("underwriting_team", ""),
                "date": di.get("date", "") or (memo.get("memo_date") if isinstance(memo.get("memo_date"), str) else ""),
            }
        if not self._property and memo:
            ps = memo.get("property_summary") or {}
            if isinstance(ps, dict):
                self._property = {
                    "name": ps.get("property_name") or ps.get("project_name", ""),
                    "address": {"street": ps.get("address", ""), "city": ps.get("city", ""), "state": ps.get("state", ""), "zip": ps.get("zip", "")},
                    "property_type": ps.get("property_type", ""),
                    "building_sf": ps.get("gla") or ps.get("gross_leasable_area_sf"),
                    "land_area_acres": ps.get("site_size_acres") or ps.get("land_area_acres"),
                    "year_built": ps.get("year_built"),
                    "occupancy_current": ps.get("occupancy"),
                }
        placeholders = memo.get("narrative_placeholders") or {}
        if not self._narratives and placeholders:
            self._narratives = {
                "property_overview": placeholders.get("property_description") or placeholders.get("property_overview", ""),
                "location_overview": placeholders.get("location_overview", ""),
                "market_overview": placeholders.get("market_overview", ""),
                "transaction_overview": placeholders.get("deal_summary", ""),
                "sponsor_narrative": placeholders.get("sponsor_summary", ""),
                "closing_funding_narrative": placeholders.get("closing_funding_narrative", ""),
            }
        elif self._narratives and placeholders:
            # Fill in missing narrative keys from Layer 3 narrative_placeholders
            if not (self._narratives.get("property_overview") or "").strip() or (self._narratives.get("property_overview") or "").strip() == "None":
                self._narratives["property_overview"] = placeholders.get("property_description") or placeholders.get("property_overview", "") or ""

    def _fmt_currency(self, val: Any) -> str:
        if val is None:
            return "N/A"
        if isinstance(val, str) and val.startswith("$"):
            return val
        try:
            num = float(val)
            if num >= 1_000_000:
                return f"${num/1_000_000:,.2f}M"
            return f"${num:,.0f}"
        except (ValueError, TypeError):
            return str(val)

    def _fmt_pct(self, val: Any) -> str:
        if val is None:
            return "N/A"
        if isinstance(val, str) and "%" in val:
            return val
        try:
            return f"{float(val):.2f}%"
        except (ValueError, TypeError):
            return str(val)

    def _split_list(self, s: str) -> List[str]:
        if not s:
            return []
        return [x.strip() for x in str(s).split(",") if x.strip()]

    def _str_or_empty(self, val: Any) -> str:
        """Return empty string for None; otherwise str(val). Ensures template never shows 'None'."""
        if val is None:
            return ""
        return str(val)

    def _strip_markdown(self, text: str) -> str:
        """Remove markdown formatting from text."""
        if not isinstance(text, str):
            return str(text) if text else ""
        # Remove headers (# ## ###)
        text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
        # Remove bold/italic markers
        text = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', text)
        text = re.sub(r'_{1,2}([^_]+)_{1,2}', r'\1', text)
        # Remove escaped characters
        text = text.replace('\\#', '#').replace('\\*', '*').replace('\\_', '_')
        # Clean up extra whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _build_cover(self) -> Dict[str, Any]:
        addr = self._property.get("address") or {}
        prop_name = self._str_or_empty(self._property.get("name"))
        return {
            "memo_subtitle": "CREDIT COMMITTEE MEMO",
            "memo_title": "BRIDGE LOAN REQUEST",
            "property_name": prop_name,
            "property_address": self._str_or_empty(self._cover.get("property_address")),
            "credit_committee": self._split_list(self._cover.get("credit_committee") or ""),
            "underwriting_team": self._split_list(self._cover.get("underwriting_team") or ""),
            "memo_date": self._str_or_empty(self._cover.get("date")) or datetime.now().strftime("%B %d, %Y"),
        }

    def _build_transaction_overview(self) -> Dict[str, Any]:
        ir_raw = self._loan_terms.get("interest_rate")
        ir = ir_raw if isinstance(ir_raw, dict) else {}
        if isinstance(ir_raw, str):
            ir = {"description": ir_raw, "default_rate": ""}
        deal_facts = [
            {"label": "Property Type", "value": self._str_or_empty(self._deal_facts.get("property_type")) or "N/A"},
            {"label": "Property Name", "value": self._str_or_empty(self._property.get("name")) or "N/A"},
            {"label": "Loan Purpose", "value": self._str_or_empty(self._deal_facts.get("loan_purpose")) or "N/A"},
            {"label": "Loan Amount", "value": self._str_or_empty(self._deal_facts.get("loan_amount")) or "N/A"},
            {"label": "Source", "value": self._str_or_empty(self._deal_facts.get("source")) or "N/A"},
        ]
        loan_terms_list = [
            {"label": "Interest Rate", "value": self._str_or_empty(ir.get("description")) or "N/A"},
            {"label": "Origination Fee", "value": self._str_or_empty(self._loan_terms.get("origination_fee")) or "N/A"},
            {"label": "Exit Fee", "value": self._str_or_empty(self._loan_terms.get("exit_fee")) or "N/A"},
            {"label": "Prepayment", "value": self._str_or_empty(self._loan_terms.get("prepayment")) or "N/A"},
            {"label": "Guaranty", "value": self._str_or_empty(self._loan_terms.get("guaranty")) or "N/A"},
        ]
        lev = self._leverage
        leverage_list = [
            {"label": "LTC at Closing", "value": self._str_or_empty(lev.get("fb_ltc_at_closing") or lev.get("ltc_at_closing")) or "N/A"},
            {"label": "LTV at Closing", "value": self._str_or_empty(lev.get("ltv_at_closing")) or "N/A"},
            {"label": "LTV at Maturity", "value": self._str_or_empty(lev.get("ltv_at_maturity")) or "N/A"},
            {"label": "Debt Yield", "value": self._str_or_empty(lev.get("debt_yield_fully_drawn") or lev.get("debt_yield")) or "N/A"},
        ]
        return {
            "deal_facts": deal_facts,
            "loan_terms": loan_terms_list,
            "leverage_metrics": leverage_list,
        }

    def _build_executive_summary(self) -> Dict[str, Any]:
        narrative = self._narratives.get("transaction_overview") or ""
        if not narrative:
            narrative = f"Bridge loan request for {self._property.get('name') or 'the property'}. See narratives for full overview."
        narrative = (narrative or "")[:4000] if isinstance(narrative, str) else str(narrative or "")[:4000]
        items = (self._highlights.get("items") or [])[:6]
        key_highlights = [self._str_or_empty(h.get("highlight") or h.get("description")) for h in items if isinstance(h, dict)]
        return {
            "narrative": narrative,
            "transaction_overview": narrative,
            "key_highlights": key_highlights or ["See deal highlights."],
            "recommendation": "APPROVE - Subject to conditions",
            "conditions": ["Standard closing conditions", "Satisfactory title and survey review", "Completion of legal documentation"],
        }

    def _build_sources_and_uses(self) -> Dict[str, Any]:
        table = self._sources_uses.get("table") or {}
        if not isinstance(table, dict):
            table = {}
        total_sources = table.get("total_sources") or 0
        try:
            total_sources = float(total_sources)
        except (TypeError, ValueError):
            total_sources = 0
        sources = []
        for item in (table.get("sources") or []):
            if not isinstance(item, dict):
                continue
            raw_amount = item.get("amount")
            if total_sources and raw_amount is not None:
                try:
                    pct = (float(raw_amount) / total_sources) * 100
                    percent = f"{pct:.1f}%"
                except (TypeError, ValueError):
                    percent = self._fmt_pct(item.get("rate_pct"))
            else:
                percent = self._fmt_pct(item.get("rate_pct"))
            sources.append({
                "label": item.get("label") or item.get("item") or "Source",
                "amount": self._fmt_currency(raw_amount),
                "percent": percent,
            })
        uses = []
        for cat in (table.get("uses") or []):
            if not isinstance(cat, dict):
                continue
            for item in (cat.get("items") or []):
                if not isinstance(item, dict):
                    continue
                uses.append({
                    "label": item.get("label") or item.get("item") or "Use",
                    "amount": self._fmt_currency(item.get("amount")),
                    "release_conditions": cat.get("category", ""),
                })
        return {
            "fairbridge_sources_uses": {
                "sources": sources if sources else [{"label": "TBD", "amount": "TBD", "percent": "TBD"}],
                "uses": uses if uses else [{"label": "TBD", "amount": "TBD", "release_conditions": "TBD"}],
            }
        }

    def _build_property(self) -> Dict[str, Any]:
        addr = self._property.get("address") or {}
        if not isinstance(addr, dict):
            addr = {}
        narrative = self._narratives.get("property_overview") or ""
        if narrative is None or (isinstance(narrative, str) and narrative.strip() == "None"):
            narrative = ""
        if not narrative:
            narrative = f"{self._property.get('name') or 'The property'} is located at {addr.get('street', '')}, {addr.get('city', '')}, {addr.get('state', '')}. {self._property.get('building_sf') or 'N/A'} SF, {self._property.get('land_area_acres') or 'N/A'} acres."
        yb = self._property.get("year_built")
        year_built_str = str(yb) if yb is not None else "N/A"
        if isinstance(yb, list):
            year_built_str = ", ".join(str(x) for x in yb)
        bsf = self._property.get("building_sf")
        bsf_str = f"{bsf:,} SF" if isinstance(bsf, (int, float)) else str(bsf) if bsf is not None else "N/A"
        metrics = [
            {"label": "Property Name", "value": self._property.get("name", "N/A")},
            {"label": "Property Type", "value": self._property.get("property_type", "N/A")},
            {"label": "Land Area", "value": f"{self._property.get('land_area_acres', 'N/A')} acres"},
            {"label": "Building SF", "value": bsf_str},
            {"label": "Year Built", "value": year_built_str},
            {"label": "Year Renovated", "value": str(self._property.get("year_renovated", "N/A"))},
            {"label": "Condition", "value": self._property.get("condition", "N/A")},
            {"label": "Current Occupancy", "value": f"{self._property.get('occupancy_current', 'N/A')}%" if self._property.get("occupancy_current") is not None else "N/A"},
            {"label": "Stabilized Occupancy", "value": f"{self._property.get('occupancy_stabilized', 'N/A')}%" if self._property.get("occupancy_stabilized") is not None else "N/A"},
            {"label": "Anchor Tenants", "value": self._property.get("anchor_tenants", "N/A")},
        ]
        desc = (narrative or "")[:5000] if isinstance(narrative, str) else str(narrative or "")[:5000]
        if desc == "None":
            desc = ""
        return {"description_narrative": desc, "metrics": metrics}

    def _build_location(self) -> Dict[str, Any]:
        narrative = self._narratives.get("location_overview") or ""
        if not narrative:
            addr = self._property.get("address") or {}
            narrative = f"The property is located in {addr.get('city', '')}, {addr.get('county', '')}, {addr.get('state', '')}. See appraisal for detailed location analysis."
        return {"narrative": (narrative or "")[:4000] if isinstance(narrative, str) else str(narrative or "")[:4000]}

    def _build_market(self) -> Dict[str, Any]:
        narrative = self._narratives.get("market_overview") or ""
        if not narrative:
            narrative = "Market analysis indicates favorable conditions. Please refer to the appraisal for detailed market analysis."
        return {"narrative": (narrative or "")[:4000] if isinstance(narrative, str) else str(narrative or "")[:4000]}

    def _build_sponsorship(self) -> Dict[str, Any]:
        print(f"DEBUG _build_sponsorship: self._sponsor = {self._sponsor}")
        print(f"DEBUG _build_sponsorship: self._sponsor.get('name') = {self._sponsor.get('name')}")
        guarantors = self._sponsor.get("guarantors") or {}
        print(f"DEBUG _build_sponsorship: guarantors = {guarantors}")
        print(f"DEBUG _build_sponsorship: guarantors.get('names') = {guarantors.get('names')}")
        principals = (self._sponsor.get("principals") or [])
        sponsors = []
        for name in (guarantors.get("names") or []):
            sponsors.append({
                "name": name,
                "total_assets": None,
                "net_worth": guarantors.get("combined_net_worth"),
                "liquidity": (guarantors.get("combined_cash_position") or 0) + (guarantors.get("combined_securities_holdings") or 0),
                "cash": guarantors.get("combined_cash_position"),
                "securities": guarantors.get("combined_securities_holdings"),
            })
        if not sponsors and principals:
            for p in principals:
                if not isinstance(p, dict):
                    continue
                name = p.get("name", "")
                if not name:
                    continue
                fp = p.get("financial_profile") or {}
                if not isinstance(fp, dict):
                    fp = {}
                nw = fp.get("net_worth")
                liq = fp.get("liquid_assets")
                sponsors.append({"name": name, "total_assets": None, "net_worth": nw, "liquidity": liq, "cash": liq, "securities": None})
        # Use parse_currency_to_number to handle currency strings like "$35,610,000"
        combined_nw = sum(parse_currency_to_number(s.get("net_worth")) for s in sponsors)
        combined_liq = sum(parse_currency_to_number(s.get("liquidity")) for s in sponsors)
        financial_summary = [
            {"label": "COMBINED NET WORTH", "value": self._fmt_currency(guarantors.get("combined_net_worth") or combined_nw)},
            {"label": "COMBINED LIQUIDITY", "value": self._fmt_currency(combined_liq)},
        ]
        for s in sponsors:
            financial_summary.append({"label": f"{s['name']} - Net Worth", "value": self._fmt_currency(s.get("net_worth"))})
            financial_summary.append({"label": f"{s['name']} - Liquidity", "value": self._fmt_currency(s.get("liquidity"))})
        overview = self._narratives.get("sponsor_narrative", "")
        if not overview:
            overview = f"The principals are {', '.join(s['name'] for s in sponsors)}. Combined net worth {self._fmt_currency(combined_nw)}, liquidity {self._fmt_currency(combined_liq)}."
        # Use pre-computed name from Layer 3 if available; otherwise derive from guarantors
        sponsor_display_name = self._sponsor.get("name")
        if not sponsor_display_name:
            sponsor_names = guarantors.get("names", [])
            sponsor_display_name = " & ".join(str(n) for n in sponsor_names) if sponsor_names else ""
        if not sponsor_display_name:
            sponsor_display_name = "See sponsor details"
        print(f"DEBUG _build_sponsorship RETURN: sponsor_display_name = '{sponsor_display_name}'")
        print(f"DEBUG _build_sponsorship RETURN: overview_narrative will be = '{sponsor_display_name if sponsor_display_name else 'FALLBACK'}'")
        return {
            "name": sponsor_display_name,
            "table": self._sponsor.get("table") or [],  # ownership structure table
            "overview": sponsor_display_name,  # Template uses sponsor.overview
            "overview_narrative": sponsor_display_name if sponsor_display_name else (overview[:3000] if isinstance(overview, str) else str(overview)[:3000]),
            "financial_summary": financial_summary if financial_summary else [{"label": "TBD", "value": "TBD"}],
            "track_record": [{"property": "See sponsor narrative", "role": "Principal", "outcome": "Various"}],
            "_sponsors_detail": sponsors if sponsors else [{"name": "TBD", "total_assets": None, "net_worth": None, "liquidity": None}],
        }

    def _build_risks_and_mitigants(self) -> Dict[str, Any]:
        items = (self._risks.get("items") or [])
        risk_items = []
        for r in items:
            if not isinstance(r, dict):
                continue
            risk_items.append({
                "category": r.get("risk", "Risk"),
                "score": "Moderate",
                "risk": r.get("description", ""),
                "mitigant": r.get("mitigant", ""),
            })
        narrative = self._narratives.get("risks_mitigants_narrative") or ""
        risk_list = risk_items if risk_items else [{"category": "General", "score": "Moderate", "risk": "See risks and mitigants.", "mitigant": "See narrative."}]
        return {
            "overall_risk_score": "MODERATE",
            "recommendation_narrative": (narrative or "")[:2000] if narrative else "Based on the analysis, this transaction presents acceptable risk levels for Fairbridge.",
            "risk_items": risk_list,
            "items": risk_list,
        }

    def _build_validation_flags(self) -> Dict[str, Any]:
        return {
            "summary": {"total_checks": 7, "passed": 7, "warnings": 0, "failed": 0},
            "critical_flags": [],
            "warning_flags": [],
        }

    def _build_third_party_reports(self) -> Dict[str, Any]:
        return {
            "appraisal": {
                "firm": self._str_or_empty(self._due_diligence.get("appraisal_company")) or "N/A",
                "appraiser": self._str_or_empty(self._due_diligence.get("appraisal_firm")) or "N/A",
                "effective_date": "N/A",
                "as_is_value": self._str_or_empty(self._valuation.get("as_is_value")) or "N/A",
                "stabilized_value": self._str_or_empty(self._valuation.get("as_stabilized_value")) or "N/A",
                "cap_rate": self._str_or_empty(self._valuation.get("cap_rate")) or "N/A",
            },
            "environmental": {
                "firm": self._str_or_empty(self._environmental.get("firm")) or "N/A",
                "report_date": self._str_or_empty(self._environmental.get("report_date")) or "N/A",
                "current_recs": str(len(self._environmental.get("historical_recs") or [])),
                "phase_ii_required": "No",
                "findings": (self._str_or_empty(self._environmental.get("findings_summary")) or "N/A")[:500],
            },
            "pca": {
                "firm": self._str_or_empty(self._due_diligence.get("pca_firm")) or "N/A",
                "report_date": "N/A",
                "summary": self._str_or_empty(self._narratives.get("pca_narrative")) or "See property condition assessment.",
            },
        }

    def _build_zoning_entitlements(self) -> Dict[str, Any]:
        narrative = self._narratives.get("zoning_narrative") or ""
        if not narrative:
            narrative = f"Current zoning: {self._zoning.get('zone_code') or 'N/A'}. {self._zoning.get('highest_best_use_improved') or ''}"
        return {
            "summary_narrative": (narrative or "")[:3000] if isinstance(narrative, str) else str(narrative or "")[:3000],
            "current_zoning": self._str_or_empty(self._zoning.get("zone_code")) or "N/A",
            "proposed_zoning": "See redevelopment",
            "entitlement_status": "See zoning narrative",
            "exists": bool(self._zoning),
        }

    def _build_foreclosure_analysis(self) -> Dict[str, Any]:
        narrative = self._narratives.get("foreclosure_assumptions") or ""
        rows = [{"Quarter": f"Q{q}", "Beginning_Balance": "TBD", "Legal_Fees": "TBD", "Taxes": "TBD", "Insurance": "TBD", "Total_Carrying_Costs": "TBD", "Interest_Accrued": "TBD", "Ending_Balance": "TBD", "Property_Value": "TBD", "LTV": "TBD"} for q in range(1, 9)]
        return {"scenario_default_rate": {"rows": rows}, "scenario_note_rate": {"rows": rows}}

    def _build_litigation(self) -> Dict[str, Any]:
        """Build litigation section for template. Template expects sections.litigation with has_litigation, narrative, cases."""
        al = self.deal.get("active_litigation") or {}
        if not isinstance(al, dict):
            al = {}

        # Get and normalize cases
        cases_raw = al.get("cases") or []
        if isinstance(cases_raw, dict):
            # Single case object - wrap in array
            cases_raw = [cases_raw]

        # Build normalized cases list with correct field names for template
        cases = []
        for c in cases_raw:
            if not isinstance(c, dict):
                continue
            cases.append({
                "case_name": self._str_or_empty(c.get("case_name") or c.get("case") or ""),
                "background": self._str_or_empty(c.get("background") or c.get("complaint_background") or ""),
                "sponsor_explanation": self._str_or_empty(c.get("sponsor_explanation") or ""),
                "fairbridge_analysis": self._str_or_empty(c.get("fairbridge_analysis") or c.get("fairbridge_counsel_analysis") or ""),
                "holdback": self._str_or_empty(c.get("holdback") or c.get("fairbridge_holdback") or ""),
            })

        has_litigation = al.get("exists", False) or len(cases) > 0
        narrative = self._narratives.get("litigation_narrative") or ""
        if not narrative and has_litigation:
            narrative = f"{len(cases)} active litigation case(s). See details below."
        elif not narrative:
            narrative = "No active litigation identified."

        return {
            "has_litigation": has_litigation,
            "narrative": narrative,
            "cases": cases,
        }

    def _build_capital_stack_flat(self) -> tuple:
        """Flatten capital_stack into (title, sources_list, uses_list) for template iteration."""
        cs = self.deal.get("capital_stack") or {}
        table = cs.get("table") if isinstance(cs.get("table"), dict) else cs
        if not isinstance(table, dict):
            table = {}
        title = self._str_or_empty(table.get("title")) or "Capital Stack at Closing"
        sources_raw = table.get("sources") or []
        sources_list = []
        for item in sources_raw:
            if not isinstance(item, dict):
                continue
            sources_list.append({
                "label": self._str_or_empty(item.get("item") or item.get("label")),
                "amount": self._fmt_currency(item.get("amount")),
                "percent": self._fmt_pct(item.get("rate_pct") or item.get("percent")),
            })
        uses_raw = table.get("uses") or []
        uses_list = []
        for cat in uses_raw:
            if not isinstance(cat, dict):
                continue
            category = self._str_or_empty(cat.get("category"))
            items = cat.get("items") or []
            if not items and (cat.get("item") is not None or cat.get("label") is not None):
                items = [cat]  # flat row: { item, amount } or { label, amount }
            for item in items:
                if not isinstance(item, dict):
                    continue
                uses_list.append({
                    "label": self._str_or_empty(item.get("item") or item.get("label")),
                    "amount": self._fmt_currency(item.get("amount")),
                    "release_conditions": category,
                })
        # If capital_stack has top-level sources/uses (no .table), use those
        if not sources_list and (cs.get("sources") or cs.get("uses")):
            sources_list = [{"label": self._str_or_empty(x.get("item") or x.get("label")), "amount": self._fmt_currency(x.get("amount")), "percent": self._fmt_pct(x.get("rate_pct"))} for x in (cs.get("sources") or []) if isinstance(x, dict)]
            for u in (cs.get("uses") or []):
                if isinstance(u, dict):
                    uses_list.append({"label": self._str_or_empty(u.get("item") or u.get("label")), "amount": self._fmt_currency(u.get("amount")), "release_conditions": self._str_or_empty(u.get("category"))})
        return title, sources_list, uses_list

    def _build_disbursement_rows(self) -> List[Dict[str, str]]:
        """Build list of {label, value} from closing_disbursement for table rendering."""
        cd = self._closing_disbursement or {}
        if not isinstance(cd, dict):
            return []
        labels = [
            ("payoff_existing_debt", "Payoff Existing Debt"),
            ("broker_fee", "Broker Fee"),
            ("origination_fee", "Origination Fee"),
            ("closing_costs_title", "Closing Costs (Title)"),
            ("lender_legal", "Lender Legal"),
            ("borrower_legal", "Borrower Legal"),
            ("misc", "Misc"),
            ("interest_reserve", "Interest Reserve"),
            ("total_disbursements", "Total Disbursements"),
            ("sponsors_equity_at_closing", "Sponsors Equity at Closing"),
            ("fairbridge_release_at_closing", "Fairbridge Release at Closing"),
        ]
        return [{"label": lbl, "value": self._str_or_empty(cd.get(key)) or ""} for key, lbl in labels]

    def transform(self) -> Dict[str, Any]:
        """Transform deal input to template schema format."""
        print("=== Layer 3 Input Debug ===")
        print("deal_facts:", self._deal_facts)
        print("leverage:", self._leverage)
        print("loan_terms keys:", list(self._loan_terms.keys()) if isinstance(self._loan_terms, dict) else self._loan_terms)
        print("closing_disbursement:", self._closing_disbursement)
        print("narratives keys:", list(self._narratives.keys()) if isinstance(self._narratives, dict) else self._narratives)
        out = {
            "cover": self._build_cover(),
            "toc": "{{TOC}}",
            "sections": {
                "transaction_overview": self._build_transaction_overview(),
                "executive_summary": self._build_executive_summary(),
                "sources_and_uses": self._build_sources_and_uses(),
                "property": self._build_property(),
                "location": self._build_location(),
                "market": self._build_market(),
                "sponsorship": self._build_sponsorship(),
                "risks_and_mitigants": self._build_risks_and_mitigants(),
                "validation_flags": self._build_validation_flags(),
                "third_party_reports": self._build_third_party_reports(),
                "zoning_entitlements": self._build_zoning_entitlements(),
                "foreclosure_analysis": self._build_foreclosure_analysis(),
                "litigation": self._build_litigation(),
            },
        }
        li = self.deal.get("loan_issues") or {}
        if li:
            out["loan_issues"] = {
                "income_producing": li.get("income_producing") if isinstance(li.get("income_producing"), list) else (li.get("income_producing") or []),
                "development": li.get("development") if isinstance(li.get("development"), list) else (li.get("development") or []),
            }
        out["loan_issues_income_producing"] = li.get("income_producing") if isinstance(li.get("income_producing"), list) else []
        out["loan_issues_development"] = li.get("development") if isinstance(li.get("development"), list) else []
        out["loan_issues_disclosure"] = li.get("disclosure_statement") or ""

        cv = self.deal.get("collaborative_ventures")
        if isinstance(cv, dict):
            out["collaborative_ventures"] = {"items": cv.get("items") or cv.get("ventures") or list(cv.values()) if cv else []}
        elif isinstance(cv, list):
            out["collaborative_ventures"] = {"items": cv}
        else:
            out["collaborative_ventures"] = {"items": []}
        if isinstance(cv, dict):
            out["collaborative_ventures_list"] = cv.get("items") or cv.get("ventures") or list(cv.values()) or []
            out["collaborative_ventures_disclosure"] = cv.get("disclosure_statement") or ""
        elif isinstance(cv, list):
            out["collaborative_ventures_list"] = cv
            out["collaborative_ventures_disclosure"] = ""
        else:
            out["collaborative_ventures_list"] = []
            out["collaborative_ventures_disclosure"] = ""

        # Flatten capital_stack into iterable arrays for Jinja (avoid raw dict in template)
        cap_title, cap_sources, cap_uses = self._build_capital_stack_flat()
        out["capital_stack_title"] = cap_title
        out["capital_stack_sources"] = cap_sources
        out["capital_stack_uses"] = cap_uses
        out["capital_stack"] = {"title": cap_title, "sources": cap_sources, "uses": cap_uses}

        # === DIRECT TEMPLATE VARIABLES (bypass dict wrapper) ===
        sponsor_rows = self._sponsor.get("table") or []
        normalized_sponsor_table = []
        for row in sponsor_rows:
            if isinstance(row, dict):
                normalized_sponsor_table.append({
                    "entity": row.get("entity") or row.get("name") or row.get("member") or "",
                    "profit_pct": row.get("profit_pct") or row.get("profit_percentage_interest") or row.get("profit_percentage") or "",
                    "membership_interest": row.get("membership_interest") or row.get("membership_units") or "",
                    "capital_interest": row.get("capital_interest") or row.get("capital_contribution") or "",
                    "capital_pct": row.get("capital_pct") or row.get("capital_interest_percentage") or row.get("capital_percentage") or "",
                })
        out["sponsor_table"] = normalized_sponsor_table
        out["sponsors"] = self._sponsor.get("principals") or []

        sources_table = self._sources_uses.get("table") or {}
        out["sources_list"] = sources_table.get("sources") or self._sources_uses.get("sources") or []
        out["uses_list"] = sources_table.get("uses") or self._sources_uses.get("uses") or []
        out["sources_total"] = self._sources_uses.get("total_sources") or self._sources_uses.get("sources_total") or ""
        out["uses_total"] = self._sources_uses.get("total_uses") or self._sources_uses.get("uses_total") or ""
        out["sources_uses_max_rows"] = max(len(out["sources_list"]), len(out["uses_list"]), 1)

        cap_stack = self.deal.get("capital_stack") or {}
        cap_table = cap_stack.get("table") if isinstance(cap_stack.get("table"), dict) else cap_stack
        out["capital_stack_sources"] = (cap_table.get("sources") or cap_stack.get("sources") or []) if isinstance(cap_table, dict) else []
        out["capital_stack_uses"] = (cap_table.get("uses") or cap_stack.get("uses") or []) if isinstance(cap_table, dict) else []
        out["capital_stack_total"] = cap_stack.get("total") or cap_stack.get("sources_total") or ""

        cd = self._closing_disbursement or {}
        out["disbursement_payoff"] = cd.get("payoff_existing_debt") or ""
        out["disbursement_broker_fee"] = cd.get("broker_fee") or ""
        out["disbursement_origination_fee"] = cd.get("origination_fee") or ""
        out["disbursement_closing_costs"] = cd.get("closing_costs_title") or ""
        out["disbursement_lender_legal"] = cd.get("lender_legal") or ""
        out["disbursement_borrower_legal"] = cd.get("borrower_legal") or ""
        out["disbursement_misc"] = cd.get("misc") or ""
        out["disbursement_interest_reserve"] = cd.get("interest_reserve") or ""
        out["disbursement_total"] = cd.get("total_disbursements") or ""
        out["disbursement_sponsor_equity"] = cd.get("sponsors_equity_at_closing") or ""
        out["disbursement_fairbridge_release"] = cd.get("fairbridge_release_at_closing") or ""

        # Clean display values for Deal Facts (not full paragraphs)
        lt = self._loan_terms or {}
        interest_rate_raw = lt.get("interest_rate") or self._deal_facts.get("interest_rate") or ""
        if isinstance(interest_rate_raw, str) and len(interest_rate_raw) > 50:
            match = re.search(r'SOFR\s*\+\s*\d+|[\d.]+%', interest_rate_raw)
            out["interest_rate_display"] = match.group(0) if match else "See Loan Terms"
        else:
            out["interest_rate_display"] = interest_rate_raw or ""

        orig_fee_raw = lt.get("origination_fee") or ""
        if isinstance(orig_fee_raw, str) and len(orig_fee_raw) > 20:
            match = re.search(r'[\d.]+%', orig_fee_raw)
            out["origination_fee_display"] = match.group(0) if match else "See Loan Terms"
        else:
            out["origination_fee_display"] = orig_fee_raw or ""

        exit_fee_raw = lt.get("exit_fee") or ""
        if isinstance(exit_fee_raw, str) and len(exit_fee_raw) > 20:
            match = re.search(r'[\d.]+%', exit_fee_raw)
            out["exit_fee_display"] = match.group(0) if match else "See Loan Terms"
        else:
            out["exit_fee_display"] = exit_fee_raw or ""

        if not isinstance(cd, dict):
            cd = {}
        # Disbursement table: iterable rows + normalized dict (no None -> template shows "" not "None")
        out["disbursement_rows"] = self._build_disbursement_rows()
        out["closing_disbursement"] = {k: self._str_or_empty(v) for k, v in cd.items()}

        for key in ("rent_roll", "construction_budget", "comps", "redevelopment"):
            out[key] = self.deal.get(key) if self.deal.get(key) is not None else {}

        # Due diligence: explicit fields for template, empty string instead of None
        dd = self.deal.get("due_diligence") or {}
        if not isinstance(dd, dict):
            dd = {}
        out["due_diligence"] = {
            "lenders_counsel": self._str_or_empty(dd.get("lenders_counsel")),
            "borrowers_counsel": self._str_or_empty(dd.get("borrowers_counsel")),
            "pca_firm": self._str_or_empty(dd.get("pca_firm")),
            "background_check": self._str_or_empty(dd.get("background_check") or dd.get("background_check_firm")),
            "site_visit": self._str_or_empty(dd.get("site_visit") or dd.get("site_visit_team")),
            "appraisal_firm": self._str_or_empty(dd.get("appraisal_firm")),
            "appraisal_company": self._str_or_empty(dd.get("appraisal_company")),
            "environmental_firm": self._str_or_empty(dd.get("environmental_firm")),
        }

        al = self.deal.get("active_litigation") or {}
        if isinstance(al, dict):
            cases = al.get("cases")
            if isinstance(cases, dict):
                al = {**al, "cases": list(cases.values())}
            elif cases is None:
                al = {**al, "cases": []}
            # Sanitize case fields so template never sees "None"
            cases_list = al.get("cases") or []
            al["cases"] = [{k: self._str_or_empty(v) for k, v in (c.items() if isinstance(c, dict) else {})} for c in cases_list]
        out["active_litigation"] = al

        dh = self.deal.get("deal_highlights") or {}
        out["deal_highlights"] = dict(dh) if isinstance(dh, dict) else {}
        if "items" not in out["deal_highlights"]:
            out["deal_highlights"]["items"] = []
        narrative = self._narratives.get("closing_funding_narrative") or ""
        out["closing_funding_and_reserves"] = {k: self._str_or_empty(v) for k, v in (self._closing_disbursement or {}).items()}
        if narrative:
            out["closing_funding_and_reserves"]["narrative"] = narrative
        lev = self._leverage
        out["LTC"] = lev.get("fb_ltc_at_closing") or lev.get("ltc_at_closing") or lev.get("ltc_at_maturity") or "N/A"
        out["LTV"] = lev.get("ltv_at_closing") or lev.get("ltv_at_maturity") or "N/A"
        out["property_value"] = self._valuation if self._valuation else {}
        exit_narr = self._narratives.get("exit_strategy") or ""
        out["exit_strategy"] = {"narrative": exit_narr} if isinstance(exit_narr, str) else (exit_narr if isinstance(exit_narr, dict) else {"narrative": ""})
        fa_narr = self._narratives.get("foreclosure_assumptions") or ""
        out["foreclosure_assumptions"] = {"narrative": fa_narr} if isinstance(fa_narr, str) else (fa_narr if isinstance(fa_narr, dict) else {"narrative": ""})
        out["narratives"] = {k: self._strip_markdown(v) if isinstance(v, str) else v for k, v in self._narratives.items()}
        if "loan_terms" in out.get("sections", {}):
            lt_section = out["sections"]["loan_terms"]
            if isinstance(lt_section, dict) and "narrative" in lt_section:
                lt_section["narrative"] = self._strip_markdown(lt_section["narrative"])
        # Add raw Layer 3 fields for templates that use direct property access
        # (e.g. {{ deal_facts_raw.property_type }} or {{ property_type }})
        out["deal_facts_raw"] = self._deal_facts
        out["leverage_raw"] = self._leverage
        out["loan_terms_raw"] = dict(self._loan_terms) if self._loan_terms else {}
        # Default missing loan_terms fields so template never shows blank (Layer 3 may not send all keys)
        for key in ("origination_fee", "exit_fee", "prepayment", "guaranty", "collateral"):
            val = out["loan_terms_raw"].get(key)
            if val is None or (isinstance(val, str) and not val.strip()):
                out["loan_terms_raw"][key] = "See Loan Terms narrative"
        for key, val in self._deal_facts.items():
            if key not in out:
                out[key] = val
        for key, val in self._leverage.items():
            if key not in out:
                out[key] = val
        for key, val in (self._loan_terms or {}).items():
            if key not in out:
                out[key] = val

        # Debug logging for empty values
        print("=== Transform Output Debug ===")
        print(f"sponsor_table rows: {len(out.get('sponsor_table', []))}")
        print(f"sources_list rows: {len(out.get('sources_list', []))}")
        print(f"uses_list rows: {len(out.get('uses_list', []))}")
        print(f"capital_stack_sources rows: {len(out.get('capital_stack_sources', []))}")
        print(f"collaborative_ventures_list rows: {len(out.get('collaborative_ventures_list', []))}")
        print(f"loan_issues_income_producing rows: {len(out.get('loan_issues_income_producing', []))}")
        print(f"disbursement_payoff: '{out.get('disbursement_payoff', '')}'")
        if out.get('sponsor_table'):
            print(f"First sponsor row: {out['sponsor_table'][0]}")

        return out


# =============================================================================
# Template (S3 key for FB Deal Memo template)
# =============================================================================
DEFAULT_TEMPLATE_KEY = "_Templates/FB_Deal_Memo_Template.docx"


# =============================================================================
# Request/Response Models
# =============================================================================
class FillRequest(BaseModel):
    data: Dict[str, Any]
    images: Dict[str, str] = {}
    template_key: str = DEFAULT_TEMPLATE_KEY
    output_filename: str = "Deal_Memo_Generated.docx"


class FillAndUploadRequest(BaseModel):
    data: Dict[str, Any]
    images: Dict[str, str] = {}
    template_key: str = DEFAULT_TEMPLATE_KEY
    output_key: str


class FillFromLayer2Request(BaseModel):
    """NEW: Request model for direct Layer 2 → Memo generation."""
    layer2_data: List[Dict[str, Any]]  # Raw Layer 2 extractions array
    images: Dict[str, str] = {}
    template_key: str = DEFAULT_TEMPLATE_KEY
    output_key: str
    deal_folder: str = ""  # Optional deal folder name for logging


class FillFromDealRequest(BaseModel):
    """Request model for deal memo input format (DealInputPayload)."""
    payload: List[Dict[str, Any]]  # Array of deal objects (DealInputPayload)
    deal_index: int = 0  # Which deal in the array to use
    images: Dict[str, str] = {}
    template_key: str = DEFAULT_TEMPLATE_KEY
    output_key: str


class HealthResponse(BaseModel):
    status: str
    version: str
    engine: str


# =============================================================================
# Layer 3 preprocessing (flat variables, markdown stripping, display values)
# =============================================================================
def strip_markdown(text: Optional[str]) -> Optional[str]:
    """Remove markdown formatting from text."""
    if not text:
        return text
    # Remove headers (# ## ### etc)
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    # Remove bold markers (**text** or __text__)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    # Remove italic markers (*text* or _text_)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    # Remove [GENERATED] prefix if present
    text = re.sub(r'^\[GENERATED\]\s*', '', text)
    return text.strip()


def extract_first_line_or_value(value: Any) -> str:
    """If value is a paragraph (multi-line), return first line; else return string value."""
    if value is None:
        return ''
    s = str(value).strip()
    if not s:
        return ''
    first_line = s.split('\n')[0].strip()
    return first_line


def preprocess_layer3_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Preprocess Layer 3 data for template rendering.
    - Pass-through flat variables (sponsor_table, sources_list, etc.) unchanged
    - Strips markdown from narratives
    - Adds display values for Deal Facts
    - Normalizes due_diligence field name (background_check -> background_check_firm)
    """
    result = deepcopy(data)

    # Strip markdown from section narrative fields
    narrative_fields = [
        ('transaction_overview', 'narrative'),
        ('loan_terms', 'narrative'),
        ('property_overview', 'narrative'),
        ('location_overview', 'narrative'),
        ('market_overview', 'narrative'),
        ('zoning_entitlements', 'narrative'),
        ('exit_strategy', 'narrative'),
    ]
    for section, field in narrative_fields:
        if section in result and isinstance(result[section], dict) and field in result[section]:
            result[section] = dict(result[section])
            result[section][field] = strip_markdown(result[section][field])

    # Strip markdown from top-level narrative fields
    for field in ('loan_issues_disclosure', 'collaborative_ventures_disclosure'):
        if field in result and result[field]:
            result[field] = strip_markdown(result[field])

    # Strip markdown from sponsor bios
    for sponsor in result.get('sponsors', []):
        if isinstance(sponsor, dict):
            for key in ('overview', 'financial_profile', 'track_record'):
                if key in sponsor and sponsor[key]:
                    sponsor[key] = strip_markdown(sponsor[key])

    # Add display values for Deal Facts (single-line for template)
    loan_terms = result.get('loan_terms') or {}
    if isinstance(loan_terms, dict):
        ir = loan_terms.get('interest_rate', '')
        result['interest_rate_display'] = extract_first_line_or_value(ir)
        result['origination_fee_display'] = loan_terms.get('origination_fee', '')
        result['exit_fee_display'] = loan_terms.get('exit_fee', '')
        result['term_display'] = loan_terms.get('term', '')
        result['extension_display'] = loan_terms.get('extension_option', '')
    else:
        result['interest_rate_display'] = ''
        result['origination_fee_display'] = ''
        result['exit_fee_display'] = ''
        result['term_display'] = ''
        result['extension_display'] = ''

    # Normalize due_diligence: Layer 3 outputs 'background_check', template may expect 'background_check_firm'
    if 'due_diligence' in result and isinstance(result['due_diligence'], dict):
        dd = result['due_diligence']
        if 'background_check' in dd and 'background_check_firm' not in dd:
            dd['background_check_firm'] = dd['background_check']

    return result


# =============================================================================
# Helper Functions
# =============================================================================
def calculate_image_dimensions(image_bytes: bytes, preferred_width: float) -> tuple[float, float]:
    try:
        image = Image.open(BytesIO(image_bytes))
        original_width, original_height = image.size
        aspect_ratio = original_height / original_width

        width_inches = min(preferred_width, MAX_WIDTH_INCHES)
        height_inches = width_inches * aspect_ratio

        if height_inches > MAX_HEIGHT_INCHES:
            height_inches = MAX_HEIGHT_INCHES
            width_inches = height_inches / aspect_ratio
            if width_inches > MAX_WIDTH_INCHES:
                width_inches = MAX_WIDTH_INCHES
                height_inches = width_inches * aspect_ratio

        return width_inches, height_inches
    except Exception as e:
        print(f"Warning: Could not process image dimensions: {e}")
        return min(preferred_width, MAX_WIDTH_INCHES), min(4.0, MAX_HEIGHT_INCHES)


def download_template(template_key: str) -> bytes:
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=template_key)
        return response['Body'].read()
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Template not found: {template_key} - {str(e)}")


def get_unique_output_key(output_key: str) -> str:
    try:
        s3_client.head_object(Bucket=S3_BUCKET, Key=output_key)
    except:
        return output_key

    base, ext = os.path.splitext(output_key)
    match = re.match(r'(.+)_(\d+)$', base)
    if match:
        base = match.group(1)
        start = int(match.group(2)) + 1
    else:
        start = 2

    for i in range(start, 1000):
        new_key = f"{base}_{i}{ext}"
        try:
            s3_client.head_object(Bucket=S3_BUCKET, Key=new_key)
        except:
            return new_key

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f"{base}_{timestamp}{ext}"


def upload_to_s3(content: bytes, key: str) -> str:
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=content,
            ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        return f"{S3_ENDPOINT}/{S3_BUCKET}/{key}"
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload to S3: {str(e)}")


def prepare_images_for_template(doc: DocxTemplate, images: Dict[str, str]) -> Dict[str, InlineImage]:
    inline_images = {}
    for key, base64_data in images.items():
        try:
            image_bytes = base64.b64decode(base64_data)
            preferred_width = IMAGE_WIDTHS.get(key, 5.0)
            width_inches, height_inches = calculate_image_dimensions(image_bytes, preferred_width)

            image_stream = BytesIO(image_bytes)
            inline_images[key] = InlineImage(doc, image_stream, width=Inches(width_inches), height=Inches(height_inches))
            print(f"Prepared image {key}: {width_inches:.2f}\" x {height_inches:.2f}\"")
        except Exception as e:
            print(f"Warning: Failed to prepare image {key}: {e}")
            continue
    return inline_images


# Template placeholder names that differ from our schema keys. Add aliases here as we find them.
# To get the full list of variables the template expects: GET /template-info?template_key=_Templates/FB_Deal_Memo_Template.docx
TEMPLATE_ALIASES = {
    "leverage": "leverage_metrics",
}


def flatten_schema_for_template(data: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten schema so template can use top-level vars like deal_facts, loan_terms, leverage, narrative."""
    flat = dict(data)
    sections = flat.pop("sections", None) or {}
    for _section_name, section_data in sections.items():
        if isinstance(section_data, dict):
            for k, v in section_data.items():
                if k not in flat:
                    flat[k] = v
    for template_name, schema_key in TEMPLATE_ALIASES.items():
        if template_name not in flat and schema_key in flat:
            flat[template_name] = flat[schema_key]
    if "sponsor" not in flat and "sponsorship" in sections:
        flat["sponsor"] = sections["sponsorship"]
    if "sponsors" not in flat and "sponsorship" in sections:
        flat["sponsors"] = sections["sponsorship"].get("_sponsors_detail") or []
    if "sources_and_uses" not in flat and "sources_and_uses" in sections:
        flat["sources_and_uses"] = sections["sources_and_uses"]
    if "property_overview" not in flat and "property" in sections:
        flat["property_overview"] = sections["property"]
    for section_name in ("zoning_entitlements", "risks_and_mitigants", "third_party_reports", "validation_flags", "foreclosure_analysis", "location", "market"):
        if section_name not in flat and section_name in sections:
            flat[section_name] = sections[section_name]
    if "location_overview" not in flat and "location" in sections:
        flat["location_overview"] = sections["location"]
    if "market_overview" not in flat and "market" in sections:
        flat["market_overview"] = sections["market"]
    if "property_overview_narrative" not in flat and "property" in sections:
        flat["property_overview_narrative"] = sections["property"].get("description_narrative") or ""
    if "financial_info" not in flat and "sponsorship" in sections:
        flat["financial_info"] = sections["sponsorship"].get("financial_summary", [])
    # Template alias: guarantor_financials = financial_summary from sponsorship
    if "guarantor_financials" not in flat and "sponsorship" in sections:
        flat["guarantor_financials"] = sections["sponsorship"].get("financial_summary", [])
    fa = sections.get("foreclosure_analysis") or {}
    def _scenario_with_items(s):
        if not s or not isinstance(s, dict):
            s = {"rows": []}
        rows = s.get("rows") if isinstance(s.get("rows"), list) else []
        return {**s, "rows": rows, "items": rows}
    if "default_interest_scenario" not in flat:
        flat["default_interest_scenario"] = _scenario_with_items(fa.get("scenario_default_rate"))
    if "note_interest_scenario" not in flat:
        flat["note_interest_scenario"] = _scenario_with_items(fa.get("scenario_note_rate"))
    # Keep sections for templates that use sections.* paths (e.g. sections.transaction_overview.deal_facts)
    flat["sections"] = sections
    # If sections.sponsorship.overview_narrative is missing, derive from sponsor name (e.g. "Steve Hudson & Charlie Ladd Jr.")
    if sections.get("sponsorship") and isinstance(sections["sponsorship"], dict):
        if not sections["sponsorship"].get("overview_narrative"):
            sections["sponsorship"]["overview_narrative"] = sections["sponsorship"].get("name", "See Sponsor Details")
    # Spread raw Layer 3 fields for templates that use direct property access (e.g. {{ property_type }}, {{ loan_amount }})
    for raw_key in ("deal_facts_raw", "leverage_raw", "loan_terms_raw"):
        if raw_key in flat and isinstance(flat[raw_key], dict):
            for k, v in flat[raw_key].items():
                if k not in flat:
                    flat[k] = v
    # CRITICAL: Template uses {{ deal_facts.property_type }}, {{ leverage.fb_ltc_at_closing }}, {{ closing_disbursement.payoff_existing_debt }}, etc.
    # These need to be DICTS, not arrays. Override with raw versions so direct property access works.
    if "deal_facts_raw" in flat:
        flat["deal_facts"] = flat["deal_facts_raw"]
    if "leverage_raw" in flat:
        flat["leverage"] = flat["leverage_raw"]
    if "loan_terms_raw" in flat:
        flat["loan_terms"] = flat["loan_terms_raw"]
    # Normalize interest_rate so {{ loan_terms.interest_rate }} renders as text (Layer 3 may send a dict with description/default_rate)
    if "loan_terms" in flat and isinstance(flat["loan_terms"], dict):
        ir = flat["loan_terms"].get("interest_rate")
        if isinstance(ir, dict):
            flat["loan_terms"]["interest_rate"] = ir.get("description", str(ir))
    # Template uses property_overview.narrative, location_overview.narrative, etc.; ensure .narrative alias exists
    if "property_overview" in flat and isinstance(flat["property_overview"], dict):
        if "narrative" not in flat["property_overview"] and "description_narrative" in flat["property_overview"]:
            flat["property_overview"]["narrative"] = flat["property_overview"]["description_narrative"]
    if "loan_terms" in flat and isinstance(flat["loan_terms"], dict):
        lt_narr = flat.get("narratives", {}).get("loan_terms_narrative", "")
        if lt_narr:
            flat["loan_terms"]["narrative"] = lt_narr
    if "zoning_entitlements" in flat and isinstance(flat["zoning_entitlements"], dict):
        if "narrative" not in flat["zoning_entitlements"] and "summary_narrative" in flat["zoning_entitlements"]:
            flat["zoning_entitlements"]["narrative"] = flat["zoning_entitlements"]["summary_narrative"]
    if "active_litigation" in flat and isinstance(flat["active_litigation"], dict):
        if "narrative" not in flat["active_litigation"]:
            cases = flat["active_litigation"].get("cases", [])
            if cases:
                flat["active_litigation"]["narrative"] = f"{len(cases)} active case(s). See details below."
            else:
                flat["active_litigation"]["narrative"] = "No active litigation."
    return flat


class _DictWithItemsList:
    """Wrapper so Jinja 'for x in obj.items' gets a list (template uses .items not .items())."""
    __slots__ = ("_d",)

    def __init__(self, d: dict):
        self._d = dict(d)
        if "items" not in self._d or not isinstance(self._d.get("items"), list):
            self._d["items"] = list(self._d.items())

    def __getitem__(self, k):
        return self._d[k]

    def get(self, k, default=None):
        return self._d.get(k, default)

    def __getattr__(self, k):
        if k == "items":
            return self._d["items"]
        return self._d.get(k)

    def __contains__(self, k):
        return k in self._d

    def __iter__(self):
        return iter(self._d)

    def keys(self):
        return self._d.keys()

    def values(self):
        return self._d.values()


def _ensure_items_on_dicts(obj: Any, seen: Optional[set] = None, root: bool = True) -> None:
    """Recursively ensure every dict (except root) has an 'items' key that is a list (for Jinja .items iteration)."""
    if seen is None:
        seen = set()
    if id(obj) in seen:
        return
    if isinstance(obj, dict):
        seen.add(id(obj))
        for v in obj.values():
            _ensure_items_on_dicts(v, seen, root=False)
        if not root and "items" not in obj:
            obj["items"] = list(obj.items())
    elif isinstance(obj, list):
        for item in obj:
            _ensure_items_on_dicts(item, seen, root=False)


def fill_template(template_bytes: bytes, data: Dict[str, Any], images: Dict[str, str]) -> bytes:
    template_stream = BytesIO(template_bytes)
    doc = DocxTemplate(template_stream)

    inline_images = prepare_images_for_template(doc, images)
    # Flatten sections into root so template placeholders like {{ deal_facts }} work
    flat_data = flatten_schema_for_template(data)
    # Escape any Jinja-like syntax in LLM-generated text to prevent template errors
    flat_data = escape_jinja_syntax(flat_data)
    context = {**flat_data, **inline_images}
    if "images" not in context:
        context["images"] = []
    _ensure_items_on_dicts(context)
    for k, v in list(context.items()):
        if isinstance(v, dict) and not hasattr(v, "_d"):
            context[k] = _DictWithItemsList(v)
    if "sponsors" in context and not isinstance(context["sponsors"], list):
        v = context["sponsors"]
        context["sponsors"] = list(v.values()) if isinstance(v, dict) else (list(v) if hasattr(v, "__iter__") and not isinstance(v, str) else [])
    if "loan_issues" in context and isinstance(context["loan_issues"], dict):
        li = context["loan_issues"]
        for k in ("income_producing", "development"):
            if k in li and li[k] is not None and not isinstance(li[k], list):
                li[k] = []

    try:
        doc.render(context)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Template rendering failed: {str(e)}")

    output = BytesIO()
    doc.save(output)
    output.seek(0)
    return output.getvalue()


# =============================================================================
# API Endpoints
# =============================================================================
@app.get("/health", response_model=HealthResponse)
async def health_check():
    return {"status": "ok", "version": "2.0.0", "engine": "docxtpl"}


@app.post("/fill")
async def fill_template_endpoint(request: FillRequest):
    """Fill template and return as download. Layer 3 flat data is preprocessed (markdown stripped, display values added)."""
    template_bytes = download_template(request.template_key)
    processed_data = preprocess_layer3_data(request.data)
    filled_bytes = fill_template(template_bytes, processed_data, request.images)

    return StreamingResponse(
        BytesIO(filled_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={request.output_filename}"}
    )


@app.post("/fill-and-upload")
async def fill_and_upload_endpoint(request: FillAndUploadRequest):
    """Fill template and upload to S3. Layer 3 flat data is preprocessed (markdown stripped, display values added)."""
    template_bytes = download_template(request.template_key)
    processed_data = preprocess_layer3_data(request.data)
    filled_bytes = fill_template(template_bytes, processed_data, request.images)
    output_key = get_unique_output_key(request.output_key)
    output_url = upload_to_s3(filled_bytes, output_key)

    return {
        "success": True,
        "output_key": output_key,
        "output_url": output_url,
        "original_key": request.output_key
    }


@app.post("/fill-from-layer2")
async def fill_from_layer2_endpoint(request: FillFromLayer2Request):
    """
    NEW ENDPOINT: Direct Layer 2 → Deal Memo generation.

    Takes raw Layer 2 extraction data, transforms it to schema format,
    fills the template, and uploads to S3.

    Request body:
    - layer2_data: Array of extraction objects from Layer 2
    - images: Optional dict of image_key -> base64 encoded image
    - template_key: S3 key for template file (default: v2_0)
    - output_key: S3 key for output file
    - deal_folder: Optional deal folder name for logging

    Returns:
    - success: bool
    - output_key: Actual S3 key used
    - output_url: Full URL to the uploaded file
    - sponsors_found: Number of sponsors captured
    - sponsor_names: List of sponsor names found
    """
    print(f"Processing Layer 2 data for deal: {request.deal_folder}")
    print(f"Layer 2 items received: {len(request.layer2_data)}")

    # Step 1: Transform Layer 2 to schema
    mapper = Layer2ToSchemaMapper(request.layer2_data)
    schema_data = mapper.transform()

    # Log sponsor capture for verification
    sponsors = schema_data.get('sections', {}).get('sponsorship', {}).get('_sponsors_detail', [])
    sponsor_names = [s['name'] for s in sponsors]
    print(f"Sponsors captured: {sponsor_names}")

    # Step 2: Download template
    template_bytes = download_template(request.template_key)

    # Step 3: Fill template
    filled_bytes = fill_template(template_bytes, schema_data, request.images)

    # Step 4: Upload to S3
    output_key = get_unique_output_key(request.output_key)
    output_url = upload_to_s3(filled_bytes, output_key)

    return {
        "success": True,
        "output_key": output_key,
        "output_url": output_url,
        "original_key": request.output_key,
        "sponsors_found": len(sponsors),
        "sponsor_names": sponsor_names,
        "template_used": request.template_key
    }


def _run_fill_from_deal(
    payload: List[Dict[str, Any]],
    deal_index: int,
    output_key: str,
    template_key: str = DEFAULT_TEMPLATE_KEY,
    images: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Shared logic for fill-from-deal: (1) pull template from S3, (2) map Layer 3 input to schema, (3) fill template, (4) upload result to S3."""
    if not payload:
        raise HTTPException(status_code=400, detail="payload must be a non-empty array of deal objects")
    if deal_index < 0 or deal_index >= len(payload):
        raise HTTPException(status_code=400, detail=f"deal_index must be between 0 and {len(payload) - 1}")
    deal = payload[deal_index]
    deal_id = deal.get("deal_id", "")
    deal_folder = deal.get("deal_folder", "")
    print(f"Processing deal input: deal_id={deal_id}, deal_folder={deal_folder}")

    mapper = DealInputToSchemaMapper(deal)
    schema_data = mapper.transform()

    sponsors = schema_data.get("sections", {}).get("sponsorship", {}).get("_sponsors_detail", [])
    sponsor_names = [s.get("name", "") for s in sponsors]
    print(f"Sponsors captured: {sponsor_names}")

    # 1. Pull template from S3
    try:
        template_bytes = download_template(template_key)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to pull template from S3 ({template_key}): {str(e)}")
    # 2. Fill template with schema (Layer 3 input mapped to template variables)
    try:
        filled_bytes = fill_template(template_bytes, schema_data, images or {})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Template render failed: {str(e)}")
    # 3. Upload filled memo to S3
    try:
        out_key = get_unique_output_key(output_key)
        output_url = upload_to_s3(filled_bytes, out_key)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to upload filled memo to S3: {str(e)}")

    return {
        "success": True,
        "output_key": out_key,
        "output_url": output_url,
        "original_key": output_key,
        "deal_id": deal_id,
        "deal_folder": deal_folder,
        "sponsors_found": len(sponsors),
        "sponsor_names": sponsor_names,
        "template_used": template_key,
    }


@app.post("/fill-from-deal")
async def fill_from_deal_endpoint(request: Request):
    """
    Fill memo from Layer 3 output (deal JSON with required fields for the memo).

    Input is the exact JSON produced by Layer 3; no separate schema step needed.

    Accepts two body shapes so n8n or other callers can send either format:

    1) Wrapped (recommended):
       { "payload": [ { deal_id, deal_folder, cover, deal_facts, ... } ], "output_key": "path/to.docx", "deal_index": 0, "images": {}, "template_key": "..." }

    2) Raw Layer 3 output (body = single deal object):
       Body is the deal object directly. output_key optional (default: deals/{deal_id}/Investment_Memo.docx).

    Returns: success, output_key, output_url, deal_id, deal_folder, sponsors_found, sponsor_names, template_used
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON")

    payload = None
    deal_index = 0
    output_key = None
    template_key = DEFAULT_TEMPLATE_KEY
    images = {}

    if isinstance(body, dict) and "payload" in body and isinstance(body.get("payload"), list):
        # Wrapped format
        payload = body["payload"]
        deal_index = int(body.get("deal_index", 0))
        output_key = body.get("output_key")
        template_key = body.get("template_key", template_key)
        images = body.get("images") or {}
    elif isinstance(body, dict) and body.get("deal_id") and body.get("cover") is not None:
        # Raw deal: body is the single deal object
        payload = [body]
        deal_index = 0
        output_key = request.query_params.get("output_key")
        template_key = request.query_params.get("template_key") or template_key
    elif isinstance(body, list) and len(body) > 0 and isinstance(body[0], dict) and body[0].get("deal_id"):
        # Body is array of deals (no wrapper)
        payload = body
        deal_index = 0
        output_key = request.query_params.get("output_key")

    if not payload:
        raise HTTPException(
            status_code=422,
            detail="Body must be either (1) { \"payload\": [ deal, ... ], \"output_key\": \"...\" } or (2) a single deal object (optionally ?output_key=...)"
        )
    # Default output_key from deal_id when not provided (e.g. raw deal from n8n with no query param)
    if not output_key and payload:
        deal_id = payload[deal_index].get("deal_id") if deal_index < len(payload) else payload[0].get("deal_id")
        safe_id = (deal_id or "deal").strip().replace(" ", "-")
        output_key = f"deals/{safe_id}/Investment_Memo.docx"

    try:
        return _run_fill_from_deal(payload=payload, deal_index=deal_index, output_key=output_key, template_key=template_key, images=images)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"fill-from-deal error: {e}\n{tb}")
        raise HTTPException(status_code=500, detail=f"Memo fill failed: {str(e)}. Check server logs for traceback.")


@app.post("/transform-deal-to-schema")
async def transform_deal_to_schema_endpoint(request: Request):
    """
    Debug: Map Layer 3 deal JSON to template schema only (no S3, no fill).
    Body: single deal object or array with one deal. Returns the schema that would be passed to the template.
    Use this to verify your input JSON is accepted and see the mapped output.
    """
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Request body must be valid JSON: {str(e)}")
    if isinstance(body, list) and len(body) > 0:
        deal = body[0]
    elif isinstance(body, dict) and body.get("deal_id") is not None:
        deal = body
    else:
        raise HTTPException(status_code=422, detail="Body must be a single deal object or array with one deal (with deal_id).")
    try:
        mapper = DealInputToSchemaMapper(deal)
        schema_data = mapper.transform()
        return schema_data
    except Exception as e:
        import traceback
        raise HTTPException(status_code=400, detail=f"Transform failed: {str(e)}\n{traceback.format_exc()}")


@app.post("/transform-layer2")
async def transform_layer2_endpoint(layer2_data: List[Dict[str, Any]]):
    """
    Transform Layer 2 data to schema format WITHOUT filling template.
    Useful for debugging or previewing the transformation.

    Request body: Array of Layer 2 extraction objects

    Returns: Transformed schema data
    """
    mapper = Layer2ToSchemaMapper(layer2_data)
    schema_data = mapper.transform()
    return schema_data


@app.get("/template-info")
async def get_template_info(template_key: str = DEFAULT_TEMPLATE_KEY):
    """Get information about a template (useful for debugging)."""
    try:
        template_bytes = download_template(template_key)
        template_stream = BytesIO(template_bytes)
        doc = DocxTemplate(template_stream)
        variables = doc.get_undeclared_template_variables()

        return {
            "template_key": template_key,
            "variables": list(variables),
            "variable_count": len(variables)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to analyze template: {str(e)}")


# =============================================================================
# Main
# =============================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
