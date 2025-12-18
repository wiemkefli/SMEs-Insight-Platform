from __future__ import annotations

import re
from typing import Final

import numpy as np
import pandas as pd


_NUMERIC_STRIP_RE: Final[re.Pattern[str]] = re.compile(r"[^0-9\.\-\+eE]+")


def _coerce_numeric_like(series: pd.Series) -> pd.Series:
    s = series.astype("string")
    cleaned = s.str.replace(_NUMERIC_STRIP_RE, "", regex=True).str.strip()
    return pd.to_numeric(cleaned, errors="coerce").astype("float64")


def compute_red_flags(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute per-company red flags using fixed thresholds:
      - net_margin < 8
      - current_ratio < 1.8
      - gearing_ratio < 0.85
      - interest_coverage < 15

    Missing values handling:
      - If a ratio is NaN for a company, that specific flag is False and the ratio remains NaN.

    Output columns (always present):
      - financing_id, red_flag_count, red_flag_list
      - net_margin, current_ratio, gearing_ratio, interest_coverage (numeric with NaNs kept)
      - flag_net_margin, flag_current_ratio, flag_gearing_ratio, flag_interest_coverage
    Optional passthrough (if present in input):
      - industry, region
    """
    # Project convention: identify companies by Financing_id (snake_case: financing_id).
    # If it's not present, fall back to the canonical optional `sme_id`.
    company_col = "financing_id" if "financing_id" in df.columns else ("sme_id" if "sme_id" in df.columns else None)

    # Project convention: treat net_margin as the "net ratio" input for red-flag rules.
    # If net_margin is not present, fall back to net_ratio if provided.
    net_margin_col = "net_margin" if "net_margin" in df.columns else ("net_ratio" if "net_ratio" in df.columns else None)
    current_ratio_col = "current_ratio" if "current_ratio" in df.columns else None
    gearing_ratio_col = "gearing_ratio" if "gearing_ratio" in df.columns else None
    interest_coverage_col = "interest_coverage" if "interest_coverage" in df.columns else None

    base_cols = ["financing_id", "net_margin", "current_ratio", "gearing_ratio", "interest_coverage"]
    flag_cols = [
        "flag_net_margin",
        "flag_current_ratio",
        "flag_gearing_ratio",
        "flag_interest_coverage",
    ]
    out_cols = [
        "financing_id",
        "red_flag_count",
        "red_flag_list",
        "net_margin",
        "current_ratio",
        "gearing_ratio",
        "interest_coverage",
        *flag_cols,
    ]

    if df.shape[0] == 0 or company_col is None:
        return pd.DataFrame(columns=out_cols)

    ratio_col_map: dict[str, str] = {}
    if net_margin_col is not None:
        ratio_col_map["net_margin"] = net_margin_col
    if current_ratio_col is not None:
        ratio_col_map["current_ratio"] = current_ratio_col
    if gearing_ratio_col is not None:
        ratio_col_map["gearing_ratio"] = gearing_ratio_col
    if interest_coverage_col is not None:
        ratio_col_map["interest_coverage"] = interest_coverage_col

    ratio_cols = list(ratio_col_map.values())
    if len(ratio_cols) == 0:
        return pd.DataFrame(columns=out_cols)

    work_cols = [company_col, *ratio_cols]
    for optional in ["industry", "region"]:
        if optional in df.columns:
            work_cols.append(optional)

    work = df[work_cols].copy()
    work["financing_id"] = work[company_col].astype("string").fillna("Unknown").str.strip().replace("", "Unknown")

    for c in ratio_cols:
        work[c] = _coerce_numeric_like(work[c])

    # Aggregate per company, then normalize output column names.
    agg: dict[str, str] = {c: "min" for c in ratio_cols}
    if "industry" in work.columns:
        agg["industry"] = "first"
    if "region" in work.columns:
        agg["region"] = "first"

    company_df = work.groupby("financing_id", dropna=False).agg(agg).reset_index()

    # Ensure all expected ratio columns exist on output, even if missing in input.
    for canonical, src in ratio_col_map.items():
        if canonical != src and src in company_df.columns:
            company_df[canonical] = company_df[src]

    for canonical in ["net_margin", "current_ratio", "gearing_ratio", "interest_coverage"]:
        if canonical not in company_df.columns:
            company_df[canonical] = pd.Series([np.nan] * company_df.shape[0], dtype="float64")

    company_df["flag_net_margin"] = (company_df["net_margin"] < 8.0) & company_df["net_margin"].notna()
    company_df["flag_current_ratio"] = (company_df["current_ratio"] < 1.8) & company_df["current_ratio"].notna()
    company_df["flag_gearing_ratio"] = (company_df["gearing_ratio"] < 0.85) & company_df["gearing_ratio"].notna()
    company_df["flag_interest_coverage"] = (
        (company_df["interest_coverage"] < 15.0) & company_df["interest_coverage"].notna()
    )

    company_df["red_flag_count"] = (
        company_df[flag_cols].sum(axis=1).astype("int64")
    )

    def _list_flags(row: pd.Series) -> str:
        triggered: list[str] = []
        if bool(row["flag_net_margin"]):
            triggered.append("net_margin")
        if bool(row["flag_current_ratio"]):
            triggered.append("current_ratio")
        if bool(row["flag_gearing_ratio"]):
            triggered.append("gearing_ratio")
        if bool(row["flag_interest_coverage"]):
            triggered.append("interest_coverage")
        return ",".join(triggered)

    company_df["red_flag_list"] = company_df.apply(_list_flags, axis=1)

    ordered = ["financing_id"]
    for c in ["industry", "region"]:
        if c in company_df.columns:
            ordered.append(c)
    ordered += out_cols[1:]  # everything except financing_id
    company_df = company_df[ordered]
    company_df = company_df.sort_values(["red_flag_count", "financing_id"], ascending=[False, True])
    return company_df
