# Layer 3 Input Data Debugging - Handoff Document

**Date:** January 29, 2026
**Status:** Template rendering WORKING - Input data needs debugging
**Deal:** Broward Blvd - 7001-7181 W. Broward Blvd, Plantation, FL

---

## 1. What's Working

### Template Engine Fixed
The docxtpl table loop syntax has been corrected. The issue was that `{%tr for...%}` and `{%tr endfor %}` were in the same table row, but docxtpl replaces the ENTIRE row when it sees `{%tr`.

**Solution applied:** Each table loop restructured from 1 row to 3 rows:
1. Row 1: `{%tr for item in items %}` (loop directive)
2. Row 2: `{{ item.label }}` | `{{ item.value }}` (content that repeats)
3. Row 3: `{%tr endfor %}` (close loop)

**Fixed template:** `Fairbridge_Memo_Template_FIXED_v2.docx`

### Tables Confirmed Working
- Foreclosure Default Rate table: 13 rows (header + 12 quarters) ✅
- Foreclosure Note Rate table: 13 rows (header + 12 quarters) ✅
- Deal facts table: Expanding correctly ✅
- Loan terms table: Expanding correctly ✅
- Leverage metrics table: Expanding correctly ✅
- Sources table: Expanding correctly ✅
- Uses table: Expanding correctly ✅

---

## 2. Service Architecture

```
memo-filler service (FastAPI + docxtpl)
├── Endpoint: POST /fill-and-upload
├── Template: S3 fam.workspace/_Templates/Fairbridge_Memo_Template_v1_0.docx
├── Input: { data: {...}, images: {...}, template_key, output_key }
└── Output: Filled .docx uploaded to S3
```

**Key files:**
- `/sessions/compassionate-modest-darwin/mnt/memo_filler/main.py` - FastAPI service
- `/sessions/compassionate-modest-darwin/mnt/memo_filler/Fairbridge_Memo_Template_FIXED_v2.docx` - Fixed template
- `/sessions/compassionate-modest-darwin/fix_table_loops.py` - Script that fixed the template

---

## 3. Layer 3 Data Structure Overview

The Layer 3 JSON is ~2,500 lines with this top-level structure:

```json
{
  "meta": { "layer": 3, "deal_id": "broward-blvd", "ready_for_layer4": true },
  "deal_identification": { "property_address", "borrower", "sponsor_names", ... },
  "extracted_data": {
    "appraisal": { "data": { "value_as_is", "value_upon_stabilization", ... } },
    "environmental": { "phase_i": { "data": {...} } },
    "loan_terms": { "data": { "loan_amount", "interest_rate", ... } },
    "sources_and_uses": { "data": {...} },
    "site_plan": { "data": {...} },
    "sponsor_pfs": [ { "data": { "net_worth", "liquid_assets", ... } } ],
    ...
  },
  "calculations": { "leverage_ratios": {...} },
  "sources_uses_analysis": { "tables": {...} },
  "foreclosure_analysis": { "scenario_default_rate", "scenario_note_rate" },
  "risk_analysis": { "categories": { "sponsor_risk", "property_risk", ... } },
  "deal_memo_ready": {
    "deal_facts_table": {...},
    "leverage_ratios_table": {...},
    "sources_uses_table": {...},
    "property_summary": {...},
    "sponsor_summary": {...},
    "third_party_reviews": {...},
    "default_analysis": {...},
    "narrative_placeholders": {...}
  },
  "validations": { "summary": {...}, "checks": [...] }
}
```

---

## 4. Gap Analysis: Generated vs Reference PDF

### Reference PDF Structure (49 pages)
The Fairbridge reference memo (`FB Deal Memo - 7001 and 7007-7181 W. Broward Blvd, Plantation, FL.pdf`) contains:

