import streamlit as st

st.set_page_config(
    page_title="ESEF XBRL Viewer",
    page_icon="📊",
    layout="wide",
)

# ── Shared CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    [data-testid="stSidebar"] { background: #1e3a5f; }
    [data-testid="stSidebar"] * { color: #e2e8f0 !important; }
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stTextInput label,
    [data-testid="stSidebar"] .stCheckbox label { color: #94a3b8 !important; }
    .metric-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1rem 1.25rem;
    }
    .metric-value {
        font-size: 1.75rem;
        font-weight: 700;
        color: #1e3a5f;
        line-height: 1.1;
    }
    .metric-label {
        font-size: 0.78rem;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-top: 0.25rem;
    }
    .section-header {
        font-size: 1.05rem;
        font-weight: 600;
        color: #1e3a5f;
        margin: 1.5rem 0 0.75rem 0;
        padding-bottom: 0.35rem;
        border-bottom: 2px solid #e2e8f0;
    }
</style>
""", unsafe_allow_html=True)

st.title("📊 ESEF XBRL Viewer")
st.markdown("Upload an ESEF report package to explore the tagged financial data across three views.")

st.markdown("""
---
**How to use:**
1. Upload your ESEF `.zip` report package below
2. Use the sidebar to navigate between **Dashboard**, **Facts Table**, and **Pivot View**

The file is processed once and shared across all pages — no need to re-upload.
""")

uploaded = st.file_uploader(
    "Upload ESEF Report Package (.zip)",
    type=["zip"],
    help="Standard ESEF packages contain an iXBRL .xhtml file plus extension taxonomy."
)

if uploaded:
    from loader import load_facts
    with st.spinner("Loading via Arelle — may take 20–30 seconds on first load…"):
        try:
            df, logs, meta = load_facts(uploaded.read())
            st.session_state["esef_df"] = df
            st.session_state["esef_meta"] = meta
            st.session_state["esef_filename"] = uploaded.name
            st.success(f"✅ Loaded **{len(df):,}** facts from **{uploaded.name}**")
            with st.expander("Processing log"):
                for line in logs:
                    st.text(line)
            st.info("👈 Use the sidebar to navigate to Dashboard, Facts Table, or Pivot View.")
        except Exception as e:
            st.error(f"Failed to load: {e}")
else:
    st.info("👆 Upload an ESEF report package zip to begin.")
    with st.expander("What is an ESEF report package?"):
        st.markdown("""
**European Single Electronic Format (ESEF)** is the mandatory format for annual financial reports
filed by companies listed on EU regulated markets since 2020.

Reports are distributed as a **zip file** containing:
- An **iXBRL (.xhtml)** file — the human-readable annual report with embedded XBRL tags
- An **extension taxonomy** — custom concepts defined by the company
- A **META-INF** folder with package metadata

You can find ESEF filings from:
- Company investor relations pages
- National regulators (FCA in the UK, ESMA's ESEF filing database)
- Data aggregators like Calcbench or Dains
        """)
