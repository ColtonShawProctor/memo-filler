# Template Variables Expected by Memo-Filler (for Claude)

This document lists the **Jinja2/docxtpl** variable names the Fairbridge Deal Memo template and memo-filler service expect. Use it when:

- **Generating Layer 3 output** that will be sent to `POST /fill` or `POST /fill-from-deal`
- **Writing or editing the Word template** (placeholders like `{{ variable }}`, `{% for row in sponsor_table %}`)

Data is flattened to the root for the template, so use **top-level names** unless noted.

---

## Cover & TOC

| Variable | Type | Description |
|----------|------|-------------|
| `cover` | dict | `property_address`, `credit_committee` (list or string), `underwriting_team`, `memo_date` (or `date`) |
| `toc` | string | Literal `{{TOC}}` for Word TOC |

---

## Deal Facts (single values or label/value table)

| Variable | Type | Description |
|----------|------|-------------|
| `deal_facts` | dict | Direct access: `property_type`, `property_name`, `loan_purpose`, `loan_amount`, `source` |
| `deal_facts_raw` | dict | Same as above; flattened to root so `{{ property_type }}`, `{{ loan_amount }}` work |
| `transaction_overview` | dict | Contains `deal_facts` (array of `{label, value}`), `loan_terms` (array), `narrative`, `key_highlights` |

Template may use either:
- `{{ deal_facts.property_type }}`, `{{ deal_facts.loan_amount }}`, etc.
- Or loop: `{% for row in transaction_overview.deal_facts %}` … `{{ row.label }}` / `{{ row.value }}`

---

## Loan Terms

| Variable | Type | Description |
|----------|------|-------------|
| `loan_terms` | dict | `interest_rate` (string or dict with `description`), `origination_fee`, `exit_fee`, `term`, `extension_option`, `prepayment`, `guaranty`, `collateral` |
| `loan_terms_raw` | dict | Same; used for direct property access |
| `interest_rate_display` | string | One-line rate (e.g. "SOFR + 2.50%" or "7.25%") for Deal Facts table |
| `origination_fee_display` | string | One-line origination fee |
| `exit_fee_display` | string | One-line exit fee |

Use `{{ loan_terms.interest_rate }}`, `{{ interest_rate_display }}`, etc.

---

## Leverage

| Variable | Type | Description |
|----------|------|-------------|
| `leverage` | dict | `fb_ltc_at_closing`, `ltc_at_closing`, `ltc_at_maturity`, `ltv_at_closing`, `ltv_at_maturity`, `debt_yield_fully_drawn`, `debt_yield` |
| `leverage_raw` | dict | Same |
| `LTC` | string | Single display value (e.g. "51.00%") |
| `LTV` | string | Single display value |

Alias: `leverage` is also exposed as `leverage_metrics` via template alias.

---

## Sources & Uses

| Variable | Type | Description |
|----------|------|-------------|
| `sources_list` | list | `[{ "label" or "item" or "name", "amount" }]` — one row per source |
| `uses_list` | list | `[{ "label" or "item" or "name", "amount", optional "release_conditions" }]` — one row per use |
| `sources_total` | string | e.g. `"$27,000,000"` |
| `uses_total` | string | e.g. `"$27,000,000"` |
| `sources_uses_max_rows` | number | `max(len(sources_list), len(uses_list), 1)` for table row count |
| `sources_and_uses` | dict | Section object; may contain `table`, `total_sources`, `total_uses` |

Template usage: `{% for s in sources_list %}`, `{% for u in uses_list %}`, `{{ sources_total }}`, `{{ uses_total }}`.

---

## Capital Stack

| Variable | Type | Description |
|----------|------|-------------|
| `capital_stack_sources` | list | `[{ "label" or "item", "amount", optional "percent" }]` |
| `capital_stack_uses` | list | Same shape as uses |
| `capital_stack_total` | string | e.g. `"$X,XXX,XXX"` |
| `capital_stack_title` | string | e.g. "Capital Stack" |
| `capital_stack` | dict | `{ "title", "sources", "uses" }` |

Template: `{% for s in capital_stack_sources %}`, `{% for u in capital_stack_uses %}`, `{{ capital_stack_total }}`.

---

## Sponsor Ownership Table (5-column)

| Variable | Type | Description |
|----------|------|-------------|
| `sponsor_table` | list | One row per entity: `[{ "entity", "profit_pct", "membership_interest", "capital_interest", "capital_pct" }]` |

Template: `{% for row in sponsor_table %}` then `{{ row.entity }}`, `{{ row.profit_pct }}`, `{{ row.membership_interest }}`, `{{ row.capital_interest }}`, `{{ row.capital_pct }}`.

---

## Sponsor Bios

| Variable | Type | Description |
|----------|------|-------------|
| `sponsors` | list | One per principal: `[{ "name", "overview", "financial_profile", "track_record", optional "title", "company" }]` |
| `sponsor` | dict | Section object; may contain `_sponsors_detail` (same as `sponsors`), `overview_narrative`, `name` |

