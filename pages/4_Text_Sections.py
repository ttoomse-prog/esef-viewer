import streamlit as st
import pandas as pd
import re

st.set_page_config(page_title="Text Sections", page_icon="📄", layout="wide")

st.markdown("""
<style>
    [data-testid="stSidebar"] { background: #1e3a5f; }
    [data-testid="stSidebar"] * { color: #e2e8f0 !important; }
    .section-header { font-size:1.05rem; font-weight:600; color:#1e3a5f; margin:1.5rem 0 0.75rem 0;
        padding-bottom:0.35rem; border-bottom:2px solid #e2e8f0; }
    .chunk-text { background:#f8fafc; border-left:3px solid #1e3a5f; padding:0.75rem 1rem;
        border-radius:0 6px 6px 0; font-size:0.9rem; line-height:1.6; color:#1a1a1a; }
    .full-read { background:#ffffff; border:1px solid #e2e8f0; border-radius:8px;
        padding:1.5rem 2rem; font-size:0.92rem; line-height:1.8; color:#1a1a1a;
        max-height:70vh; overflow-y:auto; }
    .full-read h3 { font-size:1rem; font-weight:700; color:#1e3a5f;
        margin:1.25rem 0 0.4rem 0; padding-bottom:0.2rem;
        border-bottom:1px solid #e2e8f0; }
    .full-read p { margin:0 0 0.75rem 0; }
    .search-highlight { background:#fef08a; border-radius:2px; padding:0 2px; }
    .section-divider { font-size:1.1rem; font-weight:700; color:#1e3a5f;
        margin:1.5rem 0 0.5rem 0; }
</style>
""", unsafe_allow_html=True)

st.title("📄 Text Sections")
st.caption(
    "Narrative text extracted from the iXBRL report, classified into annual report sections. "
    "XBRL inline tags are stripped — this shows the human-readable content only."
)

# ── Guard ──────────────────────────────────────────────────────────────────────
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
col1, col2, col3, col4 = st.columns(4)
col1.metric("Text chunks", f"{len(text_df):,}")
col2.metric("Sections identified", text_df["section"].nunique())
col3.metric("Total characters", f"{text_df['char_count'].sum():,}")
col4.metric("Approx. words", f"{text_df['text'].str.split().str.len().sum():,}")

st.divider()

# Search term is defined in the right column but the summary table
# in the left column needs to reference it — so define the controls first,
# then render both columns.

# Temporary placeholder columns for layout; we'll re-render left after search is known
_ctrl1, _ctrl2, _ctrl3 = st.columns([2, 2, 1])
with _ctrl1:
    all_sections = ["All sections"] + sorted(text_df["section"].unique().tolist())
    chosen_section = st.selectbox("Filter by section", all_sections)
with _ctrl2:
    search_term = st.text_input(
        "Search within text",
        placeholder="e.g. going concern, climate"
    )
with _ctrl3:
    view_mode = st.radio(
        "View mode",
        ["Chunks", "Full read"],
        horizontal=True,
        help=(
            "**Chunks**: each heading as a collapsible block.\n\n"
            "**Full read**: entire section as one continuous scrollable text."
        )
    )

# ── Filter data ───────────────────────────────────────────────────────────────
filtered = text_df.copy()
if chosen_section != "All sections":
    filtered = filtered[filtered["section"] == chosen_section]
if search_term.strip():
    mask = (
        filtered["text"].str.contains(search_term, case=False, na=False) |
        filtered["heading"].str.contains(search_term, case=False, na=False)
    )
    filtered = filtered[mask]

# ── Section summary + mention counts ─────────────────────────────────────────
left, right = st.columns([1, 2])

