# Functional Requirements Specification (FRS)
**Project:** AmBank SME Insights Platform (AmDigital Track – Data Exploration & Insights)  
**Target:** Build a Streamlit Python app for dataset cleaning, exploration, risk insights, and dashboard visuals (MVP in 2 days).  
**Primary “bank angle”:** Risk detection (repayment weakness + PD + litigation + profitability signals).

---

## 1) Objectives
1. Clean and explore the SME dataset from Excel.
2. Identify trends across **industry**, **region**, **business size**, and **loan purpose**.
3. Highlight **risk-relevant insights** for decision-making.
4. Provide a simple dashboard with **3–5 clear visuals** (locked to 5 default visuals below).
5. Support exporting of filtered data and chart outputs for slide-deck use.

---

## 2) Scope
### In-scope
- Local Streamlit web app (single-user) running on a laptop.
- Load SME dataset from `SME_Dataset.xlsx` (default) or allow upload.
- Auto cleaning + standardization.
- Filtering by key segments.
- KPIs + 5 visuals + auto insight bullets.
- Export: filtered dataset CSV; chart export (PNG preferred, HTML fallback).

### Out-of-scope (MVP)
- Database storage (use in-memory pandas).
- Real-time data updates.

---

## 3) Users & Use Cases
### Primary user
- AmDigital team member preparing insights for a case study pitch deck.

### Use cases
- **UC1:** Load dataset and view cleaned overview.
- **UC2:** Filter by industry/region/size/purpose to see segment-specific KPIs.
- **UC3:** Identify risk clusters (high weak rate / high PD / negative margins / litigation).
- **UC4:** Export charts and filtered data for slides.

---

## 4) Data Requirements
### 4.1 Input
- Excel file with one main table containing SME-level rows.
- Default path: `data/SME_Dataset.xlsx`
- Alternative: Streamlit file uploader.

### 4.2 Required logical fields (canonical schema)
The app must operate using the canonical fields below. If the dataset uses different column names, the app must map them via **(a) auto-detection** and **(b) a manual mapping UI fallback**.

#### Canonical fields (must be mapped)
- `sme_id` (optional but recommended)
- `industry`
- `region`
- `loan_amount`
- `loan_purpose`
- `employee_count` (or any size indicator)
- `probability_of_default` (PD)
- `net_margin`
- `repayment_status` (must allow determining “Weak” vs others)
- `litigation_status` (Yes/No or boolean)

### Column auto-detection rules
Implement fuzzy matching on lowercased, stripped column names. Support synonyms like:

- industry: `industry`, `sector`, `business_industry`
- region: `region`, `state`, `location`
- loan_amount: `loan_amount`, `amount`, `financing_amount`, `loan_amt`
- loan_purpose: `loan_purpose`, `purpose`, `facility_purpose`
- employee_count: `employees`, `employee_count`, `headcount`, `no_of_employees`
- PD: `pd`, `probability_of_default`, `default_probability`, `risk_score` *(if risk_score is used, still label as PD in UI)*
- net_margin: `net_margin`, `margin`, `profit_margin`, `net_profit_margin`
- repayment_status: `repayment`, `repayment_status`, `payment_status`, `repayment_behavior`
- litigation_status: `litigation`, `in_litigation`, `legal`, `legal_status`

### Manual mapping fallback (must-have)
If any canonical field cannot be auto-mapped:
- Show a **Column Mapping** screen to let user select dataset columns for each canonical field.
- Persist mapping in a local `config/mapping.json` for future runs.

---

## 5) Data Cleaning & Transformation Requirements
### 5.1 Standardization
- Convert column names to snake_case internally.
- Trim whitespace and normalize casing for categoricals.

### 5.2 Type enforcement
- `loan_amount`, `probability_of_default`, `net_margin`, `employee_count` must be numeric.
  - Strip currency symbols and commas.
  - Coerce errors to NaN and record count of coercions.
- `litigation_status` must be boolean-like:
  - Accept: Yes/No, Y/N, True/False, 1/0.
- `repayment_status` must be categorical; app must derive:
  - `repayment_flag` ∈ {`Weak`, `Not Weak`} using rules below.

### 5.3 Missing value handling
- Categorical: fill missing with `"Unknown"`.
- Numeric: keep NaN; computations must handle NaN safely (ignore NaNs).
- Show a **Data Quality** box: % missing for key fields.

### 5.4 Derived fields (must implement)
- `size_bucket` derived from `employee_count`:
  - `<50`, `50–149`, `150+`
  - If employee_count missing, bucket = `"Unknown"`
- `margin_bucket` derived from `net_margin`:
  - Prefer quartiles on non-null values: Q1–Q4 labels.
  - If insufficient non-null values (<20), use bins: `<=0`, `0–5`, `5–10`, `10+` (numeric bins).
- `is_weak_repayment` boolean:
  - True if repayment_status normalized equals `"weak"` OR matches a list: {weak, poor, delinquent, late, default} (case-insensitive).
- `is_litigation` boolean from litigation_status mapping.

---

## 6) Filtering Requirements (UI)
Filters must apply to all KPIs, visuals, and insights.

### 6.1 Sidebar filters
- Multi-select `industry`
- Multi-select `region`
- Multi-select `size_bucket`
- Multi-select `loan_purpose`
- Toggle: “Only Weak repayment” (filters `is_weak_repayment=True`)
- Toggle: “Only Litigation” (filters `is_litigation=True`)
- Button: “Reset filters”

### 6.2 Default selections
- Default: all values selected (no filter applied).

---

