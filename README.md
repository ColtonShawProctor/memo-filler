# Memo Filler

Consumes the **deal memo input format** and supports filling or generating memo content from structured deal data.

## Input format

The input is an **array of deal objects** (`DealInput[]`). Each element has this shape:

| Top-level key | Description |
|---------------|-------------|
| `deal_id` | Slug identifier (e.g. `"broward-blvd"`) |
| `deal_folder` | Human-readable deal folder name |
| `generated_at` | ISO 8601 timestamp |
| `cover` | Cover page: property_address, credit_committee, underwriting_team, date |
| `deal_facts` | Property type, loan purpose, loan amount, source |
| `loan_terms` | Interest rate (description, default_rate), origination_fee, exit_fee, prepayment, guaranty, collateral |
| `leverage` | LTC/LTV and debt yield metrics |
| `sponsor` | Table (entity, profit %, membership, capital), borrowing_entity, guarantors, principals |
| `sources_and_uses` | Table (sources, uses, totals, notes) and equity fields |
| `closing_disbursement` | Payoff, fees, reserves, totals |
| `capital_stack` | Table (sources, uses, totals, notes) |
| `due_diligence` | Counsel, appraisal, PCA, environmental, site visit |
| `property` | Name, address, type, GLA, occupancy, anchors, parking, condition, parcels |
| `valuation` | As-is/stabilized value, cap/discount rates, NOI, valuation_approaches, market_value_conclusions |
| `zoning` | Zone code, permitted uses, Live Local Act, highest & best use |
| `redevelopment` | Description, proposed units, demolition, land area, cost |
| `environmental` | Firm, report date, findings, historical RECs, assessment standard |
| `rent_roll` | Occupancy rate, monthly/annual rent (often empty) |
| `active_litigation` | exists, cases (complaint, sponsor explanation, counsel analysis, holdback) |
| `comps` | sales_comps array |
| `construction_budget` | total_budget, hard_costs, soft_costs |
| `risks_and_mitigants` | items (risk, description, mitigant, sub_risks) |
| `deal_highlights` | items (highlight, description) |
| `collaborative_ventures` | Object (often empty) |
| `loan_issues` | income_producing, development |
| `narratives` | Long-form text: transaction_overview, loan_terms_narrative, property_overview, etc. |

## Types

- **TypeScript**: `types/deal-input.ts` exports `DealInput`, `DealInputPayload`, and all nested interfaces.
- Use `DealInputPayload` for the root (array of deals).

## Sample

- `sample-input/` contains an example payload in this format (one deal, e.g. Broward Blvd).

## Usage

### Filling a memo from the new format

The Memo Filler service accepts the new format via **`POST /fill-from-deal`**:

- **Request body**: `{ "payload": [ { deal_id, deal_folder, cover, deal_facts, loan_terms, sponsor, narratives, ... } ], "deal_index": 0, "output_key": "path/to/output.docx", "images": {} }`
- **payload**: Array of deal objects (your full JSON in this format).
- **deal_index**: Which deal in the array to use (default `0`).
- **output_key**: S3 key where the filled memo will be uploaded.
- **images**: Optional `{ image_key: base64 }` for template images.

The service maps the deal object to the Word template schema, fills the template, and uploads the result to S3. It returns `success`, `output_key`, `output_url`, `deal_id`, `sponsors_found`, and `sponsor_names`.

### Other consumers

1. Send `DealInputPayload` (array of deal objects) to `POST /fill-from-deal` with `output_key` and optional `deal_index`.
2. Use `deal_id` and `deal_folder` for routing or naming.
3. Read sections from each `DealInput` (cover, loan_terms, sponsor, narratives, etc.) as needed.
