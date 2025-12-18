import streamlit as st

def inject_custom_css():
    st.markdown(
        """
        <style>
        /* Global tweaks */
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        
        /* Metric Card Styling */
        div[data-testid="metric-container"] {
            background-color: #FFFFFF;
            border: 1px solid #E0E0E0;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            transition: transform 0.2s;
        }
        div[data-testid="metric-container"]:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            border-color: #ED1C24;
        }
        div[data-testid="metric-container"] label {
            font-size: 0.9rem;
            color: #666;
        }
        div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
            font-size: 1.6rem;
            font-weight: 700;
            color: #333;
        }

        /* Sidebar tweaks */
        section[data-testid="stSidebar"] {
            background-color: #F8F9FA;
            border-right: 1px solid #E0E0E0;
        }
        
        /* Headers */
        h1, h2, h3 {
            font-family: 'Segoe UI', sans-serif;
            font-weight: 600;
        }
        h1 { color: #ED1C24; }
        
        /* Buttons */
        button[kind="primary"] {
            background-color: #ED1C24 !important;
            border-color: #ED1C24 !important;
        }
        button[kind="primary"]:hover {
            background-color: #C4121A !important;
            border-color: #C4121A !important;
        }

        /* Tabs */
        .stTabs [data-baseweb="tab-list"] {
            gap: 10px;
        }
        .stTabs [data-baseweb="tab"] {
            height: 50px;
            white-space: pre-wrap;
            border-radius: 4px;
            padding: 0 20px;
            font-weight: 500;
        }
        .stTabs [aria-selected="true"] {
            background-color: #FEF2F2;
            color: #ED1C24 !important;
            border-bottom-color: #ED1C24 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

def render_kpi_card(label: str, value: str, help_text: str = None):
    """
    Renders a KPI card using Streamlit's native metric component but styled via CSS.
    We wrap it in a container to ensure the CSS selector targets it correctly if needed,
    though the global CSS handles the `data-testid="metric-container"` well.
    """
    st.metric(label=label, value=value, help=help_text)