Template: `{% for sponsor in sponsors %}` then `{{ sponsor.name }}`, `{{ sponsor.overview }}`, `{{ sponsor.financial_profile }}`, `{{ sponsor.track_record }}`.

---

## Loan Issues

| Variable | Type | Description |
|----------|------|-------------|
| `loan_issues_income_producing` | list | `[{ "asset_name", "location", "description" }]` (or `name`, `location`, `description`) |
| `loan_issues_development` | list | Same shape |
| `loan_issues_disclosure` | string | Narrative paragraph |
| `loan_issues` | dict | `{ "income_producing", "development" }` (optional; template may use flat lists above) |

Template: `{% for prop in loan_issues_income_producing %}`, `{% for prop in loan_issues_development %}`, `{{ loan_issues_disclosure }}`.

---

## Collaborative Ventures

| Variable | Type | Description |
|----------|------|-------------|
| `collaborative_ventures_list` | list | `[{ "name", "location", "description" }]` |
| `collaborative_ventures_disclosure` | string | Narrative (e.g. "The principals have collaborated on X ventures...") |
| `collaborative_ventures` | dict | Optional `{ "items": [...] }` |

Template: `{% for v in collaborative_ventures_list %}`, `{{ collaborative_ventures_disclosure }}`.

---

## Closing Disbursement

| Variable | Type | Description |
|----------|------|-------------|
| `closing_disbursement` | dict | All disbursement fields as strings: `payoff_existing_debt`, `broker_fee`, `origination_fee`, `closing_costs_title`, `lender_legal`, `borrower_legal`, `misc`, `interest_reserve`, `total_disbursements`, `sponsors_equity_at_closing`, `fairbridge_release_at_closing` |
| `disbursement_payoff` | string | Payoff existing debt |
| `disbursement_broker_fee` | string | |
| `disbursement_origination_fee` | string | |
| `disbursement_closing_costs` | string | |
| `disbursement_lender_legal` | string | |
| `disbursement_borrower_legal` | string | |
| `disbursement_misc` | string | |
| `disbursement_interest_reserve` | string | |
| `disbursement_total` | string | |
| `disbursement_sponsor_equity` | string | |
| `disbursement_fairbridge_release` | string | |
| `disbursement_rows` | list | Table rows: `[{ "label", "value" }]` for each line item |

Template: `{{ closing_disbursement.payoff_existing_debt }}`, etc., or loop `disbursement_rows`.

---

## Due Diligence

| Variable | Type | Description |
|----------|------|-------------|
| `due_diligence` | dict | `lenders_counsel`, `borrowers_counsel`, `appraisal_firm`, `appraisal_company`, `pca_firm`, `background_check` or `background_check_firm`, `environmental_firm`, `site_visit` or `site_visit_team` |

Template: `{{ due_diligence.lenders_counsel }}`, `{{ due_diligence.background_check_firm }}` (memo-filler may alias `background_check` → `background_check_firm`).

---

## Property & Valuation

| Variable | Type | Description |
|----------|------|-------------|
| `property_overview` | dict | `narrative` (or `description_narrative`), plus property fields: `name`, `property_type`, `building_sf`, `land_area_acres`, `year_built`, `occupancy_current`, `occupancy_stabilized`, `anchor_tenants`, etc. |
| `property_overview_narrative` | string | Same as `property_overview.narrative` |
| `property_value` | dict | Valuation: `as_is_value`, `as_stabilized_value`, `noi`, `cap_rate`, etc. |
| `property` | dict | Raw property section (address, name, type, SF, etc.) |

---

## Location & Market

| Variable | Type | Description |
|----------|------|-------------|
| `location_overview` | dict | `narrative` (string) |
| `market_overview` | dict | `narrative` (string) |
| `location` | dict | Section object |
| `market` | dict | Section object |

---

## Narratives (sections)

| Variable | Type | Description |
|----------|------|-------------|
| `transaction_overview` | dict | `narrative`, `deal_facts`, `loan_terms`, `key_highlights` |
| `narratives` | dict | Keys: `transaction_overview`, `loan_terms_narrative`, `property_overview`, `location_overview`, `market_overview`, `exit_strategy`, `closing_funding_narrative`, `foreclosure_assumptions`, etc. |
| `loan_terms` | dict | May have `narrative` (full loan terms narrative) |
| `zoning_entitlements` | dict | `narrative` or `summary_narrative` |
| `exit_strategy` | dict | `narrative` (string) |
| `foreclosure_assumptions` | dict | `narrative` (string) |
| `active_litigation` | dict | `cases` (list of case objects), optional `narrative` |

---

## Other Sections

