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

        # Calculate combined totals
        combined_net_worth = sum(s.get('net_worth', 0) or 0 for s in sponsors)
        combined_liquidity = sum(s.get('liquidity', 0) or 0 for s in sponsors)

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
        self._sponsor = deal.get("sponsor") or {}
        self._sources_uses = deal.get("sources_and_uses") or {}
        self._valuation = deal.get("valuation") or {}
        self._narratives = deal.get("narratives") or {}
        self._risks = deal.get("risks_and_mitigants") or {}
        self._highlights = deal.get("deal_highlights") or {}
        self._due_diligence = deal.get("due_diligence") or {}
        self._environmental = deal.get("environmental") or {}
        self._zoning = deal.get("zoning") or {}

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

    def _build_cover(self) -> Dict[str, Any]:
        addr = self._property.get("address") or {}
        prop_name = self._property.get("name", "")
        return {
            "memo_subtitle": "CREDIT COMMITTEE MEMO",
            "memo_title": "BRIDGE LOAN REQUEST",
            "property_name": prop_name,
            "property_address": self._cover.get("property_address", ""),
            "credit_committee": self._split_list(self._cover.get("credit_committee", "")),
            "underwriting_team": self._split_list(self._cover.get("underwriting_team", "")),
            "memo_date": self._cover.get("date", datetime.now().strftime("%B %d, %Y")),
        }

    def _build_transaction_overview(self) -> Dict[str, Any]:
        ir_raw = self._loan_terms.get("interest_rate")
        ir = ir_raw if isinstance(ir_raw, dict) else {}
        if isinstance(ir_raw, str):
            ir = {"description": ir_raw, "default_rate": ""}
        deal_facts = [
            {"label": "Property Type", "value": self._deal_facts.get("property_type", "N/A")},
            {"label": "Property Name", "value": self._property.get("name", "N/A")},
            {"label": "Loan Purpose", "value": self._deal_facts.get("loan_purpose", "N/A")},
            {"label": "Loan Amount", "value": self._deal_facts.get("loan_amount", "N/A")},
            {"label": "Source", "value": self._deal_facts.get("source", "N/A")},
        ]
        loan_terms_list = [
            {"label": "Interest Rate", "value": ir.get("description", "N/A")},
            {"label": "Origination Fee", "value": (self._loan_terms.get("origination_fee") or "N/A")},
            {"label": "Exit Fee", "value": (self._loan_terms.get("exit_fee") or "N/A")},
            {"label": "Prepayment", "value": (self._loan_terms.get("prepayment") or "N/A")},
            {"label": "Guaranty", "value": (self._loan_terms.get("guaranty") or "N/A")},
        ]
        leverage_list = [
            {"label": "LTC at Closing", "value": self._leverage.get("fb_ltc_at_closing", "N/A")},
            {"label": "LTV at Closing", "value": self._leverage.get("ltv_at_closing", "N/A")},
            {"label": "LTV at Maturity", "value": self._leverage.get("ltv_at_maturity", "N/A")},
            {"label": "Debt Yield", "value": self._leverage.get("debt_yield_fully_drawn", "N/A")},
        ]
        return {
            "deal_facts": deal_facts,
            "loan_terms": loan_terms_list,
            "leverage_metrics": leverage_list,
        }

    def _build_executive_summary(self) -> Dict[str, Any]:
        narrative = self._narratives.get("transaction_overview", "")
        if not narrative:
            narrative = f"Bridge loan request for {self._property.get('name', 'the property')}. See narratives for full overview."
        narrative = narrative[:4000] if isinstance(narrative, str) else str(narrative)[:4000]
        items = (self._highlights.get("items") or [])[:6]
        key_highlights = [h.get("highlight", "") or h.get("description", "") for h in items if isinstance(h, dict)]
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
        sources = []
        for item in (table.get("sources") or []):
            if not isinstance(item, dict):
                continue
            sources.append({
                "label": item.get("item", "Source"),
                "amount": self._fmt_currency(item.get("amount")),
                "percent": self._fmt_pct(item.get("rate_pct")),
            })
        uses = []
        for cat in (table.get("uses") or []):
            if not isinstance(cat, dict):
                continue
            for item in (cat.get("items") or []):
                if not isinstance(item, dict):
                    continue
                uses.append({
                    "label": item.get("item", "Use"),
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
        narrative = self._narratives.get("property_overview", "")
        if not narrative:
            narrative = f"{self._property.get('name', 'The property')} is located at {addr.get('street', '')}, {addr.get('city', '')}, {addr.get('state', '')}. {self._property.get('building_sf', 'N/A')} SF, {self._property.get('land_area_acres', 'N/A')} acres."
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
        return {"description_narrative": narrative[:5000] if isinstance(narrative, str) else str(narrative)[:5000], "metrics": metrics}

    def _build_location(self) -> Dict[str, Any]:
        narrative = self._narratives.get("location_overview", "")
        if not narrative:
            addr = self._property.get("address") or {}
            narrative = f"The property is located in {addr.get('city', '')}, {addr.get('county', '')}, {addr.get('state', '')}. See appraisal for detailed location analysis."
        return {"narrative": narrative[:4000] if isinstance(narrative, str) else str(narrative)[:4000]}

    def _build_market(self) -> Dict[str, Any]:
        narrative = self._narratives.get("market_overview", "")
        if not narrative:
            narrative = "Market analysis indicates favorable conditions. Please refer to the appraisal for detailed market analysis."
        return {"narrative": narrative[:4000] if isinstance(narrative, str) else str(narrative)[:4000]}

    def _build_sponsorship(self) -> Dict[str, Any]:
        guarantors = self._sponsor.get("guarantors") or {}
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
        combined_nw = sum((s.get("net_worth") or 0) for s in sponsors)
        combined_liq = sum((s.get("liquidity") or 0) for s in sponsors)
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
        return {
            "overview_narrative": overview[:3000] if isinstance(overview, str) else str(overview)[:3000],
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
        narrative = self._narratives.get("risks_mitigants_narrative", "")
        risk_list = risk_items if risk_items else [{"category": "General", "score": "Moderate", "risk": "See risks and mitigants.", "mitigant": "See narrative."}]
        return {
            "overall_risk_score": "MODERATE",
            "recommendation_narrative": narrative[:2000] if narrative else "Based on the analysis, this transaction presents acceptable risk levels for Fairbridge.",
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
                "firm": self._due_diligence.get("appraisal_company", "N/A"),
                "appraiser": self._due_diligence.get("appraisal_firm", "N/A"),
                "effective_date": "N/A",
                "as_is_value": self._valuation.get("as_is_value", "N/A"),
                "stabilized_value": self._valuation.get("as_stabilized_value", "N/A"),
                "cap_rate": self._valuation.get("cap_rate", "N/A"),
            },
            "environmental": {
                "firm": self._environmental.get("firm", "N/A"),
                "report_date": self._environmental.get("report_date", "N/A"),
                "current_recs": str(len(self._environmental.get("historical_recs", []))),
                "phase_ii_required": "No",
                "findings": (self._environmental.get("findings_summary") or "N/A")[:500],
            },
            "pca": {
                "firm": self._due_diligence.get("pca_firm") or "N/A",
                "report_date": "N/A",
                "summary": self._narratives.get("pca_narrative") or "See property condition assessment.",
            },
        }

    def _build_zoning_entitlements(self) -> Dict[str, Any]:
        narrative = self._narratives.get("zoning_narrative", "")
        if not narrative:
            narrative = f"Current zoning: {self._zoning.get('zone_code', 'N/A')}. {self._zoning.get('highest_best_use_improved', '')}"
        return {
            "summary_narrative": narrative[:3000] if isinstance(narrative, str) else str(narrative)[:3000],
            "current_zoning": self._zoning.get("zone_code", "N/A"),
            "proposed_zoning": "See redevelopment",
            "entitlement_status": "See zoning narrative",
            "exists": bool(self._zoning),
        }

    def _build_foreclosure_analysis(self) -> Dict[str, Any]:
        narrative = self._narratives.get("foreclosure_assumptions", "")
        rows = [{"Quarter": f"Q{q}", "Beginning_Balance": "TBD", "Legal_Fees": "TBD", "Taxes": "TBD", "Insurance": "TBD", "Total_Carrying_Costs": "TBD", "Interest_Accrued": "TBD", "Ending_Balance": "TBD", "Property_Value": "TBD", "LTV": "TBD"} for q in range(1, 9)]
        return {"scenario_default_rate": {"rows": rows}, "scenario_note_rate": {"rows": rows}}

    def transform(self) -> Dict[str, Any]:
        """Transform deal input to template schema format."""
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
            },
        }
        raw_li = self.deal.get("loan_issues")
        if raw_li is not None:
            out["loan_issues"] = {
                "income_producing": raw_li.get("income_producing") if isinstance(raw_li.get("income_producing"), list) else (raw_li.get("income_producing") or []),
                "development": raw_li.get("development") if isinstance(raw_li.get("development"), list) else (raw_li.get("development") or []),
            }
        cv = self.deal.get("collaborative_ventures")
        if isinstance(cv, list):
            out["collaborative_ventures"] = {"items": cv}
        elif isinstance(cv, dict):
            out["collaborative_ventures"] = {"items": list(cv.values()) if cv else []}
        else:
            out["collaborative_ventures"] = {"items": []}
        for key in ("capital_stack", "closing_disbursement", "rent_roll", "construction_budget", "comps", "redevelopment", "due_diligence"):
            out[key] = self.deal.get(key) if self.deal.get(key) is not None else {}
        al = self.deal.get("active_litigation") or {}
        if isinstance(al, dict):
            cases = al.get("cases")
            if isinstance(cases, dict):
                al = {**al, "cases": list(cases.values())}
            elif cases is None:
                al = {**al, "cases": []}
        out["active_litigation"] = al
        dh = self.deal.get("deal_highlights") or {}
        out["deal_highlights"] = dict(dh) if isinstance(dh, dict) else {}
        if "items" not in out["deal_highlights"]:
            out["deal_highlights"]["items"] = []
        cd = self.deal.get("closing_disbursement") or {}
        narrative = self._narratives.get("closing_funding_narrative") or ""
        out["closing_funding_and_reserves"] = dict(cd) if isinstance(cd, dict) else {}
        if narrative:
            out["closing_funding_and_reserves"]["narrative"] = narrative
        lev = self._leverage
        out["LTC"] = lev.get("fb_ltc_at_closing") or lev.get("ltc_at_maturity") or "N/A"
        out["LTV"] = lev.get("ltv_at_closing") or lev.get("ltv_at_maturity") or "N/A"
        out["property_value"] = self._valuation if self._valuation else {}
        exit_narr = self._narratives.get("exit_strategy") or ""
        out["exit_strategy"] = {"narrative": exit_narr} if isinstance(exit_narr, str) else (exit_narr if isinstance(exit_narr, dict) else {"narrative": ""})
        fa_narr = self._narratives.get("foreclosure_assumptions") or ""
        out["foreclosure_assumptions"] = {"narrative": fa_narr} if isinstance(fa_narr, str) else (fa_narr if isinstance(fa_narr, dict) else {"narrative": ""})
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
    if "financial_info" not in flat and "sponsorship" in sections:
        flat["financial_info"] = sections["sponsorship"].get("financial_summary", [])
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
    """Fill template and return as download."""
    template_bytes = download_template(request.template_key)
    filled_bytes = fill_template(template_bytes, request.data, request.images)

    return StreamingResponse(
        BytesIO(filled_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={request.output_filename}"}
    )


@app.post("/fill-and-upload")
async def fill_and_upload_endpoint(request: FillAndUploadRequest):
    """Fill template and upload to S3."""
    template_bytes = download_template(request.template_key)
    filled_bytes = fill_template(template_bytes, request.data, request.images)
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
