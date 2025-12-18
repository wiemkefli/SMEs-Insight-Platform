from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import streamlit as st

from src.charts import (
    red_flag_count_bar,
    v1_weak_rate_by_industry,
    v3_weak_rate_by_region,
)
from src.load_clean import (
    CANONICAL_FIELDS,
    REQUIRED_CANONICAL_FIELDS,
    auto_detect_mapping,
    dataframe_to_csv_bytes,
    ensure_dirs,
    load_excel_to_dataframe,
    load_mapping_json,
    prepare_clean_dataset,
    save_mapping_json,
    validate_mapping_for_columns,
)
from src.metrics import compute_kpis, format_currency, format_percent
from src.red_flags import compute_red_flags


DEFAULT_DATASET_PATH = Path("data/SME_Dataset.xlsx")
MAPPING_PATH = Path("config/mapping.json")


@dataclass(frozen=True)
class AppData:
    raw_df: pd.DataFrame
    cleaned_full_df: pd.DataFrame
    filtered_df: pd.DataFrame
    mapping: dict[str, Optional[str]]
    data_quality: dict[str, Any]


def _reset_portfolio_filters() -> None:
    for key in ["filters_industry", "filters_region", "filters_loan_purpose", "filters_size_bucket"]:
        st.session_state.pop(key, None)


def _sidebar_portfolio_filters(cleaned_df: pd.DataFrame) -> dict[str, list[str]]:
    with st.sidebar.expander("Filters", expanded=True):
        st.caption("Applies to Overview, Red Flags, and Export.")

        def _col_options(col: str) -> list[str]:
            if col not in cleaned_df.columns:
                return []
            return sorted(
                cleaned_df[col].astype("string").fillna("Unknown").replace("", "Unknown").unique().tolist()
            )

        industries = _col_options("industry")
        regions = _col_options("region")
        purposes = _col_options("loan_purpose")
        sizes = _col_options("size_bucket")

        if not any([industries, regions, purposes, sizes]):
            st.info(
                "No filterable columns available. Use the Column Mapping page to map "
                "`industry`, `region`, `loan_purpose`, and/or `employee_count` (for size_bucket)."
            )
            return {"industry": [], "region": [], "loan_purpose": [], "size_bucket": []}

        st.button("Reset filters", use_container_width=True, on_click=_reset_portfolio_filters)

        selected_industry = st.multiselect(
            "Industry",
            options=industries,
            default=industries,
            key="filters_industry",
            disabled=(len(industries) == 0),
        )
        selected_region = st.multiselect(
            "Region",
            options=regions,
            default=regions,
            key="filters_region",
            disabled=(len(regions) == 0),
        )
        selected_purpose = st.multiselect(
            "Loan purpose",
            options=purposes,
            default=purposes,
            key="filters_loan_purpose",
            disabled=(len(purposes) == 0),
        )
        selected_size = st.multiselect(
            "Business size",
            options=sizes,
            default=sizes,
            key="filters_size_bucket",
            disabled=(len(sizes) == 0),
        )

        return {
            "industry": list(selected_industry),
            "region": list(selected_region),
            "loan_purpose": list(selected_purpose),
            "size_bucket": list(selected_size),
        }


def _apply_portfolio_filters(cleaned_df: pd.DataFrame, filters: dict[str, list[str]]) -> pd.DataFrame:
    df = cleaned_df.copy()

    for col in ["industry", "region", "loan_purpose", "size_bucket"]:
        if col not in df.columns:
            continue
        selected = filters.get(col) or []
        if len(selected) == 0:
            continue
        df_col = df[col].astype("string").fillna("Unknown").replace("", "Unknown")
        if len(selected) < int(df_col.nunique(dropna=False)):
            df = df[df_col.isin(set(selected))]
    return df


