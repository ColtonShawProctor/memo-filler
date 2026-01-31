/**
 * Type definitions for the deal memo input format.
 * Input is an array of deal objects: DealInput[]
 */

export interface DealCover {
  property_address: string;
  credit_committee: string;
  underwriting_team: string;
  date: string;
}

export interface DealFacts {
  property_type: string;
  loan_purpose: string;
  loan_amount: string;
  source: string;
}

export interface InterestRateBlock {
  description: string;
  default_rate: string;
}

export interface LoanTerms {
  interest_rate: InterestRateBlock;
  origination_fee: string;
  exit_fee: string;
  prepayment: string;
  guaranty: string;
  collateral: string;
}

export interface Leverage {
  fb_ltc_at_closing: string;
  ltc_at_maturity: string;
  ltv_at_closing: string;
  ltv_at_maturity: string;
  ltpp: string;
  debt_yield_fully_drawn: string;
}

export interface SponsorInternalSplitItem {
  principal: string;
  share_of_interest_pct: number;
}

export interface SponsorTableRow {
  entity: string;
  profit_percentage_interest: string;
  membership_interest: number;
  capital_interest_amount: number | null;
  capital_interest_percentage: string | null;
  internal_split?: SponsorInternalSplitItem[];
}

export interface GuarantorLenderRequirements {
  minimum_net_worth: number;
  minimum_liquidity_securities: number;
}

export interface SponsorGuarantors {
  names: string[];
  guarantees: string[];
  combined_net_worth: number;
  combined_cash_position: number;
  combined_securities_holdings: number;
  lender_requirements: GuarantorLenderRequirements;
}

export interface PrincipalFinancialProfile {
  credit_score?: number;
  credit_score_date?: string;
  net_worth?: number;
  liquid_assets?: number;
  liquid_assets_composition?: string;
  sreo?: Record<string, unknown> | string;
}

export interface PrincipalHistoricalLoanIssue {
  property_name?: string;
  description?: string;
  loan_amount?: number;
  loan_type?: string;
  issue?: string;
  resolution?: string;
  ownership_interest_pct?: number;
}

export interface PrincipalHistoricalDevelopment {
  project_name?: string;
  description?: string;
  loan_amount?: number;
  issue?: string;
  resolution?: string;
  ownership_interest_pct?: number;
  parcels?: string[];
}

export interface PrincipalHistoricalLoanIssues {
  period?: string;
  income_producing_properties?: PrincipalHistoricalLoanIssue[];
  development_properties?: PrincipalHistoricalDevelopment[];
}

export interface Principal {
  name: string;
  title?: string;
  company?: string;
  experience?: string;
  notable_projects?: string[];
  civic_involvement?: string[];
  financial_profile?: PrincipalFinancialProfile;
  historical_loan_issues?: PrincipalHistoricalLoanIssues;
}

export interface Sponsor {
  table: SponsorTableRow[];
  borrowing_entity: string;
  guarantors: SponsorGuarantors;
  principals: Principal[];
}

export interface SourcesUsesItem {
  item: string;
  amount: number;
  rate_pct?: number;
}

export interface SourcesUsesCategory {
  category: string;
  items: SourcesUsesItem[];
}

export interface SourcesUsesTable {
  title: string;
  sources: SourcesUsesItem[];
  total_sources: number;
  uses: SourcesUsesCategory[];
  total_uses: number;
  notes: string[];
}

export interface SourcesAndUses {
  table: SourcesUsesTable;
  total_project_cost: string;
  equity_at_closing: string;
  equity_already_invested: string;
}

export interface ClosingDisbursement {
  payoff_existing_debt: string;
  broker_fee: string;
  origination_fee: string;
  closing_costs_title: string;
  lender_legal: string;
  borrower_legal: string;
  misc: string;
  interest_reserve: string;
  total_disbursements: string;
  sponsors_equity_at_closing: string;
  fairbridge_release_at_closing: string;
}

export interface CapitalStack {
  table: SourcesUsesTable;
}

export interface DueDiligence {
  lenders_counsel: string | null;
  borrowers_counsel: string | null;
  appraisal_firm: string;
  appraisal_company: string;
  pca_firm: string | null;
  background_check_firm: string | null;
  environmental_firm: string;
  site_visit_team: string | null;
}

export interface PropertyAddress {
  street: string;
  city: string;
  county: string;
  state: string;
  zip: string;
}

export interface Property {
  name: string;
  address: PropertyAddress;
  property_type: string;
  year_built: number | number[];
  year_renovated?: number;
  land_area_acres: number;
  land_area_sf: number;
  building_sf: number;
  num_buildings: number;
  num_stories: number;
  occupancy_current: number;
  occupancy_stabilized: number;
  anchor_tenants: string;
  parking_spaces: number;
  parking_ratio: number;
  condition: string;
  parcel_numbers: string;
}

export interface ValuationApproaches {
  [key: string]: unknown;
}

