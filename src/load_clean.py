from __future__ import annotations

import json
import re
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd


CANONICAL_FIELDS: list[str] = [
    "sme_id",  # optional
    "industry",
    "region",
    "loan_amount",
    "loan_purpose",
    "employee_count",
    "probability_of_default",
    "net_margin",
    "repayment_status",
    "litigation_status",
]

REQUIRED_CANONICAL_FIELDS: list[str] = [f for f in CANONICAL_FIELDS if f != "sme_id"]


SYNONYMS: dict[str, set[str]] = {
    "sme_id": {"sme_id", "smeid", "id", "customer_id", "client_id", "account_id"},
    "industry": {"industry", "sector", "business_industry"},
    "region": {"region", "state", "location"},
    "loan_amount": {"loan_amount", "amount", "financing_amount", "loan_amt", "facility_amount"},
    "loan_purpose": {"loan_purpose", "purpose", "facility_purpose"},
    "employee_count": {"employees", "employee_count", "headcount", "no_of_employees", "staff_count"},
    "probability_of_default": {
        "pd",
        "probability_of_default",
        "default_probability",
        "risk_score",
        "prob_default",
    },
    "net_margin": {"net_margin", "margin", "profit_margin", "net_profit_margin"},
    "repayment_status": {"repayment", "repayment_status", "payment_status", "repayment_behavior"},
    "litigation_status": {"litigation", "in_litigation", "legal", "legal_status", "legal_flag"},
}


KEY_NUMERIC_FIELDS: list[str] = [
    "loan_amount",
    "probability_of_default",
    "net_margin",
    "employee_count",
]


def ensure_dirs() -> None:
    Path("config").mkdir(parents=True, exist_ok=True)
    Path("data").mkdir(parents=True, exist_ok=True)


def _snake_case(s: str) -> str:
    s = str(s).strip()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s.lower() if s else "col"


