import streamlit as st

st.set_page_config(
    page_title="XBRL Fact Viewer",
    page_icon="📊",
    layout="wide",
)

st.markdown("""
<style>
    [data-testid="stSidebar"] { background: #1e3a5f; }
    [data-testid="stSidebar"] * { color: #e2e8f0 !important; }
    .metric-card { background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:1rem 1.25rem; }
    .metric-value { font-size:1.75rem; font-weight:700; color:#1e3a5f; line-height:1.1; }
    .metric-label { font-size:0.78rem; color:#64748b; text-transform:uppercase; letter-spacing:0.05em; margin-top:0.25rem; }
    .section-header { font-size:1.05rem; font-weight:600; color:#1e3a5f; margin:1.5rem 0 0.75rem 0;
        padding-bottom:0.35rem; border-bottom:2px solid #e2e8f0; }
</style>
""", unsafe_allow_html=True)

st.title("📊 XBRL Fact Viewer")
st.markdown(
    "Upload any XBRL file to extract, explore, and download all tagged financial facts. "
    "Supports ESEF report packages, UK iXBRL accounts, SEC EDGAR filings, and standard XBRL instance documents."
)

st.markdown("""
---
**How to use:**
1. Upload your file below — see supported formats in the expander
2. Use the sidebar to navigate between **Dashboard**, **Facts Table**, **Pivot View**, and **Text Sections**

The file is processed once and shared across all pages — no need to re-upload.
""")

uploaded = st.file_uploader(
    "Upload XBRL file",
    type=["zip", "xhtml", "html", "xml"],
    help="Accepts ESEF zip packages, standalone iXBRL .xhtml/.html files (e.g. Companies House), or XBRL instance .xml files."
)

st.markdown("**What would you like to extract?**")
opt_col1, opt_col2 = st.columns(2)
with opt_col1:
    do_tags = st.checkbox(
        "📊 XBRL tags",
        value=True,
        help="Extract all tagged financial facts using Arelle. Powers the Dashboard, Facts Table, and Pivot View pages. Takes 20–30 seconds."
    )
with opt_col2:
    do_text = st.checkbox(
        "📄 Narrative text sections",
        value=True,
        help="Strip iXBRL tags and extract the narrative text, classified into annual report sections (Strategic Report, Auditor's Report, etc.). Powers the Text Sections page."
    )

if not do_tags and not do_text:
    st.warning("Select at least one extraction option above.")

if uploaded:
    from loader import load_facts_from_file, load_text_sections

    file_ext = uploaded.name.rsplit(".", 1)[-1].lower()
    file_bytes = uploaded.read()

    if do_tags:
        with st.spinner("Loading XBRL facts — may take 20–30 seconds on first load…"):
            try:
                df, logs, meta = load_facts_from_file(file_bytes, file_ext, uploaded.name)
                st.session_state["esef_df"] = df
                st.session_state["esef_meta"] = meta
                st.session_state["esef_filename"] = uploaded.name
                st.success(f"✅ Loaded **{len(df):,}** facts from **{uploaded.name}**")
                with st.expander("Processing log"):
                    for line in logs:
                        st.text(line)
            except Exception as e:
                st.error(f"Failed to load XBRL facts: {e}")
    else:
        # Clear any stale tag data from a previous upload
        for key in ["esef_df", "esef_meta"]:
            st.session_state.pop(key, None)
        st.session_state["esef_filename"] = uploaded.name

    if do_text:
        with st.spinner("Extracting narrative text sections…"):
            try:
                text_df = load_text_sections(file_bytes, file_ext, uploaded.name)
                st.session_state["esef_text_df"] = text_df
                if not text_df.empty:
                    n_sections = text_df["section"].nunique()
                    st.success(f"✅ Extracted **{len(text_df):,}** text chunks across **{n_sections}** sections")
                else:
                    st.info("No narrative text sections were found in this file.")
            except Exception as e:
                st.warning(f"Text extraction failed: {e}")
                st.session_state["esef_text_df"] = None
    else:
        st.session_state.pop("esef_text_df", None)

    if do_tags or do_text:
        st.info("👈 Use the sidebar to navigate to Dashboard, Facts Table, Pivot View, or Text Sections.")

else:
    st.info("👆 Upload a file above to begin.")

    with st.expander("📁 Supported file formats"):
        st.markdown("""
| Format | Extension | Example sources |
|--------|-----------|-----------------|
| **ESEF Report Package** | `.zip` | Company investor relations pages, ESMA filing database, FCA National Storage Mechanism |
| **Inline XBRL (iXBRL)** | `.xhtml` / `.html` | Companies House individual filings, ESEF extracted files, HMRC accounts |
| **XBRL Instance Document** | `.xml` | SEC EDGAR, older UK/EU filings, taxonomy test files |

**Where to find files:**
- **ESEF (EU listed companies):** [ESMA Filings](https://filings.esma.europa.eu) or company IR pages
- **UK accounts:** [Companies House](https://find-and-update.company-information.service.gov.uk) — search a company and look under *Filing history*
- **US public companies:** [SEC EDGAR](https://www.sec.gov/cgi-bin/browse-edgar) — search any ticker and find the latest 10-K

**Note:** Files are processed locally on Streamlit's servers and not stored or shared.
        """)

    with st.expander("ℹ️ About this tool"):
        st.markdown("""
This tool uses [Arelle](https://arelle.org), the leading open-source XBRL processor, to parse your filing
and extract every tagged fact into a structured table.

**What you can do:**
- **Dashboard** — overview charts, key financial KPIs, fact distribution by statement and namespace
- **Facts Table** — filterable, searchable table of all facts grouped by financial statement, with CSV download
- **Pivot View** — pivot numeric facts by period for easy year-on-year comparison
- **Text Sections** — narrative text extracted from the report, classified into annual report sections with search

**Limitations:**
- Taxonomy labels may not resolve if the taxonomy cannot be fetched — concept names are used as fallback
- Very large files (>100MB) may be slow or hit Streamlit's 800MB memory limit
- Text section detection works best on structured reports with clear HTML headings
        """)