export interface MarketValueConclusion {
  appraisal_premise: string;
  interest_appraised?: string;
  date_of_value?: string;
  value_conclusion: number;
}

export interface Valuation {
  as_is_value: string;
  as_stabilized_value: string;
  cap_rate: string;
  discount_rate: string;
  terminal_cap_rate: string;
  noi: string;
  effective_gross_income: string;
  operating_expenses: string;
  expense_ratio: string;
  valuation_approaches?: ValuationApproaches;
  market_value_conclusions?: MarketValueConclusion[];
}

export interface LiveLocalAct {
  description?: string;
  tax_credit_program?: string;
  land_use_entitlements_summary?: Record<string, string>;
  subject_applicability?: string;
}

export interface Zoning {
  zone_code: string;
  permitted_uses: string;
  live_local_act: LiveLocalAct;
  highest_best_use_vacant: string;
  highest_best_use_improved: string;
}

export interface Redevelopment {
  description: string;
  proposed_units: number;
  demolition_area_sf: number;
  land_area_for_multifamily: number;
  estimated_demolition_cost: string;
}

export interface EnvironmentalHistoricalRec {
  site: string;
  address: string;
  description: string;
}

export interface Environmental {
  firm: string;
  report_date: string;
  property_address: string;
  findings_summary: string;
  historical_recs: EnvironmentalHistoricalRec[];
  recognized_environmental_conditions: unknown[];
  controlled_recs: unknown[];
  assessment_standard: string;
}

export interface RentRoll {
  occupancy_rate: string;
  total_monthly_rent: string;
  total_annual_rent: string;
}

export interface FairbridgeCounselAnalysis {
  counsel_firm: string;
  filing_date: string;
  counts: string;
  damage_theories: string[];
  relief_sought: string;
  potential_damages: string;
  trial_period: string;
}

export interface FairbridgeHoldback {
  amount: number;
  sponsor_settlement_estimate: string;
  additional_requirements: string;
}

export interface ActiveLitigationCase {
  case: string;
  complaint_background: string;
  sponsor_explanation: string;
  fairbridge_counsel_analysis: FairbridgeCounselAnalysis;
  fairbridge_holdback: FairbridgeHoldback;
}

export interface ActiveLitigation {
  exists: boolean;
  cases: {
    case?: string;
    complaint_background?: string;
    sponsor_explanation?: string;
    fairbridge_counsel_analysis?: FairbridgeCounselAnalysis;
    fairbridge_holdback?: FairbridgeHoldback;
  };
}

export interface SalesComp {
  comparable_sale: string;
  year_built: number;
  tax_year: number;
  assessors_market_value: number;
  date_of_sale: string;
  sales_price: number;
  av_ratio_percent: number;
}

export interface Comps {
  sales_comps: SalesComp[];
}

export interface ConstructionBudget {
  total_budget: string;
  hard_costs: string;
  soft_costs: string;
}

export interface RiskMitigantItem {
  risk: string;
  description: string;
  mitigant: string;
  sub_risks?: string[];
}

export interface RisksAndMitigants {
  items: RiskMitigantItem[];
}

export interface DealHighlightItem {
  highlight: string;
  description: string;
}

export interface DealHighlights {
  items: DealHighlightItem[];
}

export interface LoanIssues {
  income_producing: unknown;
  development: unknown;
}

export interface Narratives {
  transaction_overview?: string;
  loan_terms_narrative?: string;
  property_overview?: string;
  location_overview?: string;
  market_overview?: string;
  appraisal_analysis?: string;
  zoning_narrative?: string;
  exit_strategy?: string;
  environmental_narrative?: string;
  pca_narrative?: string;
  closing_funding_narrative?: string;
  foreclosure_assumptions?: string;
  active_litigation_narrative?: string;
  sponsor_narrative?: string;
  risks_mitigants_narrative?: string;
  deal_highlights_narrative?: string;
  property_value_narrative?: string;
  comps_narrative?: string;
  [key: string]: string | undefined;
}

/** Single deal object; API/pipeline input is an array of these. */
export interface DealInput {
  deal_id: string;
  deal_folder: string;
  generated_at: string;
  cover: DealCover;
  deal_facts: DealFacts;
  loan_terms: LoanTerms;
  leverage: Leverage;
  sponsor: Sponsor;
  sources_and_uses: SourcesAndUses;
  closing_disbursement: ClosingDisbursement;
  capital_stack: CapitalStack;
  due_diligence: DueDiligence;
  property: Property;
  valuation: Valuation;
  zoning: Zoning;
  redevelopment: Redevelopment;
  environmental: Environmental;
  rent_roll: RentRoll;
  active_litigation: ActiveLitigation;
  comps: Comps;
  construction_budget: ConstructionBudget;
  risks_and_mitigants: RisksAndMitigants;
  deal_highlights: DealHighlights;
  collaborative_ventures: Record<string, unknown>;
  loan_issues: LoanIssues;
  narratives: Narratives;
}

/** Root input: array of deal objects. */
export type DealInputPayload = DealInput[];
