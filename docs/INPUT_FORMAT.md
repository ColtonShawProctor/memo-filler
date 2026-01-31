# Memo-filler input format (exact)

**Endpoint:** `POST /fill-from-deal`  
**Body:** Either (1) a **single deal object** (Layer 3 output), or (2) an **array** of deal objects, or (3) a wrapper `{ "payload": [ deal, ... ], "output_key": "...", ... }`.

---

## Single deal object – required top-level keys

Every deal object must have these keys (same shape as Layer 3 output):

| Key | Type | Description |
|-----|------|-------------|
| `deal_id` | string | e.g. `"broward-blvd"` |
| `deal_folder` | string | e.g. `"7001 and 7007-7181 W. Broward Blvd., Plantation, FL"` |
| `generated_at` | string | ISO 8601, e.g. `"2026-01-31T19:32:33.420Z"` |
| `cover` | object | `{ property_address, credit_committee, underwriting_team, date }` |
| `deal_facts` | object | `{ property_type, loan_purpose, loan_amount, source }` |
| `loan_terms` | object | `{ interest_rate: { description, default_rate }, origination_fee, exit_fee, prepayment, guaranty, collateral }` |
| `leverage` | object | `{ fb_ltc_at_closing, ltc_at_maturity, ltv_at_closing, ltv_at_maturity, ltpp, debt_yield_fully_drawn }` |
| `sponsor` | object | `{ table: [...], borrowing_entity, guarantors: { names, guarantees, combined_net_worth, ... }, principals: [...] }` |
| `sources_and_uses` | object | `{ table: { title, sources, total_sources, uses, total_uses, notes }, total_project_cost, equity_at_closing, equity_already_invested }` |
| `closing_disbursement` | object | payoff, fees, totals, etc. |
| `capital_stack` | object | `{ table: { title, sources, uses, total_sources, total_uses, notes } }` |
| `due_diligence` | object | lenders_counsel, appraisal_firm, environmental_firm, etc. |
| `property` | object | `{ name, address: { street, city, county, state, zip }, property_type, year_built, building_sf, occupancy_current, ... }` |
| `valuation` | object | as_is_value, as_stabilized_value, noi, cap_rate, etc. |
| `zoning` | object | zone_code, permitted_uses, live_local_act, highest_best_use_vacant, highest_best_use_improved |
| `redevelopment` | object | description, proposed_units, demolition_area_sf, etc. |
| `environmental` | object | firm, report_date, findings_summary, historical_recs, etc. |
| `rent_roll` | object | occupancy_rate, total_monthly_rent, total_annual_rent |
| `active_litigation` | object | exists, cases |
| `comps` | object | sales_comps: [...] |
| `construction_budget` | object | total_budget, hard_costs, soft_costs |
| `risks_and_mitigants` | object | items: [ { risk, description, mitigant, sub_risks? } ] |
| `deal_highlights` | object | items: [ { highlight, description } ] |
| `collaborative_ventures` | object | {} |
| `loan_issues` | object | income_producing, development |
| `narratives` | object | transaction_overview, loan_terms_narrative, property_overview, location_overview, market_overview, appraisal_analysis, zoning_narrative, exit_strategy, environmental_narrative, pca_narrative, closing_funding_narrative, foreclosure_assumptions, active_litigation_narrative, sponsor_narrative, risks_mitigants_narrative, deal_highlights_narrative, property_value_narrative, comps_narrative (all strings) |

---

## Minimal valid example (single deal as body)