def _render_kpis(df: pd.DataFrame) -> None:
    kpis = compute_kpis(df)
    r1c1, r1c2, r1c3 = st.columns(3)
    r2c1, r2c2, r2c3 = st.columns(3)

    r1c1.metric("SMEs", f"{kpis['num_smes']:,}")
    r1c2.metric("Total Loan Amount", format_currency(kpis["total_loan_amount"]))
    r1c3.metric("Median Loan Amount", format_currency(kpis["median_loan_amount"]))

    r2c1.metric("Avg PD", format_percent(kpis["avg_pd"]))
    r2c2.metric("Weak Repayment Rate", format_percent(kpis["weak_repayment_rate"]))
    r2c3.metric("Litigation Rate", format_percent(kpis["litigation_rate"]))


def _overview_summary(df: pd.DataFrame) -> list[str]:
    n = int(df.shape[0])
    if n == 0:
        return []

    bullets: list[str] = []

    if "is_weak_repayment" in df.columns:
        weak_rate = float(df["is_weak_repayment"].mean())
        bullets.append(f"Weak repayment rate: {format_percent(weak_rate)} (n={n}).")

    if "probability_of_default" in df.columns:
        avg_pd = float(df["probability_of_default"].mean())
        bullets.append(f"Average PD: {format_percent(avg_pd)}.")

    if "net_margin" in df.columns:
        share_neg = float((df["net_margin"] <= 0).mean())
        bullets.append(f"Profitability: {share_neg * 100:.1f}% of SMEs have net_margin ≤ 0.")

    if "is_litigation" in df.columns:
        lit_rate = float(df["is_litigation"].mean())
        bullets.append(f"Litigation prevalence: {format_percent(lit_rate)}.")

    return bullets[:4]


def _mapping_ui(raw_df: pd.DataFrame, current_mapping: dict[str, Optional[str]]) -> dict[str, Optional[str]]:
    st.subheader("Column Mapping")
    st.caption(
        "Select which dataset column corresponds to each canonical field. "
        "Required fields must be mapped to continue."
    )

    options = ["(None)"] + list(raw_df.columns)

    edited: dict[str, Optional[str]] = {}
    for canonical in CANONICAL_FIELDS:
        is_optional = canonical == "sme_id"
        label = f"{canonical}{' (optional)' if is_optional else ''}"
        default_value = current_mapping.get(canonical)

        index = 0
        if default_value in raw_df.columns:
            index = options.index(default_value)

        selection = st.selectbox(label, options=options, index=index, key=f"map_{canonical}")
        edited[canonical] = None if selection == "(None)" else selection

    missing_required = [
        f for f in REQUIRED_CANONICAL_FIELDS if not edited.get(f) or edited.get(f) not in raw_df.columns
    ]
    if missing_required:
        st.warning(f"Missing required mappings: {', '.join(missing_required)}")

    col1, col2 = st.columns([1, 2])
    with col1:
        if st.button("Save mapping", type="primary", use_container_width=True, disabled=bool(missing_required)):
            ensure_dirs()
            save_mapping_json(edited, MAPPING_PATH)
            st.success(f"Saved mapping to {MAPPING_PATH.as_posix()}")
            st.rerun()
    with col2:
        if MAPPING_PATH.exists():
            if st.button("Clear saved mapping", use_container_width=True):
                try:
                    MAPPING_PATH.unlink(missing_ok=True)
                    st.success("Removed saved mapping.")
                    st.rerun()
                except OSError as exc:
                    st.error(f"Failed to remove mapping: {exc}")

    return edited


@st.cache_data(show_spinner=False)
def _load_raw_data_from_path(path_str: str) -> pd.DataFrame:
    return load_excel_to_dataframe(path_str)


@st.cache_data(show_spinner=False)
def _load_raw_data_from_upload(file_bytes: bytes, filename: str) -> pd.DataFrame:
    return load_excel_to_dataframe(file_bytes, filename=filename)


@st.cache_data(show_spinner=False)
def _prepare_cleaned_data(
    raw_df: pd.DataFrame, mapping: dict[str, Optional[str]]
) -> tuple[pd.DataFrame, dict[str, Any]]:
    return prepare_clean_dataset(raw_df, mapping)


