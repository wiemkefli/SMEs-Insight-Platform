# AmBank SME Insights Platform — Explanation (for stakeholders)

## What this app is
The **AmBank SME Insights Platform** is a **local, offline Streamlit dashboard** that helps analysts quickly **clean**, **standardize**, and **explore** an SME Excel dataset and generate **risk-focused insights** to support credit/risk discussions and pitch-deck storytelling.

It is designed as an MVP for rapid analysis: load an SME dataset, apply consistent cleaning rules, and surface key patterns around:
- **Weak repayment signals**
- **Probability of Default (PD)**
- **Litigation indicators**
- **Profitability (net margin)**

## What it does (end-to-end)
1. **Loads SME data from Excel**
   - Default: `data/SME_Dataset.xlsx`
   - Alternative: upload a `.xlsx` from the sidebar

2. **Maps your dataset columns to a standard (canonical) schema**
   - The app tries to auto-detect column mappings (based on common synonyms and fuzzy matching).
   - If anything important is missing, a **Column Mapping** screen lets you map fields manually.
   - The mapping can be saved to `config/mapping.json` so future runs “just work”.

3. **Cleans and standardizes data consistently**
   - Normalizes column names and trims/standardizes categorical values.
   - Coerces numeric fields (e.g., loan amount, PD, margin, employee count) while handling symbols/commas.
   - Shows basic **data quality warnings** if key numeric fields become too sparse after conversion.

4. **Creates derived portfolio features**
    - `size_bucket` from employee count: `<50`, `50-149`, `150+`, `Unknown`
    - `margin_bucket` from net margin (quartiles when enough data; otherwise fixed bins)
    - `is_weak_repayment` flag from repayment status text (e.g., weak/poor/delinquent/late/default)
    - `is_litigation` flag from litigation-like fields (yes/no, boolean, 1/0, or “litig*” text)

5. **Produces dashboard outputs**
   - **KPI cards**:
     - # SMEs, total loan amount, median loan amount, average PD, weak repayment rate, litigation rate
   - **Red Flags**:
     - Highlights companies breaching simple ratio thresholds and provides a chart + table for review.

6. **Exports for reporting / slide decks**
   - Download cleaned data (CSV)

## Red Flags (financial ratios)
The app includes a **Red Flags** page to highlight companies breaching simple ratio thresholds:
- Net ratio < 8
- Current ratio < 1.8
- Gearing ratio < 0.85
- Interest coverage < 15

The page is set up for your dataset naming: it uses `financing_id` as the company identifier and `net_margin` for the first threshold rule (net_margin < 8), alongside `current_ratio`, `gearing_ratio`, and `interest_coverage` if present. It provides a Financing ID search and generates a bar chart of `red_flag_count` plus a detailed company table (raw ratios + boolean flags).

## What data it expects
The app operates on a canonical SME schema (your Excel can use different names; mapping handles that):
- Optional: `sme_id`
- Required: `industry`, `region`, `loan_amount`, `loan_purpose`, `employee_count`,
  `probability_of_default`, `net_margin`, `repayment_status`, `litigation_status`

## Why this is useful for AmBank
- **Fast standardization**: reduces manual cleaning and “one-off” Excel work.
- **Portfolio risk visibility**: quickly highlights distributions of PD/margins and companies breaching simple ratio rules.
- **Portable & offline**: runs locally; no database required; suitable for laptop-based demos and case-study work.

## What it is NOT (current MVP boundaries)
- Not a production credit decisioning system.
- Not connected to databases or real-time feeds (uses in-memory pandas).
- Not a model training tool; it **visualizes and summarizes** provided PD and status fields rather than building PD models.

## How to run (local)
1. `pip install -r requirements.txt`
2. `streamlit run app.py`
3. Put your Excel at `data/SME_Dataset.xlsx` or upload it in the app.

## Suggested demo flow (2–3 minutes)
1. Load dataset → confirm mapping and data quality box.
2. Show KPI cards for full portfolio.
3. Filter to a high-risk industry/region and toggle **Only Weak repayment**.
4. Use the scatter (Margin vs PD) to highlight profitability stress vs risk.
5. Export filtered CSV and chart bundle for slide use.