def snake_case_columns(columns: list[Any]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for col in columns:
        base = _snake_case(str(col))
        if base in seen:
            seen[base] += 1
            out.append(f"{base}_{seen[base]}")
        else:
            seen[base] = 1
            out.append(base)
    return out


def normalize_token(s: str) -> str:
    s = str(s).strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def load_mapping_json(path: Path) -> Optional[dict[str, Optional[str]]]:
    try:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        out: dict[str, Optional[str]] = {}
        for k, v in data.items():
            if k in CANONICAL_FIELDS and (isinstance(v, str) or v is None):
                out[k] = v
        return out
    except Exception:
        return None


def save_mapping_json(mapping: dict[str, Optional[str]], path: Path) -> None:
    safe: dict[str, Optional[str]] = {k: mapping.get(k) for k in CANONICAL_FIELDS}
    path.write_text(json.dumps(safe, indent=2, ensure_ascii=False), encoding="utf-8")


def validate_mapping_for_columns(
    mapping: dict[str, Optional[str]], columns: list[str]
) -> dict[str, Optional[str]]:
    cols = set(columns)
    validated: dict[str, Optional[str]] = {}
    for canonical in CANONICAL_FIELDS:
        v = mapping.get(canonical)
        if canonical == "sme_id" and (v is None or v in cols):
            validated[canonical] = v
            continue
        if isinstance(v, str) and v in cols:
            validated[canonical] = v
    return validated


def auto_detect_mapping(columns: list[str]) -> dict[str, Optional[str]]:
    """
    Auto-detect a mapping from dataset columns to canonical fields using:
    1) exact match on normalized tokens + synonyms
    2) fuzzy similarity via SequenceMatcher ratio
    """
    from difflib import SequenceMatcher

    normalized_cols = {c: normalize_token(c) for c in columns}
    available = set(columns)
    mapping: dict[str, Optional[str]] = {k: None for k in CANONICAL_FIELDS}

    for canonical, syns in SYNONYMS.items():
        for col in columns:
            if normalized_cols[col] in syns:
                mapping[canonical] = col
                available.discard(col)
                break

    def score(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()

    for canonical in CANONICAL_FIELDS:
        if mapping[canonical] is not None:
            continue
        best_col = None
        best_score = 0.0
        targets = SYNONYMS.get(canonical, {canonical})
        for col in list(available):
            col_token = normalized_cols[col]
            s = max(score(col_token, t) for t in targets)
            if s > best_score:
                best_score = s
                best_col = col
        threshold = 0.74 if canonical != "sme_id" else 0.78
        if best_col is not None and best_score >= threshold:
            mapping[canonical] = best_col
            available.remove(best_col)

    return mapping


def load_excel_to_dataframe(source: str | bytes, filename: str | None = None) -> pd.DataFrame:
    """
    Load an Excel file and normalize columns to snake_case.

    Handles common real-world Excel layouts where:
    - Row 1 is a sheet title, and the actual header is on a later row
    - Column headers are present as the first data row (causing many "Unnamed:" columns)
    """
    # For uploaded bytes, create fresh buffers per read (pandas advances file pointers).
    if isinstance(source, bytes):
        bytes_data = source

        def _src() -> BytesIO:
            return BytesIO(bytes_data)

        excel_source: Any = _src()
        excel_source_factory = _src
    else:
        excel_source = source

        def _src() -> Any:
            return source

        excel_source_factory = _src

    # Pick the most likely "main table" sheet (largest non-empty area).
    xf = pd.ExcelFile(excel_source_factory(), engine="openpyxl")
    best_sheet = xf.sheet_names[0] if xf.sheet_names else 0
    best_score = -1

    for sheet in xf.sheet_names:
        preview = pd.read_excel(excel_source_factory(), sheet_name=sheet, header=None, engine="openpyxl", nrows=60)
        preview = preview.dropna(axis=0, how="all").dropna(axis=1, how="all")
        if preview.shape[0] < 5 or preview.shape[1] < 5:
            continue
        score = int(preview.shape[0] * preview.shape[1])
        if score > best_score:
            best_score = score
            best_sheet = sheet

    # Read with header=None first to detect header row.
    raw = pd.read_excel(excel_source_factory(), sheet_name=best_sheet, header=None, engine="openpyxl")
    raw = raw.dropna(axis=0, how="all").dropna(axis=1, how="all")

    # If normal header parsing would work (few unnamed columns), keep it simple.
    # Otherwise, infer the header row by matching against known tokens/synonyms.
    header_tokens = set()
    for syns in SYNONYMS.values():
        header_tokens |= set(syns)
    header_tokens |= {normalize_token(c) for c in CANONICAL_FIELDS}

    def header_row_score(row: pd.Series) -> tuple[int, int]:
        vals = [str(v) for v in row.tolist() if pd.notna(v) and str(v).strip() != ""]
        norm = [normalize_token(v) for v in vals]
        match = sum(1 for t in norm if t in header_tokens)
        non_null = len(vals)
        return match, non_null

    # Choose header row among first 25 rows.
    best_idx = 0
    best = (-1, -1)
    limit = min(25, raw.shape[0])
    for i in range(limit):
        s = header_row_score(raw.iloc[i])
        # Prefer more matches, then more non-null cells.
        if s > best:
            best = s
            best_idx = i

    # Fallback: if no matches at all, try using the first row that looks like a real header.
    if best[0] <= 0:
        # Pick first row with many non-nulls (likely header), otherwise 0.
        for i in range(limit):
            non_null = int(raw.iloc[i].notna().sum())
            if non_null >= max(5, int(raw.shape[1] * 0.5)):
                best_idx = i
                break

    header = raw.iloc[best_idx].astype(str).tolist()
    data = raw.iloc[best_idx + 1 :].copy()
    data.columns = snake_case_columns(header)
    data = data.reset_index(drop=True)
    return data


def _normalize_category(series: pd.Series, title_case: bool = True) -> pd.Series:
    s = series.astype("string").fillna("Unknown")
    s = s.str.strip().replace("", "Unknown")
    s = s.str.replace(r"\s+", " ", regex=True)
    if title_case:
        s = s.str.lower().str.title()
        s = s.replace({"Unknown": "Unknown"})
    return s


_NUMERIC_STRIP_RE = re.compile(r"[^0-9\.\-\+eE]+")


def _coerce_numeric(series: pd.Series) -> tuple[pd.Series, dict[str, Any]]:
    """
    Strip currency symbols/commas and coerce to float.
    Returns numeric series and stats about coercion.
    """
    original = series.copy()
    original_nonempty = original.notna() & original.astype(str).str.strip().ne("")

    cleaned = (
        original.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("RM", "", regex=False)
        .str.replace("%", "", regex=False)
    )
    cleaned = cleaned.str.replace(_NUMERIC_STRIP_RE, "", regex=True).str.strip()
    cleaned = cleaned.mask(cleaned.isin(["", "nan", "None"]), np.nan)

    numeric = pd.to_numeric(cleaned, errors="coerce").astype("float64")
    introduced_nan = int((original_nonempty & numeric.isna()).sum())
    introduced_ratio = float(introduced_nan) / float(len(series)) if len(series) else 0.0
    return numeric, {"introduced_nan": introduced_nan, "introduced_nan_ratio": introduced_ratio}


def _coerce_litigation_to_bool(series: pd.Series) -> pd.Series:
    s = series.astype("string").fillna("Unknown").str.strip().str.lower()
    truthy = {"yes", "y", "true", "1"}
    falsy = {"no", "n", "false", "0"}
    out = pd.Series(False, index=series.index, dtype="bool")
    out = out | s.isin(truthy)
    out = out & ~s.isin(falsy)
    out = out | s.str.contains("litig", na=False)
    out = out & ~s.str.contains(r"\b(?:no|not)\b", na=False)
    return out.fillna(False)


def prepare_clean_dataset(
    raw_df: pd.DataFrame, mapping: dict[str, Optional[str]]
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Apply mapping, clean canonical fields, compute derived fields, and return (cleaned_df, quality).
    """
    df = raw_df.copy()
    quality: dict[str, Any] = {"warnings": []}

    mapping = {k: mapping.get(k) for k in CANONICAL_FIELDS}

    missing_required = [f for f in REQUIRED_CANONICAL_FIELDS if not mapping.get(f)]
    quality["mapping_incomplete"] = bool(missing_required)
    quality["missing_required_fields"] = missing_required

    # Create canonical columns (copy from mapped source columns).
    # If a canonical column already exists in the dataset and mapping is missing/invalid,
    # keep the existing column rather than overwriting it with NA.
    for canonical, source_col in mapping.items():
        if source_col and source_col in df.columns:
            df[canonical] = df[source_col]
        elif canonical in df.columns:
            continue
        else:
            df[canonical] = pd.NA

    litigation_mapped = bool(mapping.get("litigation_status"))

    for cat_col in ["industry", "region", "loan_purpose", "repayment_status", "litigation_status"]:
        df[cat_col] = _normalize_category(df[cat_col], title_case=True)

    coercion_stats: dict[str, Any] = {}
    for num_col in KEY_NUMERIC_FIELDS:
        numeric, stats = _coerce_numeric(df[num_col])
        df[num_col] = numeric
        coercion_stats[num_col] = stats
        if stats["introduced_nan_ratio"] > 0.30:
            quality["warnings"].append(
                f"Numeric conversion introduced >30% NaNs for `{num_col}` "
                f"({stats['introduced_nan_ratio']:.0%} of rows)."
            )
    quality["coercions"] = coercion_stats

    # PD normalization: if PD looks like a percentage (e.g., 9.5 meaning 9.5%),
    # convert to probability scale (0-1) for KPIs/charts.
    pd_series = df["probability_of_default"]
    pd_non_null = pd_series.dropna()
    if len(pd_non_null) >= 5:
        pd_median = float(pd_non_null.median())
        if 1.0 < pd_median <= 100.0:
            df["probability_of_default"] = df["probability_of_default"] / 100.0
            quality["warnings"].append("Detected PD values in 0–100 range; converted to 0–1 probability scale.")

    emp = df["employee_count"]
    size_bucket = pd.Series("Unknown", index=df.index, dtype="string")
    size_bucket = size_bucket.mask(emp.notna() & (emp < 50), "<50")
    size_bucket = size_bucket.mask(emp.notna() & (emp >= 50) & (emp <= 149), "50-149")
    size_bucket = size_bucket.mask(emp.notna() & (emp >= 150), "150+")
    df["size_bucket"] = size_bucket

    margin = df["net_margin"]
    non_null = margin.dropna()
    if len(non_null) >= 20:
        try:
            q = pd.qcut(
                non_null,
                q=4,
                labels=["Q1 (Low)", "Q2", "Q3", "Q4 (High)"],
                duplicates="drop",
            )
            if q.cat.categories.size < 4:
                raise ValueError("Insufficient distinct values for quartiles.")
            df["margin_bucket"] = pd.Series("Unknown", index=df.index, dtype="string")
            df.loc[non_null.index, "margin_bucket"] = q.astype("string")
        except Exception:
            df["margin_bucket"] = pd.cut(
                margin,
                bins=[-np.inf, 0, 5, 10, np.inf],
                labels=["<=0", "0-5", "5-10", "10+"],
                include_lowest=True,
            ).astype("string")
    else:
        df["margin_bucket"] = pd.cut(
            margin,
            bins=[-np.inf, 0, 5, 10, np.inf],
            labels=["<=0", "0-5", "5-10", "10+"],
            include_lowest=True,
        ).astype("string")
    df["margin_bucket"] = df["margin_bucket"].fillna("Unknown").astype("string")

    repay = df["repayment_status"].astype("string").fillna("Unknown")
    repay_l = repay.str.lower()
    weak_terms = ["weak", "poor", "delinquent", "late", "default"]
    df["is_weak_repayment"] = repay_l.str.contains(
        r"(?:"
        + "|".join(re.escape(t) for t in weak_terms)
        + r")",
        na=False,
    )

    if litigation_mapped:
        df["is_litigation"] = _coerce_litigation_to_bool(df["litigation_status"])
    else:
        df["is_litigation"] = pd.Series(False, index=df.index, dtype="bool")
    quality["has_litigation"] = litigation_mapped

    # Heuristic checks to surface likely bad mappings (helps users reach mapping UI).
    for cat in ["industry", "region", "loan_purpose", "repayment_status"]:
        unknown_rate = float((df[cat].astype("string").fillna("Unknown") == "Unknown").mean()) if len(df) else 1.0
        if unknown_rate >= 0.95 and not quality["mapping_incomplete"]:
            quality["warnings"].append(
                f"`{cat}` is {unknown_rate:.0%} 'Unknown' after cleaning. Mapping may be incorrect."
            )

    for num in ["loan_amount", "probability_of_default", "net_margin", "employee_count"]:
        non_null_rate = float(df[num].notna().mean()) if len(df) else 0.0
        if non_null_rate <= 0.05 and not quality["mapping_incomplete"]:
            quality["warnings"].append(
                f"`{num}` is mostly missing after numeric conversion ({(1.0 - non_null_rate):.0%} NaN). "
                "Mapping may be incorrect."
            )

    missingness_pct: dict[str, float] = {}
    for field in REQUIRED_CANONICAL_FIELDS:
        missingness_pct[field] = float(df[field].isna().mean() * 100.0)
    quality["missingness_pct"] = missingness_pct

    return df, quality


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")
