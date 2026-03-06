import streamlit as st
import pandas as pd

st.set_page_config(page_title="Text Sections", page_icon="📄", layout="wide")

st.markdown("""
<style>
    [data-testid="stSidebar"] { background: #1e3a5f; }
    [data-testid="stSidebar"] * { color: #e2e8f0 !important; }
    .section-header { font-size:1.05rem; font-weight:600; color:#1e3a5f; margin:1.5rem 0 0.75rem 0;
        padding-bottom:0.35rem; border-bottom:2px solid #e2e8f0; }
    .chunk-text { background:#f8fafc; border-left:3px solid #1e3a5f; padding:0.75rem 1rem;
        border-radius:0 6px 6px 0; font-size:0.9rem; line-height:1.6; color:#1a1a1a; }
</style>
""", unsafe_allow_html=True)

st.title("📄 Text Sections")
st.caption(
    "Narrative text extracted from the iXBRL report, classified into annual report sections. "
    "XBRL inline tags are stripped — this shows the human-readable content only."
)

# ── Guard: check session state ─────────────────────────────────────────────────
if "esef_text_df" not in st.session_state or st.session_state["esef_text_df"] is None:
    st.warning("No file loaded yet. Upload a file on the **Home** page first.")
    st.stop()

text_df: pd.DataFrame = st.session_state["esef_text_df"]
filename: str = st.session_state.get("esef_filename", "report")

if text_df.empty:
    st.warning(
        "No narrative text sections were extracted from this file. "
        "This can happen if the report uses non-standard heading structure or is primarily numeric."
    )
    st.stop()

# ── Summary metrics ────────────────────────────────────────────────────────────
total_chunks = len(text_df)
total_sections = text_df["section"].nunique()
total_chars = text_df["char_count"].sum()
total_words = text_df["text"].str.split().str.len().sum()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Text chunks", f"{total_chunks:,}")
col2.metric("Sections identified", total_sections)
col3.metric("Total characters", f"{total_chars:,}")
col4.metric("Approx. words", f"{total_words:,}")

st.divider()

# ── Section summary table ──────────────────────────────────────────────────────
left, right = st.columns([1, 2])

with left:
    st.markdown('<div class="section-header">Sections found</div>', unsafe_allow_html=True)
    section_summary = (
        text_df.groupby("section")
        .agg(Chunks=("seq", "count"), Characters=("char_count", "sum"))
        .reset_index()
        .rename(columns={"section": "Section"})
        .sort_values("Characters", ascending=False)
    )
    st.dataframe(section_summary, hide_index=True, use_container_width=True)

# ── Filters & search ───────────────────────────────────────────────────────────
with right:
    st.markdown('<div class="section-header">Browse & search</div>', unsafe_allow_html=True)

    filter_col, search_col = st.columns([1, 1])
    with filter_col:
        all_sections = ["All sections"] + sorted(text_df["section"].unique().tolist())
        chosen_section = st.selectbox("Filter by section", all_sections)
    with search_col:
        search_term = st.text_input(
            "Search within text",
            placeholder="e.g. going concern, climate, dividend"
        )

    filtered = text_df.copy()
    if chosen_section != "All sections":
        filtered = filtered[filtered["section"] == chosen_section]
    if search_term.strip():
        mask = (
            filtered["text"].str.contains(search_term, case=False, na=False) |
            filtered["heading"].str.contains(search_term, case=False, na=False)
        )
        filtered = filtered[mask]

    result_count = len(filtered)
    st.markdown(f"**{result_count}** chunk(s) shown")

    if result_count == 0:
        st.info("No results match your filter / search.")
    else:
        display_limit = 50
        if result_count > display_limit:
            st.caption(f"Showing first {display_limit} of {result_count} results. Download CSV for full set.")

        for _, row in filtered.head(display_limit).iterrows():
            label = f"[{row['section']}]"
            if row["heading"]:
                label += f"  {row['heading']}"
            label += f"  —  {row['char_count']:,} chars"
            with st.expander(label):
                st.markdown(f'<div class="chunk-text">{row["text"]}</div>', unsafe_allow_html=True)

# ── Download ───────────────────────────────────────────────────────────────────
st.divider()
st.markdown('<div class="section-header">Download</div>', unsafe_allow_html=True)

dl_col1, dl_col2 = st.columns(2)

with dl_col1:
    csv_all = text_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download all sections (CSV)",
        data=csv_all,
        file_name=f"{filename}_text_sections.csv",
        mime="text/csv",
        use_container_width=True,
    )

with dl_col2:
    if chosen_section != "All sections" or search_term.strip():
        csv_filtered = filtered.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download filtered results (CSV)",
            data=csv_filtered,
            file_name=f"{filename}_text_sections_filtered.csv",
            mime="text/csv",
            use_container_width=True,
        )
    else:
        st.button("⬇️ Download filtered results (CSV)", disabled=True,
                  help="Apply a section filter or search term first",
                  use_container_width=True)