| Section | Pages | Content |
|---------|-------|---------|
| Cover Page | 1 | Title, property image, key metrics |
| Table of Contents | 1 | 18 sections with page numbers |
| Transaction Overview | 2 | Deal facts, loan terms, leverage tables |
| Sponsorship Information | 6 | Detailed sponsor bio, financials, track record |
| Sources & Uses | 2 | S&U table, capital stack charts |
| Collateral Information | 3 | Property description, tenant roll, occupancy |
| Location | 3 | Maps, demographics, accessibility |
| Market Overview | 3 | Submarket data, comps, trends |
| Zoning & Entitlements | 2 | Current zoning, development rights |
| Third Party Reports | 3 | Appraisal, environmental, PCA summaries |
| Financial Analysis | 4 | DCF, exit scenarios, sensitivity |
| Exit Strategy | 2 | Primary and backup exit paths |
| Risks & Mitigants | 3 | Risk matrix, mitigants |
| Deal Highlights | 1 | Key selling points |
| Foreclosure Analysis | 2 | Default and note rate scenarios |
| Due Diligence Checklist | 2 | Status of all DD items |
| Recommendation | 1 | IC recommendation and conditions |
| Exhibits | Multiple | Supporting documents |

### What's Missing from Generated Output

**Major Gaps:**

1. **Sponsor Information (6+ pages in reference)**
   - Detailed principal bios
   - Entity structure diagrams
   - Net worth / liquidity breakdown
   - Track record with specific deals
   - Financial statements summary

2. **Property Images & Maps**
   - Aerial view
   - Street view
   - Regional map
   - Site plan
   - Property photos

3. **Financial Analysis / DCF**
   - Cash flow projections
   - Exit scenario modeling
   - Sensitivity analysis
   - IRR calculations

4. **Market Overview**
   - Submarket metrics (requires CoStar/Green Street enrichment)
   - Comparable sales
   - Rent comps
   - Absorption data

5. **Detailed Loan Terms**
   - Rate structure
   - Prepayment provisions
   - Reserve requirements
   - Draw schedule
   - Covenants

6. **Exit Strategy**
   - Primary exit path
   - Alternative exits
   - Timeline to exit

---

## 5. Critical Data Issues in Layer 3

### Missing/Null Values

```
deal_memo_ready.deal_facts_table.interest_rate = null  ← CRITICAL
extracted_data.sources_and_uses.data.sources.* = all null
extracted_data.sources_and_uses.data.uses.* = all null
deal_memo_ready.sponsor_summary.equity_at_risk = null
deal_memo_ready.third_party_reviews.property_condition.* = all null
```

### Fields Present but Need Formatting

1. **Foreclosure Table Rows** - Currently have numeric values, need pre-formatted strings:
   ```json
   // Current format (numeric):
   { "quarter": 1, "beginning_balance": 27000000, "ltv": 0.6261 }

   // Required format (strings):
   { "Quarter": "Q1", "Beginning_Balance": "$27,000,000", "LTV": "62.6%" }
   ```

2. **Interest Rate** - Layer 3 has it in loan_terms but it's not in deal_facts_table:
   ```
   extracted_data.loan_terms.data.interest_rate = "SOFR + 670 (11.00% Interest Rate Floor)"
   deal_memo_ready.deal_facts_table.interest_rate = null  ← needs to be populated
   ```

### Narrative Placeholders Need LLM Generation

```json
"narrative_placeholders": {
  "deal_summary": "[TO BE GENERATED]",
  "location_overview": "[TO BE GENERATED]",
  "market_overview": "[TO BE GENERATED - requires CoStar data]",
  "business_plan": "...",  // This one has content
  "exit_strategy": "[TO BE GENERATED]",
  "risks_and_mitigants": "..."  // This one has content
}
```

---

## 6. Template Expected Data Schema

The template expects data in this structure:

```json
{
  "cover": {
    "memo_title": "INVESTMENT MEMORANDUM",
    "property_name": "Plantation Marketplace",
    "property_address": "7007 W Broward Blvd, Plantation, FL 33317",
    "credit_committee": ["Name 1", "Name 2"],
    "memo_date": "January 29, 2026"
  },
  "toc": "string or null",
  "sections": {
    "transaction_overview": {
      "deal_facts": [
        { "label": "Property Address", "value": "..." },
        { "label": "Loan Amount", "value": "$27,000,000" }
      ],
      "loan_terms": [
        { "label": "Loan Term", "value": "18 months" }
      ],
      "leverage_metrics": [
        { "label": "LTC at Closing", "value": "51.0%" }
      ]
    },
    "executive_summary": {
      "narrative": "string",
      "key_highlights": ["highlight1", "highlight2"],
      "recommendation": "string",
      "conditions": ["condition1"]
    },
    "property": {
      "description_narrative": "string",
      "metrics": [{ "label": "GLA", "value": "240,987 SF" }]
    },
    "foreclosure_analysis": {
      "assumptions": [{ "label": "Loan Amount", "value": "$27,000,000" }],
      "scenario_default_rate": {
        "name": "Default Interest Rate (24%)",
        "rows": [
          {
            "Quarter": "Q1",
            "Beginning_Balance": "$27,000,000",
            "Legal_Fees": "$7,500",
            "Taxes": "$233,000",
            "Insurance": "$7,926",
            "Total_Carrying_Costs": "$248,426",
            "Interest_Accrued": "$1,634,906",
            "Ending_Balance": "$28,883,331",
            "Property_Value": "$46,134,000",
            "LTV": "62.6%"
          }
          // ... 11 more quarters
        ],
        "final_ltv": "142.7%"
      },
      "scenario_note_rate": { /* same structure */ }
    }
  }
}
```