def _get_app_data() -> Optional[AppData]:
    st.title("AmBank SME Insights Platform")
    st.caption("Local SME dataset cleaning and exploration.")

    uploaded = None
    with st.sidebar.expander("Data source", expanded=not DEFAULT_DATASET_PATH.exists()):
        if DEFAULT_DATASET_PATH.exists():
            st.success(f"Using default dataset: {DEFAULT_DATASET_PATH.as_posix()}")
        else:
            st.info(f"Default file not found: {DEFAULT_DATASET_PATH.as_posix()}")
            uploaded = st.file_uploader("Upload SME Excel (.xlsx)", type=["xlsx"])

    if DEFAULT_DATASET_PATH.exists():
        raw_df = _load_raw_data_from_path(str(DEFAULT_DATASET_PATH))
    else:
        if uploaded is None:
            st.info("Place your dataset at `data/SME_Dataset.xlsx` or upload a `.xlsx` file from the sidebar.")
            return None
        raw_df = _load_raw_data_from_upload(uploaded.getvalue(), filename=uploaded.name)

    with st.sidebar.expander("Data status", expanded=False):
        st.write(f"Rows: **{raw_df.shape[0]:,}**")
        st.write(f"Columns: **{raw_df.shape[1]:,}**")
        if st.button("Reload data (clear cache)", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    saved_mapping = load_mapping_json(MAPPING_PATH) or {}
    validated_mapping = validate_mapping_for_columns(saved_mapping, list(raw_df.columns))
    auto_mapping = auto_detect_mapping(list(raw_df.columns))
    mapping = {**auto_mapping, **validated_mapping}

    cleaned_full_df, data_quality = _prepare_cleaned_data(raw_df, mapping)

    return AppData(
        raw_df=raw_df,
        cleaned_full_df=cleaned_full_df,
        filtered_df=cleaned_full_df,
        mapping=mapping,
        data_quality=data_quality,
    )


def main() -> None:
    st.set_page_config(page_title="AmBank SME Insights Platform", layout="wide")
    ensure_dirs()

    app_data = _get_app_data()
    if app_data is None:
        return

    filters = _sidebar_portfolio_filters(app_data.cleaned_full_df)
    df_filtered = _apply_portfolio_filters(app_data.cleaned_full_df, filters)

    mapping_missing = bool(app_data.data_quality.get("mapping_incomplete", False))
    quality_warnings = list(app_data.data_quality.get("warnings", []))
    st.sidebar.divider()
    if "force_show_quality_tab" not in st.session_state:
        st.session_state["force_show_quality_tab"] = False
    if st.sidebar.button("Edit column mapping / data quality", use_container_width=True):
        st.session_state["force_show_quality_tab"] = True
        st.session_state["active_page"] = "Column Mapping / Data Quality"
        st.rerun()

    show_quality_tab = bool(mapping_missing or quality_warnings or st.session_state.get("force_show_quality_tab", False))

    tab_names = ["Overview", "Red Flags", "Export"]
    if show_quality_tab:
        tab_names.append("Column Mapping / Data Quality")

    # Streamlit tabs can reset to the first tab on reruns (e.g. when clicking pagination buttons).
    # Use a stateful horizontal radio to keep the selected page stable across reruns.
    if st.session_state.get("active_page") not in tab_names:
        st.session_state["active_page"] = tab_names[0]
    active_page = st.radio(
        "Page",
        tab_names,
        horizontal=True,
        key="active_page",
        label_visibility="collapsed",
    )

    if df_filtered.shape[0] == 0:
        st.warning("No cleaned data available.")

    st.caption(
        f"Loaded: {app_data.raw_df.shape[0]:,} rows | "
        f"Cleaned: {app_data.cleaned_full_df.shape[0]:,} rows | "
        f"Selected: {df_filtered.shape[0]:,} rows"
    )

    if active_page == "Overview":
        _render_kpis(df_filtered)
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(v1_weak_rate_by_industry(df_filtered), use_container_width=True, key="overview_v1")
        with c2:
            st.plotly_chart(v3_weak_rate_by_region(df_filtered), use_container_width=True, key="overview_v3")
        with st.expander("Preview (cleaned data)", expanded=False):
            st.dataframe(df_filtered.head(50), use_container_width=True)
        bullets = _overview_summary(df_filtered)
        if bullets:
            st.subheader("Summary")
            for bullet in bullets:
                st.write(f"- {bullet}")

    if active_page == "Red Flags":
        st.subheader("Red Flags")
        st.caption("Rules: net_margin < 8, current_ratio < 1.8, gearing_ratio < 0.85, interest_coverage < 15.")

        flags_df = compute_red_flags(df_filtered)
        with st.sidebar:
            st.markdown("**Red Flags filters**")
            if flags_df.shape[0] == 0:
                st.info(
                    "No red-flag data available. Red Flags requires a company identifier "
                    "(`financing_id` or mapped `sme_id`) and at least one ratio column "
                    "(`net_margin`/`net_ratio`, `current_ratio`, `gearing_ratio`, or `interest_coverage`)."
                )
            else:
                def _reset_red_flags_filters() -> None:
                    for k in [
                        "rf_search_financing_id",
                        "rf_page_size",
                        "rf_only_flagged",
                    ]:
                        st.session_state.pop(k, None)
                    st.session_state["red_flags_chart_page"] = 1
                    st.session_state.pop("red_flags_chart_sig", None)

                top_left, top_right = st.columns([1, 1])
                with top_left:
                    st.button(
                        "Reset",
                        use_container_width=True,
                        key="rf_reset_btn",
                        on_click=_reset_red_flags_filters,
                    )
                with top_right:
                    st.toggle(
                        "Only flagged",
                        value=True,
                        key="rf_only_flagged",
                        help="When enabled, the chart paginates only financing IDs with red_flag_count >= 1.",
                    )

                st.caption("Search before paging through the chart.")

                company_search = st.text_input(
                    "Search financing_id",
                    value=st.session_state.get("rf_search_financing_id", ""),
                    key="rf_search_financing_id",
                    placeholder="Type part of a financing_id...",
                    help="Case-insensitive substring match.",
                )

                page_size = st.slider(
                    "IDs per chart page",
                    min_value=10,
                    max_value=200,
                    value=int(st.session_state.get("rf_page_size", 50) or 50),
                    step=5,
                    key="rf_page_size",
                )

        if flags_df.shape[0] == 0:
            st.info(
                "No red-flag data available. Ensure your dataset includes a company identifier "
                "(e.g. `financing_id` or mapped `sme_id`) and at least one ratio column "
                "(e.g. `net_margin`)."
            )
        else:
            filtered_flags = flags_df.copy()
            if company_search.strip():
                filtered_flags = filtered_flags[
                    filtered_flags["financing_id"]
                    .astype("string")
                    .str.contains(company_search.strip(), case=False, na=False)
                ]

            k1, k2, k3 = st.columns(3)
            k1.metric("Total financing IDs", f"{filtered_flags.shape[0]:,}")
            k2.metric("Financing IDs with ≥1 red flag", f"{int((filtered_flags['red_flag_count'] >= 1).sum()):,}")
            avg_flag_count = float(filtered_flags["red_flag_count"].mean()) if filtered_flags.shape[0] else 0.0
            k3.metric("Average red_flag_count", f"{avg_flag_count:.2f}")

            only_flagged = bool(st.session_state.get("rf_only_flagged", True))

            if filtered_flags.shape[0] == 0:
                st.info("No financing IDs match the Red Flags filters.")
            elif int(filtered_flags["red_flag_count"].max()) == 0:
                st.info("No companies triggered red flags under current filters.")
            else:
                chart_df = filtered_flags.copy()
                if only_flagged:
                    chart_df = chart_df[chart_df["red_flag_count"] >= 1].copy()
                chart_df = chart_df.sort_values(["red_flag_count", "financing_id"], ascending=[False, True])
                if chart_df.shape[0] == 0:
                    st.info("No companies triggered red flags under current filters.")
                    chart_df = pd.DataFrame()

            if filtered_flags.shape[0] != 0 and int(filtered_flags["red_flag_count"].max()) != 0 and chart_df.shape[0] != 0:

                total = int(chart_df.shape[0])
                page_size_i = max(1, int(page_size))
                total_pages = max(1, int(math.ceil(total / page_size_i)))

                sig = (
                    (company_search or "").strip().lower(),
                    only_flagged,
                    page_size_i,
                )
                if st.session_state.get("red_flags_chart_sig") != sig:
                    st.session_state["red_flags_chart_sig"] = sig
                    st.session_state["red_flags_chart_page"] = 1

                current_page = int(st.session_state.get("red_flags_chart_page", 1))
                current_page = max(1, min(current_page, total_pages))
                st.session_state["red_flags_chart_page"] = current_page

                def _rf_prev() -> None:
                    st.session_state["red_flags_chart_page"] = max(
                        1, int(st.session_state.get("red_flags_chart_page", 1)) - 1
                    )

                def _rf_next() -> None:
                    st.session_state["red_flags_chart_page"] = min(
                        total_pages, int(st.session_state.get("red_flags_chart_page", 1)) + 1
                    )

                nav1, nav2, nav3, nav4 = st.columns([1, 2, 1, 2])
                with nav1:
                    st.button(
                        "Prev",
                        disabled=(current_page <= 1),
                        key="red_flags_prev",
                        on_click=_rf_prev,
                    )
                with nav2:
                    st.selectbox(
                        "Chart page",
                        options=list(range(1, total_pages + 1)),
                        key="red_flags_chart_page",
                    )
                with nav3:
                    st.button(
                        "Next",
                        disabled=(current_page >= total_pages),
                        key="red_flags_next",
                        on_click=_rf_next,
                    )
                with nav4:
                    start_i = (int(st.session_state["red_flags_chart_page"]) - 1) * page_size_i + 1
                    end_i = min(total, int(st.session_state["red_flags_chart_page"]) * page_size_i)
                    scope = "flagged financing IDs" if only_flagged else "financing IDs"
                    st.caption(f"Showing {start_i:,}–{end_i:,} of {total:,} {scope}")

                page = int(st.session_state["red_flags_chart_page"])
                start = (page - 1) * page_size_i
                end = start + page_size_i
                page_df = chart_df.iloc[start:end].copy()

                fig = red_flag_count_bar(page_df, top_n=int(page_df.shape[0]))
                fig.update_layout(title=f"Red flags count by Financing ID (Page {page}/{total_pages})")
                st.plotly_chart(fig, use_container_width=True, key="red_flags_count_bar")

            st.subheader("Company red-flag table")
            display_cols = [
                "financing_id",
                "red_flag_count",
                "red_flag_list",
                "net_margin",
                "current_ratio",
                "gearing_ratio",
                "interest_coverage",
                "flag_net_margin",
                "flag_current_ratio",
                "flag_gearing_ratio",
                "flag_interest_coverage",
            ]

            table_df = filtered_flags.sort_values(["red_flag_count", "financing_id"], ascending=[False, True])
            st.dataframe(table_df[display_cols], use_container_width=True, hide_index=True)

    if active_page == "Export":
        st.subheader("Exports")
        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "Download selected data (CSV)",
                data=dataframe_to_csv_bytes(df_filtered),
                file_name="sme_selected_data.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with c2:
            st.download_button(
                "Download cleaned full data (CSV)",
                data=dataframe_to_csv_bytes(app_data.cleaned_full_df),
                file_name="sme_cleaned_data.csv",
                mime="text/csv",
                use_container_width=True,
            )

    if show_quality_tab and active_page == "Column Mapping / Data Quality":
        edited_mapping = _mapping_ui(app_data.raw_df, app_data.mapping)
        cleaned_full_df, data_quality = _prepare_cleaned_data(app_data.raw_df, edited_mapping)
        st.subheader("Data quality summary")
        missingness = data_quality.get("missingness_pct", {})
        if missingness:
            miss_df = (
                pd.DataFrame({"missing_%": missingness})
                .reset_index()
                .rename(columns={"index": "field"})
                .sort_values("missing_%", ascending=False)
            )
            st.dataframe(miss_df, use_container_width=True, hide_index=True)
        for warning in data_quality.get("warnings", []):
            st.warning(warning)

        st.subheader("Preview (cleaned)")
        st.dataframe(cleaned_full_df.head(50), use_container_width=True)


if __name__ == "__main__":
    main()