```json
{
  "deal_id": "example-deal",
  "deal_folder": "Example Deal Folder",
  "generated_at": "2026-01-31T19:32:33.420Z",
  "cover": {
    "property_address": "123 Main St, City, ST",
    "credit_committee": "CC1, CC2",
    "underwriting_team": "UW1, UW2",
    "date": "1/31/2026"
  },
  "deal_facts": {
    "property_type": "Retail",
    "loan_purpose": "Refinance",
    "loan_amount": "$27,000,000",
    "source": "Source Name"
  },
  "loan_terms": {
    "interest_rate": {
      "description": "SOFR plus spread.",
      "default_rate": "Default rate description."
    },
    "origination_fee": "1%",
    "exit_fee": "1%",
    "prepayment": "Permitted per loan docs.",
    "guaranty": "Bad boy and interest/carry.",
    "collateral": "First mortgage and pledge of membership interests."
  },
  "leverage": {
    "fb_ltc_at_closing": "51.00%",
    "ltc_at_maturity": "57.00%",
    "ltv_at_closing": "37.00%",
    "ltv_at_maturity": "42.00%",
    "ltpp": "57.00%",
    "debt_yield_fully_drawn": "6.81%"
  },
  "sponsor": {
    "table": [
      {
        "entity": "Sponsor LLC",
        "profit_percentage_interest": "100%",
        "membership_interest": 1000,
        "capital_interest_amount": 20000000,
        "capital_interest_percentage": "100%"
      }
    ],
    "borrowing_entity": "Borrower LLC",
    "guarantors": {
      "names": ["Guarantor One"],
      "guarantees": ["bad boy", "interest", "carry"],
      "combined_net_worth": 239650000,
      "combined_cash_position": 8400000,
      "combined_securities_holdings": 92249616,
      "lender_requirements": {
        "minimum_net_worth": 150000000,
        "minimum_liquidity_securities": 30000000
      }
    },
    "principals": [
      {
        "name": "Principal Name",
        "title": "Title",
        "company": "Company",
        "experience": "Experience summary."
      }
    ]
  },
  "sources_and_uses": {
    "table": {
      "title": "Sources and Uses",
      "sources": [{"item": "Loan", "amount": 27000000}],
      "total_sources": 27000000,
      "uses": [{"category": "Uses", "items": [{"item": "Acquisition", "amount": 27000000}]}],
      "total_uses": 27000000,
      "notes": []
    },
    "total_project_cost": "",
    "equity_at_closing": "",
    "equity_already_invested": ""
  },
  "closing_disbursement": {
    "payoff_existing_debt": "",
    "broker_fee": "",
    "origination_fee": "",
    "closing_costs_title": "",
    "lender_legal": "",
    "borrower_legal": "",
    "misc": "",
    "interest_reserve": "",
    "total_disbursements": "$24,795,500",
    "sponsors_equity_at_closing": "$980,876",
    "fairbridge_release_at_closing": "$23,814,624"
  },
  "capital_stack": {
    "table": {
      "title": "Capital Stack",
      "sources": [{"item": "Loan", "amount": 27000000}],
      "total_sources": 27000000,
      "uses": [{"category": "Uses", "items": [{"item": "Refinance", "amount": 24000000}]}],
      "total_uses": 27000000,
      "notes": []
    }
  },
  "due_diligence": {
    "lenders_counsel": null,
    "borrowers_counsel": null,
    "appraisal_firm": "Appraiser",
    "appraisal_company": "Appraisal Co",
    "pca_firm": null,
    "background_check_firm": null,
    "environmental_firm": "Environmental Co",
    "site_visit_team": null
  },
  "property": {
    "name": "Property Name",
    "address": {"street": "123 Main St", "city": "City", "county": "County", "state": "ST", "zip": "12345"},
    "property_type": "Retail",
    "year_built": 1980,
    "year_renovated": 2000,
    "land_area_acres": 22.79,
    "land_area_sf": 992684,
    "building_sf": 240987,
    "num_buildings": 4,
    "num_stories": 1,
    "occupancy_current": 82,
    "occupancy_stabilized": 96,
    "anchor_tenants": "Anchor A, Anchor B",
    "parking_spaces": 991,
    "parking_ratio": 4.11,
    "condition": "Average",
    "parcel_numbers": "123-45-67"
  },
  "valuation": {
    "as_is_value": "$46,600,000",
    "as_stabilized_value": "$51,800,000",
    "cap_rate": "6.00%",
    "discount_rate": "8.50%",
    "terminal_cap_rate": "6.50%",
    "noi": "$2,982,866",
    "effective_gross_income": "$5,119,263",
    "operating_expenses": "$2,136,397",
    "expense_ratio": "41.73%"
  },
  "zoning": {
    "zone_code": "B-2P",
    "permitted_uses": "Retail, office, etc.",
    "live_local_act": {"description": "...", "subject_applicability": "..."},
    "highest_best_use_vacant": "Mixed-Use",
    "highest_best_use_improved": "Redevelopment"
  },
  "redevelopment": {
    "description": "Partial demolition and multifamily.",
    "proposed_units": 577,
    "demolition_area_sf": 39203,
    "land_area_for_multifamily": 6.3,
    "estimated_demolition_cost": "$600,000"
  },
  "environmental": {
    "firm": "Environmental Firm",
    "report_date": "April 2022",
    "property_address": "123 Main St",
    "findings_summary": "No RECs identified.",
    "historical_recs": [],
    "recognized_environmental_conditions": [],
    "controlled_recs": [],
    "assessment_standard": "ASTM E1527-13"
  },
  "rent_roll": {"occupancy_rate": "", "total_monthly_rent": "", "total_annual_rent": ""},
  "active_litigation": {"exists": false, "cases": {}},
  "comps": {"sales_comps": []},
  "construction_budget": {"total_budget": "", "hard_costs": "", "soft_costs": ""},
  "risks_and_mitigants": {
    "items": [{"risk": "Entitlement Risk", "description": "Description.", "mitigant": "Live Local Act fallback."}]
  },
  "deal_highlights": {
    "items": [{"highlight": "Strong Cash Flow", "description": "Description."}]
  },
  "collaborative_ventures": {},
  "loan_issues": {"income_producing": null, "development": null},
  "narratives": {
    "transaction_overview": "Transaction overview narrative.",
    "loan_terms_narrative": "Loan terms narrative.",
    "property_overview": "Property overview narrative."
  }
}
```

---

## Alternative: array of deals

Body can be a JSON **array** of deal objects (same shape as above):

```json
[
  { "deal_id": "broward-blvd", "deal_folder": "...", "cover": {...}, ... },
  { "deal_id": "other-deal", ... }
]
```

The first deal is used unless you pass `deal_index` in a wrapper (see below).

---

## Alternative: wrapped body

```json
{
  "payload": [
    { "deal_id": "broward-blvd", "deal_folder": "...", "cover": {...}, "deal_facts": {...}, ... }
  ],
  "deal_index": 0,
  "output_key": "deals/broward-blvd/Investment_Memo.docx",
  "template_key": "_Templates/FB_Deal_Memo_Template.docx",
  "images": {}
}
```

---

Full TypeScript types: `types/deal-input.ts`.  
Full example file: `sample-input/deal-payload.example.json`.