| Variable | Type | Description |
|----------|------|-------------|
| `sections` | dict | All sections keyed by name (e.g. `sections.transaction_overview`, `sections.property`, `sections.sponsorship`). Templates can use `sections.*` paths. |
| `deal_highlights` | dict | `items`: list of `{ "highlight", "description" }` |
| `risks_and_mitigants` | dict | Section; often `items`: list of `{ "risk", "description", "mitigant" }` |
| `validation_flags` | dict | |
| `third_party_reports` | dict | |
| `foreclosure_analysis` | dict | `default_interest_scenario`, `note_interest_scenario` with `rows` / `items` |
| `default_interest_scenario` | dict | `rows`, `items` (list of scenario rows) |
| `note_interest_scenario` | dict | Same |
| `rent_roll` | dict | |
| `construction_budget` | dict | |
| `comps` | dict | |
| `redevelopment` | dict | |
| `closing_funding_and_reserves` | dict | Disbursement fields + optional `narrative` |

---

## Image Placeholders

Images are passed in the request as base64; memo-filler injects them by **key**. Use these exact names in the template as `{{ IMAGE_KEY }}`:

| Placeholder | Description |
|-------------|-------------|
| `IMAGE_SOURCES_USES` | Sources & uses chart |
| `IMAGE_CAPITAL_STACK_CLOSING` | Capital stack at closing |
| `IMAGE_CAPITAL_STACK_MATURITY` | Capital stack at maturity |
| `IMAGE_LOAN_TO_COST` | LTC chart |
| `IMAGE_LTV_LTC` | LTV/LTC chart |
| `IMAGE_AERIAL_MAP` | Aerial map |
| `IMAGE_LOCATION_MAP` | Location map |
| `IMAGE_REGIONAL_MAP` | Regional map |
| `IMAGE_SITE_PLAN` | Site plan |
| `IMAGE_STREET_VIEW` | Street view |
| `IMAGE_FORECLOSURE_DEFAULT` | Foreclosure scenario (default rate) |
| `IMAGE_FORECLOSURE_NOTE` | Foreclosure scenario (note rate) |

Request body: `"images": { "IMAGE_SOURCES_USES": "<base64>", ... }`.

---

## Jinja Notes

- Dicts are wrapped so `obj.items` returns a list (for `{% for k, v in obj.items %}`).
- Use `{{ variable }}` for scalars; `{% for row in list_var %}` for tables.
- Optional filters: `{{ value \| default('N/A') }}` to avoid blank output.
- Narrative fields should be **plain text** (no markdown `#`, `**`, `*`) when possible; memo-filler may strip markdown in a preprocessing step.

---

## Troubleshooting: Template syntax errors

If you see **"expected token 'end of print statement', got 'Litigation'"** (or another word):

- The **Word template** has a malformed Jinja placeholder near that word.
- Fix it in the template (.docx), not in the payload.

**Common causes:**

1. **Missing closing `}}`**  
   Placeholder is open, e.g. `{{ active_litigation.narrative` with no `}}`. The next word in the document (e.g. "Litigation") is then parsed as part of Jinja and triggers the error.  
   **Fix:** Add the closing `}}` so it reads `{{ active_litigation.narrative }}`.

2. **Spaces inside `{{ }}`**  
   Placeholder uses a space, e.g. `{{ Active Litigation }}`. Jinja expects a single expression; "Litigation" is parsed as an unexpected token.  
   **Fix:** Use a valid variable name with underscores, e.g. `{{ active_litigation.narrative }}` (no spaces).

3. **Heading/label inside placeholders**  
   Section title "Active Litigation" was put inside `{{ }}`.  
   **Fix:** Keep literal headings outside placeholders. Use a placeholder only for the narrative, e.g. `{{ active_litigation.narrative }}`.

**How to find it:** Open the template in Word, search for "Litigation" and for `{{`. Check that every `{{` has a matching `}}` and that the text inside `{{ }}` is a single variable or expression (e.g. `active_litigation.narrative`).

---

## Summary: Minimal Flat Payload (Layer 3 → /fill)

If sending **flat** Layer 3 output directly to `POST /fill`, ensure at least these top-level keys exist (lists/strings/dicts as above):

- `cover`, `deal_facts`, `loan_terms`, `leverage`, `closing_disbursement`, `due_diligence`
- `sponsor_table`, `sponsors`
- `sources_list`, `uses_list`, `sources_total`, `uses_total`
- `capital_stack_sources`, `capital_stack_uses`, `capital_stack_total`
- `loan_issues_income_producing`, `loan_issues_development`, `loan_issues_disclosure`
- `collaborative_ventures_list`, `collaborative_ventures_disclosure`
- `transaction_overview`, `property_overview`, `location_overview`, `market_overview`, `narratives`
- Optional: `deal_facts_raw`, `leverage_raw`, `loan_terms_raw` for direct `{{ property_type }}`-style access
- Optional: `sections` (nested) — if absent, flatten uses top-level keys only

This list is the **template contract** between Layer 3 output and the Word template.