## 7) KPI Requirements
Compute from the filtered dataset:
- `num_smes` = count of rows
- `total_loan_amount` = sum of loan_amount (ignore NaN)
- `median_loan_amount` = median of loan_amount
- `avg_pd` = mean(probability_of_default)
- `weak_repayment_rate` = mean(is_weak_repayment) as %
- `litigation_rate` = mean(is_litigation) as %

KPIs must display as Streamlit metric cards.

---

## 8) Visual Requirements (locked set of 5)
All charts must update based on filters. Use Plotly for interactivity.

### V1: Weak repayment rate by Industry
- Bar chart: x=industry, y=weak_repayment_rate (%)
- Sort descending by weak rate
- Hover: (#SMEs, weak count, weak rate)

### V2: Average PD by Loan Purpose
- Bar chart: x=loan_purpose, y=avg_pd
- Sort descending avg_pd

### V3: Weak repayment rate by Region
- Bar chart: x=region, y=weak_repayment_rate (%)
- Sort descending

### V4: Net Margin vs PD
- Scatter plot: x=net_margin, y=probability_of_default
- Color or symbol by `is_weak_repayment`
- Optional: shape by `is_litigation`
- Hover must show: SME id/name (if available), industry, region, loan_amount, repayment_status, litigation

### V5: Average PD by Business Size Bucket
- Bar chart: x=size_bucket, y=avg_pd
- Order buckets: `<50`, `50–149`, `150+`, `Unknown`

---

## 9) Insight Generation Requirements (Risk Angle)
The app must produce auto-generated insight bullets (6–10 bullets) based on the filtered dataset.

### 9.1 Required insight types
- Top 3 industries by weak repayment rate (include rates and counts)
- Top 3 regions by weak repayment rate (include rates and counts)
- Loan purposes with highest avg PD (top 3)
- Business size bucket with highest avg PD
- Relationship callout:
  - Share of SMEs with net_margin <= 0
  - Weak repayment rate among net_margin <= 0
- Litigation prevalence overall and in high-risk segments (if litigation exists)

### 9.2 Output format
- Bulleted list, banker-friendly phrasing.
- If filtered dataset too small (<10 rows), show “insufficient data for reliable ranking” and switch to simpler bullets.

---

## 10) Export Requirements
### 10.1 Data export
- Button: “Download filtered data (CSV)”
- Button: “Download cleaned full data (CSV)”

### 10.2 Chart export
**Preferred:**
- Export each chart as PNG (requires `kaleido` for Plotly).

**Fallback:**
- Export charts as HTML files zipped together.

### 10.3 Insights export (optional but recommended)
- Generate a simple one-page HTML report containing:
  - KPIs
  - The 5 charts (embedded images or links)
  - Insight bullets
- Download as HTML.

---

## 11) App Screens / Navigation
Single Streamlit app with tabs:

1. **Overview**
   - KPI row
   - V1 + V3 (industry + region)
   - Key takeaways panel (top 3 bullets)

2. **Segments**
   - V1, V3, V5

3. **Risk Drivers**
   - V2, V4
   - Data quality mini panel

4. **Insights & Export**
   - Full insight bullets
   - Download buttons (CSV + charts + report)

5. **Data Quality / Column Mapping** *(conditional)*
   - Only shown if mapping incomplete or errors detected
   - Shows mapping selectors + missingness summary

---

## 12) Non-Functional Requirements
- Runs locally on Windows/Mac.
- Cold start to first render: <10 seconds for ~200–5,000 rows.
- Deterministic cleaning (same input → same output).
- No internet required.
- No sensitive data persistence except optional `config/mapping.json`.
- Logging: warnings for coercions/missing required fields.

---

## 13) Technical Constraints & Libraries
- Python 3.10+
- Required libs:
  - `streamlit`, `pandas`, `numpy`, `openpyxl`, `plotly`, `kaleido`
- Packaging:
  - `requirements.txt`
- Suggested structure:
  - `app.py`
  - `src/load_clean.py` (load + map + clean)
  - `src/metrics.py` (KPIs)
  - `src/charts.py` (Plotly figs)
  - `src/insights.py` (text generation)
  - `config/mapping.json` (optional persisted mapping)
  - `data/SME_Dataset.xlsx`

---

## 14) Error Handling & Edge Cases
- If file missing: show uploader and instructions.
- If required field unmapped: open Column Mapping screen.
- If numeric conversion fails heavily (>30% NaN introduced): show warning.
- If filters reduce dataset to 0 rows: show “No data for current filters” and render empty states.
- If kaleido not available: fall back to HTML export and display message.

---

## 15) Acceptance Criteria (MVP)
1. App launches with `streamlit run app.py`.
2. Dataset loads and cleans without crashing.
3. Sidebar filters update all KPIs, charts, and insights.
4. All 5 visuals render correctly and are interpretable.
5. “Download filtered data CSV” works.
6. “Export charts” produces files (PNG preferred; HTML fallback acceptable).
7. Insight bullets reflect current filters and mention concrete segment names + rates/counts.

---

## 16) Test Cases (minimum)
- **TC1:** Load default Excel → overview renders KPIs and charts.
- **TC2:** Apply industry filter → KPI and V1 update (counts shrink, rates recompute).
- **TC3:** Toggle “Only Weak” → weak rate becomes 100% (or near if definition differs).
- **TC4:** Missing PD column → mapping UI triggers.
- **TC5:** Export filtered CSV → file downloads and contains only filtered rows.
- **TC6:** Export charts → outputs generated; open one image/HTML verifies chart.
