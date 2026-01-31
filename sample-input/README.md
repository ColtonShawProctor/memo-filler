# Sample input

Place a full deal payload here as a JSON file. The root must be an **array** of deal objects:

```json
[
  {
    "deal_id": "broward-blvd",
    "deal_folder": "7001 and 7007-7181 W. Broward Blvd., Plantation, FL",
    "generated_at": "2026-01-31T19:32:33.420Z",
    "cover": { ... },
    "deal_facts": { ... },
    "loan_terms": { ... },
    "leverage": { ... },
    "sponsor": { ... },
    "sources_and_uses": { ... },
    "closing_disbursement": { ... },
    "capital_stack": { ... },
    "due_diligence": { ... },
    "property": { ... },
    "valuation": { ... },
    "zoning": { ... },
    "redevelopment": { ... },
    "environmental": { ... },
    "rent_roll": { ... },
    "active_litigation": { ... },
    "comps": { ... },
    "construction_budget": { ... },
    "risks_and_mitigants": { ... },
    "deal_highlights": { ... },
    "collaborative_ventures": {},
    "loan_issues": { ... },
    "narratives": { ... }
  }
]
```

See `../types/deal-input.ts` for the full TypeScript interfaces. Use your full payload (e.g. the Broward Blvd deal) as the array element(s).
