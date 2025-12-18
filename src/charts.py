from __future__ import annotations

import base64
import io
import zipfile
from dataclasses import dataclass
from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def _empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, showarrow=False, xref="paper", yref="paper")
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(height=420, margin=dict(l=20, r=20, t=50, b=20))
    return fig


def _weak_rate_grouped(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    if df.shape[0] == 0 or group_col not in df.columns or "is_weak_repayment" not in df.columns:
        return pd.DataFrame(columns=[group_col, "smes", "weak_count", "weak_rate_pct"])
    g = df.groupby(group_col, dropna=False).agg(
        smes=("is_weak_repayment", "size"),
        weak_count=("is_weak_repayment", lambda s: int(s.sum())),
        weak_rate=("is_weak_repayment", "mean"),
    )
    g = g.reset_index()
    g["weak_rate_pct"] = g["weak_rate"] * 100.0
    return g


def v1_weak_rate_by_industry(df: pd.DataFrame) -> go.Figure:
    g = _weak_rate_grouped(df, "industry")
    if g.shape[0] == 0:
        return _empty_figure("No data to display.")
    g = g.sort_values(["weak_rate_pct", "smes"], ascending=[False, False])
    fig = px.bar(
        g,
        x="industry",
        y="weak_rate_pct",
        title="Weak repayment rate by Industry",
        hover_data={"smes": True, "weak_count": True, "weak_rate_pct": ":.1f"},
    )
    fig.update_layout(yaxis_title="Weak repayment rate (%)", xaxis_title="", height=420)
    fig.update_xaxes(tickangle=30)
    return fig


def v3_weak_rate_by_region(df: pd.DataFrame) -> go.Figure:
    g = _weak_rate_grouped(df, "region")
    if g.shape[0] == 0:
        return _empty_figure("No data to display.")
    g = g.sort_values(["weak_rate_pct", "smes"], ascending=[False, False])
    fig = px.bar(
        g,
        x="region",
        y="weak_rate_pct",
        title="Weak repayment rate by Region",
        hover_data={"smes": True, "weak_count": True, "weak_rate_pct": ":.1f"},
    )
    fig.update_layout(yaxis_title="Weak repayment rate (%)", xaxis_title="", height=420)
    fig.update_xaxes(tickangle=30)
    return fig


def red_flags_by_company_bar(red_flags_long_df: pd.DataFrame) -> go.Figure:
    """
    Expected columns:
      - company: str
      - red_flag: str
      - triggered: int (typically 1 per triggered flag)
    """
    required = {"company", "red_flag", "triggered"}
    if red_flags_long_df.shape[0] == 0 or not required.issubset(set(red_flags_long_df.columns)):
        return _empty_figure("No red flags to display (missing inputs or none triggered).")

    plot_df = red_flags_long_df.copy()
    plot_df["company"] = plot_df["company"].astype(str)

    fig = px.bar(
        plot_df,
        x="company",
        y="triggered",
        color="red_flag",
        title="Red flags by Company",
        barmode="stack",
        hover_data={"company": True, "red_flag": True, "triggered": False},
    )
    fig.update_layout(
        xaxis_title="Company",
        yaxis_title="Red flags triggered (count)",
        height=520,
        legend_title_text="Red flag",
    )
    fig.update_xaxes(tickangle=30)
    return fig


def red_flag_count_bar(company_flags_df: pd.DataFrame, top_n: int = 20) -> go.Figure:
    required = {
        "financing_id",
        "red_flag_count",
        "red_flag_list",
        "net_margin",
        "current_ratio",
        "gearing_ratio",
        "interest_coverage",
    }
    if company_flags_df.shape[0] == 0 or not required.issubset(set(company_flags_df.columns)):
        return _empty_figure("No companies to display.")

    plot_df = company_flags_df.copy()
    plot_df = plot_df.sort_values(["red_flag_count", "financing_id"], ascending=[False, True])
    plot_df = plot_df.head(int(top_n))

    fig = px.bar(
        plot_df,
        x="financing_id",
        y="red_flag_count",
        title="Red flags count by Financing ID (Top N)",
        hover_data={
            "financing_id": True,
            "red_flag_count": True,
            "red_flag_list": True,
            "net_margin": ":.4g",
            "current_ratio": ":.4g",
            "gearing_ratio": ":.4g",
            "interest_coverage": ":.4g",
        },
    )
    fig.update_layout(
        xaxis_title="Financing ID",
        yaxis_title="Red flags triggered (0–4)",
        height=520,
        bargap=0.15,
        margin=dict(l=20, r=20, t=60, b=20),
    )
    fig.update_yaxes(range=[0, 4], dtick=1)

    # Make bars slimmer and keep labels readable as N grows.
    fig.update_traces(width=0.35)
    n = int(plot_df.shape[0])
    if n > 120:
        fig.update_xaxes(showticklabels=False)
    elif n > 60:
        # Show every 5th label to reduce clutter.
        ids = plot_df["financing_id"].astype(str).tolist()
        tickvals = ids[::5]
        fig.update_xaxes(tickmode="array", tickvals=tickvals, ticktext=tickvals, tickangle=90, tickfont=dict(size=9))
    else:
        fig.update_xaxes(tickangle=60, tickfont=dict(size=10))
    return fig


def _fig_to_png_bytes(fig: go.Figure) -> bytes:
    return fig.to_image(format="png", scale=2)  # requires kaleido


def _fig_to_html_bytes(fig: go.Figure) -> bytes:
    html = fig.to_html(full_html=True, include_plotlyjs=True)
    return html.encode("utf-8")


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


@dataclass(frozen=True)
class ExportBundle:
    primary_label: str
    primary_bytes: bytes
    primary_filename: str
    primary_mime: str
    fallback_label: str
    fallback_bytes: bytes
    fallback_filename: str
    fallback_mime: str
    message: str | None = None


def export_figures_bundle(figures: dict[str, go.Figure]) -> ExportBundle:
    """
    Produce a preferred PNG zip (kaleido) and a fallback HTML zip.
    If PNG export fails, the fallback still works and a message is returned.
    """
    html_files = {f"{name}.html": _fig_to_html_bytes(fig) for name, fig in figures.items()}
    html_zip = _zip_bytes(html_files)

    try:
        png_files = {f"{name}.png": _fig_to_png_bytes(fig) for name, fig in figures.items()}
        png_zip = _zip_bytes(png_files)
        return ExportBundle(
            primary_label="Download charts (PNG zip)",
            primary_bytes=png_zip,
            primary_filename="charts_png.zip",
            primary_mime="application/zip",
            fallback_label="Download charts (HTML zip)",
            fallback_bytes=html_zip,
            fallback_filename="charts_html.zip",
            fallback_mime="application/zip",
            message=None,
        )
    except Exception as exc:
        return ExportBundle(
            primary_label="Download charts (HTML zip)",
            primary_bytes=html_zip,
            primary_filename="charts_html.zip",
            primary_mime="application/zip",
            fallback_label="Download charts (HTML zip)",
            fallback_bytes=html_zip,
            fallback_filename="charts_html.zip",
            fallback_mime="application/zip",
            message=f"PNG export unavailable (kaleido missing or error). Using HTML export. Details: {exc}",
        )


def figure_png_data_uri(fig: go.Figure) -> Optional[str]:
    try:
        png = _fig_to_png_bytes(fig)
        b64 = base64.b64encode(png).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return None
