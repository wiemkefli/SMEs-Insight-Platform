# AmBank SME Insights Platform (Streamlit)

Local Streamlit app for cleaning, exploring, and reviewing red-flag signals in an SME Excel dataset (weak repayment, PD, litigation, profitability).

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

Data:
- Preferred: place your Excel at `data/SME_Dataset.xlsx`
- Alternative: upload a `.xlsx` from the app sidebar

## Requirements

- Python 3.10+
- Works offline (no internet required after deps installed)
- Recommended: install in a fresh virtual environment to avoid conflicts with globally-installed packages.

## Project structure

```text
app.py
requirements.txt
README.md
src/
  load_clean.py
  metrics.py
  charts.py
  red_flags.py
config/
  .gitkeep
data/
  .gitkeep
```

## How it works

### 1) Data loading

- If `data/SME_Dataset.xlsx` exists, the app loads it automatically.
- Otherwise, the sidebar prompts you to upload a `.xlsx`.

### 2) Column mapping (auto + manual)

The app operates on a canonical schema (internal fields):

- Optional: `sme_id`
- Required: `industry`, `region`, `loan_amount`, `loan_purpose`, `employee_count`,
  `probability_of_default`, `net_margin`, `repayment_status`, `litigation_status`

Mapping behavior:
- Auto-detection uses normalized column-name matching with synonyms + fuzzy matching.
- If any required canonical field is not mapped, a conditional tab appears: **Column Mapping / Data Quality**.
- You can manually map columns via dropdowns and click **Save mapping** to persist it to `config/mapping.json`.
  (This file is not created until you save.)
  For GitHub, `config/mapping.json` is ignored by `.gitignore` (it’s usually machine/user-specific).

### 3) Cleaning & transformations

The cleaning is deterministic and runs on every load:

- Column names are normalized to `snake_case` on read.
- Categorical fields are trimmed, whitespace-normalized, and standardized (title case).
- Missing categoricals are filled with `Unknown`.
- Numeric fields are coerced to float (commas/currency/extra symbols stripped; invalid values become NaN):
  `loan_amount`, `probability_of_default`, `net_margin`, `employee_count`
- Warnings:
  - If numeric conversion introduces >30% NaNs for a key numeric field, the app shows a warning.

Derived fields:
- `size_bucket` from `employee_count`:
  - `<50`, `50-149`, `150+`, `Unknown`
- `margin_bucket` from `net_margin`:
  - Quartiles (`Q1 (Low)`..`Q4 (High)`) if >= 20 non-null values
  - Else fixed bins: `<=0`, `0-5`, `5-10`, `10+`
- `is_weak_repayment`:
  - True if `repayment_status` contains any of `{weak, poor, delinquent, late, default}` (case-insensitive)
- `is_litigation`:
  - Boolean derived from `litigation_status` (yes/no, y/n, true/false, 1/0, or “litig*” text)
  - If `litigation_status` is not mapped, `is_litigation` defaults to `False` and litigation KPIs will be minimal.

### 4) Filtering (sidebar)

Optional filters for `industry`, `region`, `loan_purpose`, and `size_bucket` apply to Overview, Red Flags, and Export.

## Dashboard outputs

### KPIs (metric cards)
Computed from the filtered dataset:
- Number of SMEs
- Total loan amount (sum)
- Median loan amount
- Average PD
- Weak repayment rate
- Litigation rate

### Charts
- Overview: weak repayment rate by `industry` and `region`.
- Red Flags: bar chart of `red_flag_count` by `financing_id` (paged for large datasets).

## Exports

Available in **Export** tab:
- Download selected data (CSV) (respects sidebar filters)
- Download cleaned full data (CSV)

## Troubleshooting

### File not loading

- Confirm the dataset is a valid `.xlsx`.
- If using the default path, ensure it exists at `data/SME_Dataset.xlsx`.

## Run commands

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
pip install -U -r requirements.txt
streamlit run app.py
```
