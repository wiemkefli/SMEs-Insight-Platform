from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def compute_kpis(df: pd.DataFrame) -> dict[str, Any]:
    num_smes = int(df.shape[0])

    loan_amount = df.get("loan_amount", pd.Series(dtype="float64"))
    pd_col = df.get("probability_of_default", pd.Series(dtype="float64"))

    total_loan_amount = float(np.nansum(loan_amount.to_numpy())) if num_smes else 0.0
    median_loan_amount = (
        float(np.nanmedian(loan_amount.to_numpy())) if num_smes and loan_amount.notna().any() else float("nan")
    )
    avg_pd = float(np.nanmean(pd_col.to_numpy())) if num_smes and pd_col.notna().any() else float("nan")

    weak = df.get("is_weak_repayment", pd.Series(dtype="bool"))
    weak_rate = float(weak.mean()) if num_smes else float("nan")

    litig = df.get("is_litigation", pd.Series(dtype="bool"))
    litigation_rate = float(litig.mean()) if num_smes else float("nan")

    return {
        "num_smes": num_smes,
        "total_loan_amount": total_loan_amount,
        "median_loan_amount": median_loan_amount,
        "avg_pd": avg_pd,
        "weak_repayment_rate": weak_rate,
        "litigation_rate": litigation_rate,
    }


def format_currency(value: float) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "-"
    return f"RM {value:,.0f}"


def format_percent(value: float) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "-"
    return f"{value * 100:.1f}%"