with left:
    st.markdown('<div class="section-header">Sections found</div>', unsafe_allow_html=True)

    section_summary = (
        text_df.groupby("section")
        .agg(Chunks=("seq", "count"), Characters=("char_count", "sum"))
        .reset_index()
        .rename(columns={"section": "Section"})
    )

    if search_term.strip():
        def count_mentions(section_name: str) -> int:
            rows = text_df[text_df["section"] == section_name]
            combined = " ".join(
                rows["text"].fillna("") + " " + rows["heading"].fillna("")
            )
            return len(re.findall(re.escape(search_term), combined, re.IGNORECASE))

        section_summary["Mentions"] = section_summary["Section"].apply(count_mentions)
        section_summary = section_summary.sort_values("Mentions", ascending=False)
        total_mentions = int(section_summary["Mentions"].sum())
        st.caption(
            f'**"{search_term}"** — **{total_mentions:,}** mention'
            f'{"s" if total_mentions != 1 else ""} across all sections'
        )
    else:
        section_summary = section_summary.sort_values("Characters", ascending=False)

    st.dataframe(section_summary, hide_index=True, use_container_width=True)

with right:
    st.markdown('<div class="section-header">Browse & read</div>', unsafe_allow_html=True)

    result_count = len(filtered)
    st.markdown(f"**{result_count}** chunk(s) shown")

    if result_count == 0:
        st.info("No results match your filter / search.")

    # ── FULL READ mode ────────────────────────────────────────────────────────
    elif view_mode == "Full read":

        def highlight(text: str, term: str) -> str:
            if not term.strip():
                return text
            return re.sub(
                f"({re.escape(term)})",
                r'<span class="search-highlight">\1</span>',
                text, flags=re.IGNORECASE
            )

        def render_full_read(group_df: pd.DataFrame) -> str:
            parts = []
            for _, row in group_df.sort_values("seq").iterrows():
                if row["heading"]:
                    parts.append(f"<h3>{row['heading']}</h3>")
                parts.append(f"<p>{highlight(row['text'], search_term)}</p>")
            return '<div class="full-read">' + "\n".join(parts) + "</div>"

        if chosen_section == "All sections":
            # Render each section as its own scrollable block
            for section_name, group in filtered.groupby("section", sort=False):
                st.markdown(f'<div class="section-divider">📑 {section_name}</div>',
                            unsafe_allow_html=True)
                st.markdown(render_full_read(group), unsafe_allow_html=True)
                st.markdown("")
        else:
            # Single section — one continuous scrollable document
            st.markdown(render_full_read(filtered), unsafe_allow_html=True)

    # ── CHUNKS mode ───────────────────────────────────────────────────────────
    else:
        display_limit = 50
        if result_count > display_limit:
            st.caption(
                f"Showing first {display_limit} of {result_count}. "
                "Download CSV for full set, or switch to Full read mode."
            )

        for _, row in filtered.head(display_limit).iterrows():
            label = f"[{row['section']}]"
            if row["heading"]:
                label += f"  {row['heading']}"
            label += f"  —  {row['char_count']:,} chars"
            with st.expander(label):
                st.markdown(
                    f'<div class="chunk-text">{row["text"]}</div>',
                    unsafe_allow_html=True
                )

# ── Download ───────────────────────────────────────────────────────────────────
st.divider()
st.markdown('<div class="section-header">Download</div>', unsafe_allow_html=True)

dl1, dl2 = st.columns(2)
with dl1:
    st.download_button(
        "⬇️ Download all sections (CSV)",
        data=text_df.to_csv(index=False).encode("utf-8"),
        file_name=f"{filename}_text_sections.csv",
        mime="text/csv",
        use_container_width=True,
    )
with dl2:
    if chosen_section != "All sections" or search_term.strip():
        st.download_button(
            "⬇️ Download filtered results (CSV)",
            data=filtered.to_csv(index=False).encode("utf-8"),
            file_name=f"{filename}_text_sections_filtered.csv",
            mime="text/csv",
            use_container_width=True,
        )
    else:
        st.button("⬇️ Download filtered results (CSV)", disabled=True,
                  help="Apply a section filter or search first",
                  use_container_width=True)