---

## 7. Transformation Tasks

### Task 1: Populate Missing Fields
- Copy `extracted_data.loan_terms.data.interest_rate` → `deal_memo_ready.deal_facts_table.interest_rate`
- Compute sources/uses breakdown from loan_terms data

### Task 2: Format Foreclosure Rows
Transform from numeric to display strings:

```javascript
function formatForeclosureRow(row) {
  return {
    Quarter: `Q${row.quarter}`,
    Beginning_Balance: formatCurrency(row.beginning_balance),
    Legal_Fees: formatCurrency(row.legal_fees),
    Taxes: formatCurrency(row.tax_payment),
    Insurance: formatCurrency(row.insurance_payment),
    Total_Carrying_Costs: formatCurrency(row.total_carrying_costs),
    Interest_Accrued: formatCurrency(row.interest_accrued),
    Ending_Balance: formatCurrency(row.ending_balance),
    Property_Value: formatCurrency(row.property_value),
    LTV: formatPercent(row.ltv)
  };
}
```

### Task 3: Generate Narratives
Use LLM to generate:
- `executive_summary.narrative`
- `property.description_narrative`
- `location.narrative`
- `sponsorship.overview_narrative`

### Task 4: Add Missing Sections
- Sponsor Information (use `extracted_data.sponsor_pfs`)
- Risk Analysis (use `risk_analysis.categories`)
- Business Plan (use `deal_memo_ready.narrative_placeholders.business_plan`)

### Task 5: Screenshot Integration
Capture Excel table images using the screenshot service:
```
POST https://e44kgo84cc8g0okggsw888o4.app9.anant.systems/detect-and-capture
```

Tables to capture:
- Sources & Uses
- Capital Stack at Closing
- Capital Stack at Maturity
- Foreclosure Analysis (if Excel-based)

---

## 8. Files for Reference

| File | Location | Purpose |
|------|----------|---------|
| Layer 3 JSON | `/sessions/compassionate-modest-darwin/mnt/uploads/memo_generation_data.md` | Full Layer 3 output |
| Reference PDF | `/sessions/compassionate-modest-darwin/mnt/uploads/FB Deal Memo - 7001 and 7007-7181 W. Broward Blvd, Plantation, FL .pdf` | Target format |
| Generated output | `/sessions/compassionate-modest-darwin/mnt/uploads/data (1).docx` | Latest render |
| Fixed template | `/sessions/compassionate-modest-darwin/mnt/memo_filler/Fairbridge_Memo_Template_FIXED_v2.docx` | Working template |
| Service code | `/sessions/compassionate-modest-darwin/mnt/memo_filler/main.py` | FastAPI service |
| Handoff doc | `/sessions/compassionate-modest-darwin/mnt/uploads/LAYER4_COWORK_HANDOFF_UPDATED.md` | Architecture context |

---

## 9. Recommended Debugging Approach

1. **Start with the transformation layer** - Build a function that takes Layer 3 JSON and outputs the template-ready schema
2. **Validate field mapping** - Ensure all template placeholders have corresponding data
3. **Test incrementally** - Add one section at a time and render
4. **Address narratives last** - These require LLM generation and can be stubbed initially
5. **Add images after text** - Get all text content working first

---

## 10. Quick Test Command

To test the memo-filler service locally:

```bash
# Start the service
cd /sessions/compassionate-modest-darwin/mnt/memo_filler
python main.py

# Test endpoint
curl -X POST http://localhost:8000/fill \
  -H "Content-Type: application/json" \
  -d @test_data.json \
  -o output.docx
```

---

*Handoff prepared for Layer 3 input data debugging.*
